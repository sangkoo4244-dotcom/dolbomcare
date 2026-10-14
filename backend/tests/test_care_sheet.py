from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import care_sheet, records
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@test.com")
CG_A = auth(2, "caregiver", "a@test.com")
CG_B = auth(3, "caregiver", "b@test.com")
OTHER_MANAGER = auth(5, "center_manager", "o@test.com")
GUARDIAN = auth(9, "guardian", "g@test.com")

WEEK = date(2026, 10, 12)  # 월요일


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="센터", institution_code="12345678901"), models.Center(id=2, name="다른센터"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="a@test.com", full_name="요양사A", role="caregiver", center_id=1),
        models.User(id=3, email="b@test.com", full_name="요양사B", role="caregiver", center_id=1),
        models.User(id=5, email="o@test.com", full_name="타센터장", role="center_manager", center_id=2),
        models.User(id=9, email="g@test.com", full_name="보호자", role="guardian", center_id=1),
        models.Resident(id=1, center_id=1, name="김이용", care_grade=3, recognition_number="L1234567890",
                        birth_date=date(1940, 3, 2)),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(records.router, prefix="/api/v1/records")
    app.include_router(care_sheet.router, prefix="/api/v1/care-sheet")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def add_record(db, caregiver_id, day, **kw):
    base = dict(resident_id=1, caregiver_id=caregiver_id, recorded_date=datetime(2026, 10, 12 + day, 10, 0),
                care_items="meal_assist,bath", duration_minutes=60, notes="양호")
    base.update(kw)
    db.add(models.DailyRecord(**base))
    db.commit()


def get_sheet(client, headers, **kw):
    params = {"resident_id": 1, "week_start": WEEK.isoformat()}
    params.update(kw)
    return client.get("/api/v1/care-sheet", params=params, headers=headers)


def test_week_has_seven_days_and_marks_visited(env):
    db, client = env
    add_record(db, 2, 0, physical_change="maintained", meal_change="improved", cognitive_change="worsened",
               stool_accidents=1, urine_accidents=2)
    data = get_sheet(client, MANAGER).json()
    assert [d["date"] for d in data["days"]][0] == "2026-10-12" and len(data["days"]) == 7
    monday, tuesday = data["days"][0], data["days"][1]
    assert monday["visited"] and not tuesday["visited"]
    assert monday["care_items"] == ["meal_assist", "bath"]
    assert (monday["physical_change"], monday["meal_change"], monday["cognitive_change"]) == ("maintained", "improved", "worsened")
    assert (monday["stool_accidents"], monday["urine_accidents"]) == (1, 2)
    assert data["resident"]["recognition_number"] == "L1234567890"
    assert data["center"]["institution_code"] == "12345678901"


def test_two_visits_same_day_merge_items_and_add_minutes(env):
    db, client = env
    add_record(db, 2, 0, care_items="meal_assist", duration_minutes=60, stool_accidents=1)
    add_record(db, 3, 0, care_items="meal_assist,laundry", duration_minutes=30, stool_accidents=2,
               recorded_date=datetime(2026, 10, 12, 15, 0))
    monday = get_sheet(client, MANAGER).json()["days"][0]
    assert monday["care_items"] == ["meal_assist", "laundry"]
    assert monday["total_minutes"] == 90
    assert monday["stool_accidents"] == 3
    assert monday["caregivers"] == ["요양사A", "요양사B"]


def test_caregiver_sees_only_own_records(env):
    db, client = env
    add_record(db, 2, 0)
    add_record(db, 3, 1)
    days = get_sheet(client, CG_A).json()["days"]
    assert days[0]["visited"] and not days[1]["visited"]


def test_other_center_and_guardian_are_blocked(env):
    db, client = env
    add_record(db, 2, 0)
    assert get_sheet(client, OTHER_MANAGER).status_code == 404
    assert get_sheet(client, GUARDIAN).status_code == 403


def test_records_outside_week_are_excluded(env):
    db, client = env
    add_record(db, 2, 7)  # 다음 주 월요일
    assert not any(d["visited"] for d in get_sheet(client, MANAGER).json()["days"])


