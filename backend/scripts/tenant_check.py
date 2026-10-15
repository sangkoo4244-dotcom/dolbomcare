"""센터 간 자료 분리 점검: 모든 API를 '다른 센터' 사용자(센터장·요양보호사·보호자)로 자동 호출해,
우리 센터 자료가 보이거나 바뀌는(200) 곳을 찾는다.

임시 SQLite DB에서만 돌아가므로 운영 데이터와 무관하다. 새 API를 만든 뒤 한 번 돌려 보는 용도다.
    cd backend && venv/Scripts/python.exe scripts/tenant_check.py            # 센터B의 자기 자료(user_id=11)를 대상으로
    FUZZ_USER_ID=2 venv/Scripts/python.exe scripts/tenant_check.py            # 센터A 직원 번호(2)를 넣어 보기
"확인 필요" 항목이 비어 있어야 한다. 센터B 자신의 자료(자기 정보 수정 등)가 나오는 줄은 정상이다.
"""
import datetime as dt
import os
import re
import sys
import tempfile
from datetime import timedelta

DB = os.path.join(tempfile.gettempdir(), "tenant_check.db")
if os.path.exists(DB):
    os.remove(DB)
os.environ["DATABASE_URL"] = "sqlite:///" + DB
os.environ["SECRET_KEY"] = "tenant-check-key"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import sqlalchemy as sa  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
import app.models as models  # noqa: E402

Base.metadata.create_all(bind=engine)
db = SessionLocal()
NOW = dt.datetime.now()
USER_ID = int(os.environ.get("FUZZ_USER_ID", "11"))
LINK_COLUMNS = ("center_id", "resident_id", "caregiver_id", "user_id", "author_id", "sender_id", "uploaded_by", "created_by", "guardian_id")
USER_LIKE = ("caregiver_id", "user_id", "uploaded_by", "author_id", "sender_id", "created_by", "writer_id", "manager_id", "approved_by", "confirmed_by")


def fake(col):
    t, name = col.type, col.name
    if name in ("center_id", "resident_id"):
        return 1
    if name in USER_LIKE:
        return 2
    if name.endswith("_id"):
        return 1
    if isinstance(t, sa.Boolean):
        return False
    if isinstance(t, sa.Integer):
        return 1
    if isinstance(t, (sa.Float, sa.Numeric)):
        return 1.0
    if isinstance(t, sa.DateTime):
        return NOW
    if isinstance(t, sa.Date):
        return NOW.date()
    if isinstance(t, sa.Time):
        return NOW.time()
    return "x"


def add_row(cls, **over):
    vals = {}
    for col in cls.__table__.columns:
        if col.primary_key and isinstance(col.type, sa.Integer):
            continue
        if col.name in over:
            vals[col.name] = over[col.name]
        elif col.name in LINK_COLUMNS or (not col.nullable and col.default is None and col.server_default is None):
            vals[col.name] = fake(col)
    obj = cls(**vals)
    for k, v in over.items():
        setattr(obj, k, v)
    db.add(obj)
    db.flush()
    return obj


from app.api.users import create_access_token  # noqa: E402

# 센터 A(자료가 있는 쪽)와 센터 B(공격자 쪽)
add_row(models.Center, id=1, name="A센터")
add_row(models.Center, id=2, name="B센터")
for u in (
    dict(id=1, email="mgrA@t.kr", full_name="A센터장", role="center_manager", center_id=1),
    dict(id=2, email="cgA@t.kr", full_name="A요양", role="caregiver", center_id=1),
    dict(id=11, email="mgrB@t.kr", full_name="B센터장", role="center_manager", center_id=2),
    dict(id=12, email="cgB@t.kr", full_name="B요양", role="caregiver", center_id=2),
    dict(id=19, email="gB@t.kr", full_name="B보호자", role="guardian", center_id=None),
    dict(id=21, email="gA@t.kr", full_name="A보호자", role="guardian", center_id=None),
):
    add_row(models.User, hashed_password="x", is_active=True, **u)
add_row(models.Resident, id=1, center_id=1, name="A이용자", care_grade=3, client_type="일반", guardian_id=21, primary_caregiver_id=2)
add_row(models.Resident, id=2, center_id=2, name="B이용자", care_grade=3, client_type="일반", guardian_id=19, primary_caregiver_id=12)
db.commit()

