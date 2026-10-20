from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import day_care, records
from app.api.users import create_access_token
from app.database import Base, get_db
from app.review import review_flags


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MGR = auth(1, "center_manager", "m@test.com")
CG = auth(2, "caregiver", "a@test.com")
CG2 = auth(3, "caregiver", "b@test.com")
OTHER_MGR = auth(7, "center_manager", "o@test.com")
DAY = datetime(2026, 10, 13).date()
MONTH = DAY.strftime("%Y-%m")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'dc.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="주야간센터", service_types="주야간보호,방문요양,방문목욕"),
        models.Center(id=2, name="방문만", service_types="방문요양"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="a@test.com", full_name="요양A", role="caregiver", center_id=1),
        models.User(id=3, email="b@test.com", full_name="요양B", role="caregiver", center_id=1),
        models.User(id=7, email="o@test.com", full_name="방문만센터장", role="center_manager", center_id=2),
        models.User(id=9, email="g@test.com", full_name="보호자", role="guardian", center_id=1),
        models.Resident(id=1, center_id=1, name="김일", care_grade=3, client_type="일반", guardian_id=9),
        models.Resident(id=2, center_id=1, name="이이", care_grade=None, client_type="기초생활보장"),
        models.Resident(id=3, center_id=2, name="타센터", care_grade=3, client_type="일반"),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(day_care.router, prefix="/api/v1/day-care")
    app.include_router(records.router, prefix="/api/v1/records")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def body(**kw):
    base = {"resident_id": 1, "attendance_date": DAY.isoformat(), "arrive_time": "09:00", "leave_time": "17:00"}
    base.update(kw)
    return base


def test_preview_shows_fee_transport_and_bath_bonus(env):
    _, client = env
    r = client.post("/api/v1/day-care/preview", json=body(transport="both", distance_km=7, bath_given=True), headers=CG).json()
    assert r["ok"] is True and r["minutes"] == 480
    assert (r["fee_total"], r["patient"], r["insurer"]) == (59640, 8940, 50700)  # 8시간 이상 10시간 미만, 3등급
    assert (r["transport_code"], r["transport_amount"], r["bath_bonus"], r["extra_amount"]) == ("러-2", 2630, 3000, 5630)
    # 편도만이면 이동서비스비용 50%
    assert client.post("/api/v1/day-care/preview", json=body(transport="in", distance_km=7), headers=CG).json()["transport_amount"] == 1315
    # 입력이 부족하면 계산하지 않고 이유를 알려 준다
    bad = client.post("/api/v1/day-care/preview", json=body(transport="both"), headers=CG).json()
    assert bad["ok"] is False and "최단거리" in bad["message"]


def test_create_makes_a_day_attendance_and_a_draft_bill_with_extra_amount(env):
    db, client = env
    r = client.post("/api/v1/day-care", json=body(transport="both", distance_km=3, bath_given=True, notes="점심 식사 양호"), headers=CG)
    assert r.status_code == 200, r.text
    a, b = db.query(models.DayCareAttendance).one(), db.query(models.BillingRecord).one()
    assert (a.minutes, a.caregiver_id, a.transport_amount, a.bath_bonus) == (480, 2, 830, 3000) and a.billing_record_id == b.id
    assert (b.benefit_type, b.total_cost, b.amount, b.extra_amount, b.approval_status) == ("day_night", 59640, 50700, 3830, "draft")
    assert b.service_category == "재가급여" and b.caregiver_id == 2 and b.year_month == DAY.strftime("%Y-%m")
    assert "주·야간보호" in db.query(models.Notification).filter(models.Notification.user_id == 9).one().message


def test_cognitive_support_grade_and_time_bands(env):
    db, client = env
    r = client.post("/api/v1/day-care", json=body(resident_id=2, arrive_time="10:00", leave_time="13:20"), headers=CG)
    assert r.status_code == 200 and r.json()["fee_total"] == 32490 and r.json()["insurer"] == 32490  # 인지지원등급 3시간 이상, 본인부담 없음
    assert client.post("/api/v1/day-care/preview", json=body(arrive_time="09:00", leave_time="11:59"), headers=CG).json()["ok"] is False  # 3시간 미만은 청구할 수 없다


def test_input_rules_are_enforced(env):
    db, client = env
    assert client.post("/api/v1/day-care", json=body(arrive_time="17:00", leave_time="09:00"), headers=CG).status_code == 400  # 24시 이후까지 걸치는 입력
    assert client.post("/api/v1/day-care", json=body(arrive_time="9시", leave_time="17:00"), headers=CG).status_code == 400
    assert client.post("/api/v1/day-care", json=body(arrive_time="09:00", leave_time="11:00"), headers=CG).status_code == 400  # 3시간 미만
    assert client.post("/api/v1/day-care", json=body(transport="both"), headers=CG).status_code == 400  # 거리 없음
    assert client.post("/api/v1/day-care", json=body(resident_id=3), headers=CG).status_code == 404  # 다른 센터 이용자
    assert client.post("/api/v1/day-care", json=body(), headers=MGR).status_code == 400  # 센터장은 기록할 요양보호사를 골라야 한다
    assert client.post("/api/v1/day-care", json=body(caregiver_id=3), headers=MGR).status_code == 200
    assert client.post("/api/v1/day-care", json=body(), headers=CG).status_code == 409  # 같은 날 중복
    assert db.query(models.DayCareAttendance).one().caregiver_id == 3


