import io
import zipfile
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import rfid_compare
from app.api.users import create_access_token
from app.database import Base, get_db
from app.sheet_reader import read_table, to_datetime

DAY = (datetime.now() - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)


def make_xlsx(rows):
    strings = []

    def sid(text):
        if text not in strings:
            strings.append(text)
        return strings.index(text)

    xml_rows = []
    for r, row in enumerate(rows, start=1):
        cells = "".join(f'<c r="{chr(65 + c)}{r}" t="s"><v>{sid(str(v))}</v></c>' for c, v in enumerate(row))
        xml_rows.append(f'<row r="{r}">{cells}</row>')
    sheet = '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(xml_rows) + "</sheetData></worksheet>"
    sst = '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", sheet)
        z.writestr("xl/sharedStrings.xml", sst)
    return buf.getvalue()


@pytest.fixture
def ctx(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'rc.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A"),
        models.User(id=1, email="m@e.com", hashed_password="x", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@e.com", hashed_password="x", full_name="김요양", role="caregiver", center_id=1),
        models.Resident(id=1, center_id=1, name="김일", age=80, health_status="stable", care_grade=3, client_type="일반"),
        models.Resident(id=2, center_id=1, name="이이", age=80, health_status="stable", care_grade=3, client_type="일반"),
        models.Resident(id=3, center_id=1, name="박삼", age=80, health_status="stable", care_grade=3, client_type="일반"),
        # 김일: 계획 09:00, 실제 도착 09:05 -> 태그 09:10 이면 정상
        models.Schedule(id=1, caregiver_id=2, resident_id=1, center_id=1, scheduled_date=DAY + timedelta(hours=9), duration_minutes=60, status="scheduled", arrived_at=DAY + timedelta(hours=9, minutes=5)),
        # 이이: 계획 14:00, 태그가 15:30 -> 시간 차이
        models.Schedule(id=2, caregiver_id=2, resident_id=2, center_id=1, scheduled_date=DAY + timedelta(hours=14), duration_minutes=60, status="scheduled"),
        # 박삼: 계획만 있고 태그 없음
        models.Schedule(id=3, caregiver_id=2, resident_id=3, center_id=1, scheduled_date=DAY + timedelta(hours=11), duration_minutes=60, status="scheduled"),
    ])
    db.commit()
    db.close()
    app = FastAPI()
    app.include_router(rfid_compare.router, prefix="/api/v1/rfid-compare")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MGR = auth(1, "center_manager", "m@e.com")
CG = auth(2, "caregiver", "c@e.com")
D = DAY.strftime("%Y-%m-%d")


def test_xlsx_and_csv_are_read_and_dates_understood():
    rows = read_table("a.xlsx", make_xlsx([["수급자", "시작"], ["김일", f"{D} 09:10"]]))
    assert rows == [["수급자", "시작"], ["김일", f"{D} 09:10"]]
    assert read_table("a.csv", "수급자,시작\n김일,09:10\n".encode("utf-8-sig"))[1] == ["김일", "09:10"]
    assert to_datetime("2026-10-14 09:10") == datetime(2026, 10, 14, 9, 10)
    assert to_datetime("20261014") == datetime(2026, 10, 14)
    assert to_datetime("09:10", "2026-10-14") == datetime(2026, 10, 14, 9, 10)
    assert to_datetime("46309.375").hour == 9  # 엑셀 일련번호
    assert to_datetime("abc") is None


def test_parse_upload_returns_headers_without_saving(ctx):
    r = ctx.post("/api/v1/rfid-compare/parse", files={"file": ("x.xlsx", make_xlsx([["수급자", "시작"], ["김일", f"{D} 09:10"]]))}, headers=MGR)
    assert r.status_code == 200 and r.json()["headers"] == ["수급자", "시작"] and r.json()["row_count"] == 1
    assert ctx.post("/api/v1/rfid-compare/parse", files={"file": ("x.pdf", b"x")}, headers=MGR).status_code == 400
    assert ctx.post("/api/v1/rfid-compare/parse", files={"file": ("x.xlsx", make_xlsx([["a"], ["b"]]))}, headers=CG).status_code == 403


def test_compare_finds_ok_time_diff_missing_plan_and_missing_tag(ctx):
    rows = [
        ["김일", f"{D} 09:10", f"{D} 10:08"],   # 정상(도착 09:05 기준 5분 차이)
        ["이이", f"{D} 15:30", f"{D} 16:30"],   # 계획 14:00과 90분 차이
        ["최없음", f"{D} 10:00", f"{D} 11:00"],  # 돌봄케어에 없는 이름
    ]
    r = ctx.post("/api/v1/rfid-compare/compare", json={"rows": rows, "resident_col": 0, "start_col": 1, "end_col": 2, "tolerance_minutes": 30}, headers=MGR)
    assert r.status_code == 200
    data = r.json()
    status = {x["name"]: x["status"] for x in data["rows"]}
    assert status["김일"] == "ok" and status["이이"] == "time_diff" and status["최없음"] == "unknown_resident" and status["박삼"] == "no_tag"
    assert data["counts"]["ok"] == 1 and data["tag_count"] == 3


def test_compare_needs_readable_rows_and_manager(ctx):
    assert ctx.post("/api/v1/rfid-compare/compare", json={"rows": [["", "x"]], "resident_col": 0, "start_col": 1}, headers=MGR).status_code == 400
    assert ctx.post("/api/v1/rfid-compare/compare", json={"rows": [["김일", f"{D} 09:10"]], "resident_col": 0, "start_col": 1}, headers=CG).status_code == 403