def test_create_record_saves_change_status_and_rejects_bad_values(env):
    db, client = env
    payload = {"caregiver_id": 2, "resident_id": 1, "service_type": "basic_care", "notes": "양호",
               "physical_change": "improved", "meal_change": "maintained", "cognitive_change": "worsened",
               "stool_accidents": 0, "urine_accidents": 3}
    assert client.post("/api/v1/records/create", json=payload, headers=CG_A).status_code == 200
    rec = db.query(models.DailyRecord).one()
    assert (rec.physical_change, rec.meal_change, rec.cognitive_change) == ("improved", "maintained", "worsened")
    assert (rec.stool_accidents, rec.urine_accidents) == (0, 3)

    bad = dict(payload, physical_change="great")
    assert client.post("/api/v1/records/create", json=bad, headers=CG_A).status_code == 422
    bad = dict(payload, urine_accidents=-1)
    assert client.post("/api/v1/records/create", json=bad, headers=CG_A).status_code == 422


def manager_payload(caregiver_id):
    return {"caregiver_id": caregiver_id, "resident_id": 1, "service_type": "basic_care", "notes": "센터장 대신 입력"}


def test_manager_records_for_a_center_caregiver(env):
    db, client = env
    assert client.post("/api/v1/records/create", json=manager_payload(2), headers=MANAGER).status_code == 200
    assert db.query(models.DailyRecord).one().caregiver_id == 2


def test_manager_cannot_record_under_own_or_other_center_name(env):
    db, client = env
    db.add(models.User(id=6, email="x@test.com", full_name="타센터요양사", role="caregiver", center_id=2))
    db.commit()
    assert client.post("/api/v1/records/create", json=manager_payload(1), headers=MANAGER).status_code == 400  # 센터장 본인
    assert client.post("/api/v1/records/create", json=manager_payload(6), headers=MANAGER).status_code == 400  # 다른 센터 직원
    assert client.post("/api/v1/records/create", json=manager_payload(2), headers=OTHER_MANAGER).status_code == 400  # 다른 센터 센터장
    assert db.query(models.DailyRecord).count() == 0


def test_saving_a_record_marks_its_record_needed_reminder_as_read(env):
    db, client = env
    db.add_all([
        models.Notification(user_id=2, kind="record_needed", message="김이용 방문 기록을 작성해 주세요"),
        models.Notification(user_id=2, kind="record_needed", message="다른이용자 방문 기록을 작성해 주세요"),
    ])
    db.commit()
    payload = {"caregiver_id": 2, "resident_id": 1, "service_type": "basic_care", "notes": "양호"}
    assert client.post("/api/v1/records/create", json=payload, headers=CG_A).status_code == 200
    read = {n.message: n.is_read for n in db.query(models.Notification).all()}
    assert read["김이용 방문 기록을 작성해 주세요"] is True
    assert read["다른이용자 방문 기록을 작성해 주세요"] is False


def test_prefill_returns_todays_plan_and_last_visit(env):
    db, client = env
    now = datetime.now()
    db.add(models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=now, duration_minutes=90,
                           planned_items="meal_assist,bath", service_type="basic_care", status="scheduled"))
    add_record(db, 2, -5, care_items="mobility,emotional", duration_minutes=60, condition="normal",
               physical_change="maintained", meal_change="improved", cognitive_change="worsened")
    db.commit()
    data = client.get("/api/v1/records/prefill?resident_id=1", headers=CG_A).json()
    assert data["planned"]["items"] == ["meal_assist", "bath"] and data["planned"]["duration_minutes"] == 90
    assert data["last"]["items"] == ["mobility", "emotional"]
    assert (data["last"]["physical_change"], data["last"]["meal_change"], data["last"]["cognitive_change"]) == ("maintained", "improved", "worsened")
    assert data["last"]["condition"] == "normal"


def test_prefill_without_history_is_empty_and_blocks_other_center(env):
    db, client = env
    data = client.get("/api/v1/records/prefill?resident_id=1", headers=CG_A).json()
    assert data == {"planned": None, "last": None}
    assert client.get("/api/v1/records/prefill?resident_id=1", headers=OTHER_MANAGER).status_code == 404
    assert client.get("/api/v1/records/prefill?resident_id=1", headers=GUARDIAN).status_code == 403


def test_prefill_for_new_caregiver_uses_previous_caregivers_last_visit(env):
    db, client = env
    add_record(db, 3, -2, care_items="bath", condition="good")  # 이전 담당(B)의 기록
    data = client.get("/api/v1/records/prefill?resident_id=1", headers=CG_A).json()
    assert data["last"]["items"] == ["bath"]