skip = {models.Center, models.User, models.Resident}
for mapper in Base.registry.mappers:
    cls = mapper.class_
    if cls in skip:
        continue
    try:
        add_row(cls, id=1) if "id" in cls.__table__.columns else add_row(cls)
        db.commit()
    except Exception as e:  # 자료를 못 넣은 표는 건너뛴다(그 표의 API는 점검이 약해진다)
        db.rollback()
        print("자료를 넣지 못한 표:", cls.__name__, str(e)[:60])

tokens = {
    key: create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=5))
    for key, (uid, email, role) in {"mgrB": (11, "mgrB@t.kr", "center_manager"), "cgB": (12, "cgB@t.kr", "caregiver"), "gB": (19, "gB@t.kr", "guardian")}.items()
}

import main  # noqa: E402  (DB가 준비된 뒤에 불러온다)
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(main.app)
spec = client.get("/openapi.json").json()
schemas = spec.get("components", {}).get("schemas", {})


def resolve(s):
    return resolve(schemas[s["$ref"].split("/")[-1]]) if "$ref" in s else s


def value_for(s, name=""):
    s = resolve(s)
    if "anyOf" in s:
        opts = [o for o in s["anyOf"] if o.get("type") != "null"]
        return value_for(opts[0], name) if opts else None
    if "enum" in s:
        return s["enum"][0]
    t = s.get("type")
    if t == "integer":
        return {"center_id": 1, "resident_id": 1, "caregiver_id": 2, "user_id": USER_ID, "co_caregiver_id": None}.get(name, 1)
    if t == "number":
        return 1
    if t == "boolean":
        return False
    if t == "array":
        return [value_for(s.get("items", {}), name)]
    if t == "object":
        return {k: value_for(v, k) for k, v in s.get("properties", {}).items() if k in s.get("required", [])}
    fmt = s.get("format")
    if fmt == "date":
        return NOW.date().isoformat()
    if fmt == "date-time":
        return NOW.isoformat()
    if fmt == "email":
        return "a@b.co"
    if name == "year_month":
        return NOW.strftime("%Y-%m")
    if name in ("arrive_time", "leave_time"):
        return "09:00"
    return "x"


results = []
for path, ops in spec["paths"].items():
    for method, op in ops.items():
        if method not in ("get", "post", "put", "patch", "delete"):
            continue
        url, params = path, {}
        for p in op.get("parameters", []):
            if not p.get("required") and p["in"] == "query" and p["name"] not in ("center_id", "resident_id", "caregiver_id"):
                continue
            v = value_for(p["schema"], p["name"])
            if p["in"] == "path":
                url = url.replace("{" + p["name"] + "}", str(v))
            elif p["in"] == "query":
                params[p["name"]] = v
        rb = op.get("requestBody", {}).get("content", {}).get("application/json")
        body = value_for(rb["schema"], "") if rb else None
        for who in ("mgrB", "cgB", "gB"):
            try:
                r = client.request(method.upper(), url, params=params, json=body, headers={"Authorization": "Bearer " + tokens[who]})
                results.append((method.upper(), path, who, r.status_code, r.text[:140]))
            except Exception as e:
                results.append((method.upper(), path, who, "EXC", str(e)[:140]))

mark = re.compile(r'A이용자|A센터|A요양|A보호자|mgrA|cgA|gA@t|"center_id":\s*1\b|"resident_id":\s*1\b|"caregiver_id":\s*2\b|"user_id":\s*2\b|"id":\s*[12],"email"|"deleted"')
safe_own = re.compile(r"auth/me|users/me|forgot|notification|read-all|records/test|batch-delete|import|preview|centers/me")
problems = [r for r in results if r[3] == 200 and (mark.search(r[4]) or (r[0] != "GET" and not safe_own.search(r[1])))]
errors = [r for r in results if r[3] in (500, "EXC")]
blocked = sum(1 for r in results if r[3] in (401, 403, 404))
print(f"호출 {len(results)}건 (403/404 등으로 막힘 {blocked}건)")
print("== 확인 필요(다른 센터 사용자에게 200) ==")
for m, p, who, code, text in problems:
    print(f"  {m:6} {p:50} {who:5} {text[:90]!r}")
print("== 서버 오류(500) ==")
for m, p, who, code, text in errors:
    print(f"  {code} {m} {p} {who} {text[:90]!r}")
