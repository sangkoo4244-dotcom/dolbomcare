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
    app.state.Session = Session
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
    assert next(x for x in data["rows"] if x["name"] == "이이")["danger"] is True  # 90분 차이
    assert next(x for x in data["rows"] if x["name"] == "김일")["danger"] is False
    assert status["김일"] == "ok" and status["이이"] == "time_diff" and status["최없음"] == "unknown_resident" and status["박삼"] == "no_tag"
    assert data["counts"]["ok"] == 1 and data["tag_count"] == 3


def test_auto_rate_follows_nhis_formula(ctx):
    # 김일·이이는 시작·종료 모두 전송(자동), 박삼은 태그 없음(직접 입력) -> 2/3 = 67%
    rows = [["김일", f"{D} 09:10", f"{D} 10:08"], ["이이", f"{D} 14:00", f"{D} 15:00"]]
    body = {"rows": rows, "resident_col": 0, "start_col": 1, "end_col": 2}
    a = ctx.post("/api/v1/rfid-compare/compare", json=body, headers=MGR).json()["auto_rate"]
    assert (a["total"], a["auto"], a["direct"], a["end_missing"], a["rate"]) == (3, 2, 1, 0, 67)
    assert a["meets_75"] is False and a["need_more"] == 1

    # 이이의 종료가 전송되지 않으면 자동청구율에서 빠진다 -> 1/3 = 33%
    rows[1][2] = ""
    d = ctx.post("/api/v1/rfid-compare/compare", json={**body, "rows": rows}, headers=MGR).json()
    a = d["auto_rate"]
    assert (a["auto"], a["end_missing"], a["rate"]) == (1, 1, 33)
    no_end = next(x for x in d["rows"] if x["name"] == "이이")
    assert no_end["status"] == "time_diff" and "종료 전송이 없습니다" in no_end["note"]

    # 박삼도 태그가 있으면 3/3 = 100%, 75% 이상이라 14일 지급 대상
    rows = [["김일", f"{D} 09:10", f"{D} 10:08"], ["이이", f"{D} 14:00", f"{D} 15:00"], ["박삼", f"{D} 11:00", f"{D} 12:00"]]
    a = ctx.post("/api/v1/rfid-compare/compare", json={**body, "rows": rows}, headers=MGR).json()["auto_rate"]
    assert a["rate"] == 100 and a["meets_75"] is True and a["need_more"] == 0

    # 종료 시각 열을 지정하지 않으면 계산하지 않는다
    assert ctx.post("/api/v1/rfid-compare/compare", json={"rows": rows, "resident_col": 0, "start_col": 1}, headers=MGR).json()["auto_rate"] is None


def test_eval_index_scores_participation_and_use_rate_and_names_who_to_follow_up(ctx):
    db = ctx.app.state.Session()
    db.add(models.User(id=3, email="c3@e.com", hashed_password="x", full_name="이요양", role="caregiver", center_id=1))
    # 이요양은 김일에게 16시 방문이 있지만 태그를 찍지 않았다
    db.add(models.Schedule(id=4, caregiver_id=3, resident_id=1, center_id=1, scheduled_date=DAY + timedelta(hours=16), duration_minutes=60, status="scheduled"))
    db.commit()
    db.close()
    rows = [["김일", f"{D} 09:10", f"{D} 10:08"], ["이이", f"{D} 14:00", f"{D} 15:00"]]  # 박삼(김요양)·김일 16시(이요양)는 태그 없음
    body = {"rows": rows, "resident_col": 0, "start_col": 1, "end_col": 2}
    e = ctx.post("/api/v1/rfid-compare/compare", json=body, headers=MGR).json()["eval_index"]
    # 요양보호사 2명 중 1명만 참여 50%, 청구 대상 4건 중 자동 2건 50% -> 미흡, 다음은 보통(85%·80%)
    assert (e["caregiver_total"], e["participating"], e["participation_rate"]) == (2, 1, 50.0)
    assert (e["visit_total"], e["auto"], e["use_rate"], e["level"], e["points"]) == (4, 2, 50.0, "미흡", 0)
    assert e["target"]["label"] == "보통" and e["target"]["need_caregivers"] == 1 and e["target"]["need_visits"] == 2
    first = e["caregivers"][0]  # 문제가 많은 요양보호사부터
    assert first["name"] in ("김요양", "이요양") and {c["name"]: c["tagged"] for c in e["caregivers"]} == {"김요양": 2, "이요양": 0}

    # 전부 태그를 찍으면 우수(3점), 더 올릴 등급이 없다
    rows += [["박삼", f"{D} 11:00", f"{D} 12:00"], ["김일", f"{D} 16:00", f"{D} 17:00"]]
    e = ctx.post("/api/v1/rfid-compare/compare", json={**body, "rows": rows}, headers=MGR).json()["eval_index"]
    assert (e["participation_rate"], e["use_rate"], e["level"], e["points"], e["target"]) == (100.0, 100.0, "우수", 3, None)

    # 참여율은 95%를 넘어도 청구활용률이 90% 미만이면 우수가 아니다: 종료 전송이 빠진 건이 있는 경우
    rows[3][2] = ""
    e = ctx.post("/api/v1/rfid-compare/compare", json={**body, "rows": rows}, headers=MGR).json()["eval_index"]
    assert (e["participation_rate"], e["use_rate"], e["level"]) == (100.0, 75.0, "미흡")

    # 종료 시각 열이 없으면 계산하지 않는다
    assert ctx.post("/api/v1/rfid-compare/compare", json={"rows": rows, "resident_col": 0, "start_col": 1}, headers=MGR).json()["eval_index"] is None