def test_service_must_be_selected_by_the_center(env):
    _, client = env
    r = client.post("/api/v1/day-care", json=body(resident_id=3), headers=OTHER_MGR)
    assert r.status_code == 400 and "센터 정보" in r.json()["detail"]
    assert client.get(f"/api/v1/day-care?year_month={MONTH}", headers=OTHER_MGR).status_code == 400


def test_bath_bonus_is_once_a_week(env):
    db, client = env
    monday = DAY - timedelta(days=DAY.weekday())
    first = client.post("/api/v1/day-care", json=body(attendance_date=monday.isoformat(), bath_given=True), headers=CG).json()
    second = client.post("/api/v1/day-care", json=body(attendance_date=(monday + timedelta(days=2)).isoformat(), bath_given=True), headers=CG).json()
    nextweek = client.post("/api/v1/day-care", json=body(attendance_date=(monday + timedelta(days=7)).isoformat(), bath_given=True), headers=CG).json()
    assert (first["bath_bonus"], second["bath_bonus"], nextweek["bath_bonus"]) == (3000, 0, 3000)
    assert any("주 1회" in n for n in second["notes"])


def test_same_day_day_care_and_home_bath_exclude_each_other(env):
    db, client = env
    # 방문목욕이 먼저 있으면 주·야간보호 기록을 거절
    db.add(models.User(id=4, email="c@test.com", full_name="요양C", role="caregiver", center_id=1))
    db.add(models.DailyRecord(resident_id=1, caregiver_id=2, recorded_date=datetime.combine(DAY, datetime.min.time()) + timedelta(hours=10),
                              duration_minutes=60, benefit_type="home_bath", bath_mode="vehicle_in", co_caregiver_id=4))
    db.commit()
    r = client.post("/api/v1/day-care", json=body(), headers=CG)
    assert r.status_code == 400 and "방문목욕" in r.json()["detail"]
    # 주·야간보호가 먼저 있으면 방문목욕 기록을 거절
    other_day = DAY - timedelta(days=1)
    assert client.post("/api/v1/day-care", json=body(attendance_date=other_day.isoformat()), headers=CG).status_code == 200
    bath = {"caregiver_id": 2, "resident_id": 1, "service_type": "basic_care", "notes": "목욕", "benefit_type": "home_bath", "bath_mode": "vehicle_in",
            "co_caregiver_id": 4, "duration_minutes": 60, "recorded_date": (datetime.combine(other_day, datetime.min.time()) + timedelta(hours=11)).isoformat()}
    r = client.post("/api/v1/records/create", json=bath, headers=CG)
    assert r.status_code == 400 and "주·야간보호" in r.json()["detail"]


def test_list_totals_visibility_and_delete_rules(env):
    db, client = env
    client.post("/api/v1/day-care", json=body(transport="both", distance_km=25), headers=CG)
    client.post("/api/v1/day-care", json=body(resident_id=2, arrive_time="09:00", leave_time="15:00", caregiver_id=3), headers=MGR)
    mgr = client.get(f"/api/v1/day-care?year_month={MONTH}", headers=MGR).json()
    assert [i["resident"] for i in mgr["items"]] == ["김일", "이이"] or {i["resident"] for i in mgr["items"]} == {"김일", "이이"}
    assert mgr["totals"]["days"] == 2 and mgr["totals"]["extra"] == 8630
    mine = client.get(f"/api/v1/day-care?year_month={MONTH}", headers=CG).json()
    assert [i["resident"] for i in mine["items"]] == ["김일"]  # 요양보호사는 자기가 기록한 것만
    assert client.get("/api/v1/day-care?year_month=2026-13", headers=MGR).status_code == 400
    # 삭제: 본인 것만(요양보호사), 승인 전 청구만
    other_id = next(i["id"] for i in mgr["items"] if i["resident"] == "이이")
    assert client.delete(f"/api/v1/day-care/{other_id}", headers=CG).status_code == 403
    mine_id = mine["items"][0]["id"]
    bill = db.query(models.BillingRecord).filter_by(resident_id=1).one()
    bill.approval_status = "approved"
    db.commit()
    assert client.delete(f"/api/v1/day-care/{mine_id}", headers=CG).status_code == 400
    bill = db.query(models.BillingRecord).filter_by(resident_id=1).one()
    bill.approval_status = "draft"
    db.commit()
    assert client.delete(f"/api/v1/day-care/{mine_id}", headers=CG).status_code == 200
    assert db.query(models.DayCareAttendance).count() == 1 and db.query(models.BillingRecord).count() == 1


def test_review_flags_do_not_mark_day_care_bills_as_out_of_plan(env):
    db, client = env
    client.post("/api/v1/day-care", json=body(), headers=CG)
    bill = db.query(models.BillingRecord).one()
    assert review_flags(db, bill) == []