def test_nhis_screen_layout_two_row_headers_are_merged_and_single_row_is_unchanged(ctx):
    # 공단 '요양요원 전송내역' 화면처럼 제목이 두 줄(묶음 제목 + 시작/종료)인 파일
    two_row = [["구분", "수급자명(서명)", "급여계약통보서", "", "서비스제공", "", "사용여부"],
               ["", "", "시작", "종료", "시작", "종료", ""],
               ["자동전송", "김일(서명)", f"{D} 09:00", f"{D} 10:00", f"{D} 09:10", f"{D} 10:08", "사용"]]
    r = ctx.post("/api/v1/rfid-compare/parse", files={"file": ("x.xlsx", make_xlsx(two_row))}, headers=MGR).json()
    assert r["headers"] == ["구분", "수급자명(서명)", "급여계약통보서 시작", "급여계약통보서 종료", "서비스제공 시작", "서비스제공 종료", "사용여부"]
    assert r["row_count"] == 1 and r["rows"][0][1] == "김일(서명)"
    # 한 줄 제목은 그대로, 데이터 둘째 줄을 제목으로 착각하지 않는다
    one_row = [["수급자", "시작", "종료"], ["김일", f"{D} 09:10", f"{D} 10:08"], ["이이", f"{D} 14:00", f"{D} 15:00"]]
    r = ctx.post("/api/v1/rfid-compare/parse", files={"file": ("x.xlsx", make_xlsx(one_row))}, headers=MGR).json()
    assert r["headers"] == ["수급자", "시작", "종료"] and r["row_count"] == 2


def test_name_suffix_is_ignored_and_unused_rows_count_as_direct_input(ctx):
    rows = [["김일(서명)", f"{D} 09:10", f"{D} 10:08", "사용"],
            ["이이", f"{D} 14:00", f"{D} 15:00", "미 사용"]]  # 공단에서 미사용으로 지정 = 직접 입력
    body = {"rows": rows, "resident_col": 0, "start_col": 1, "end_col": 2, "use_col": 3}
    d = ctx.post("/api/v1/rfid-compare/compare", json=body, headers=MGR).json()
    by = {x["name"]: x for x in d["rows"] if x["row"]}
    assert by["김일"]["status"] == "ok"  # '(서명)'이 붙어도 같은 이용자로 맞춘다
    assert by["이이"]["status"] == "time_diff" and "미사용" in by["이이"]["note"]
    a = d["auto_rate"]
    # 청구 대상 3건(김일·이이·박삼): 자동은 김일 1건뿐, 이이(미사용)와 박삼(태그 없음)은 직접 입력
    assert (a["total"], a["auto"], a["direct"], a["end_missing"]) == (3, 1, 2, 0)
    e = d["eval_index"]
    assert (e["visit_total"], e["auto"], e["caregivers"][0]["unused"]) == (3, 1, 1)
    # 사용여부 열을 지정하지 않으면 미사용 표시를 쓰지 않는다
    d = ctx.post("/api/v1/rfid-compare/compare", json={**body, "use_col": None}, headers=MGR).json()
    assert d["auto_rate"]["auto"] == 2


def test_compare_needs_readable_rows_and_manager(ctx):
    assert ctx.post("/api/v1/rfid-compare/compare", json={"rows": [["", "x"]], "resident_col": 0, "start_col": 1}, headers=MGR).status_code == 400
    assert ctx.post("/api/v1/rfid-compare/compare", json={"rows": [["김일", f"{D} 09:10"]], "resident_col": 0, "start_col": 1}, headers=CG).status_code == 403
