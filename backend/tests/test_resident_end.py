from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import residents, schedule
from app.api.users import create_access_token
from app.database import Base, get_db

ENDED = date(2026, 12, 1)
BEFORE = datetime(2026, 11, 30, 10, 0)
AFTER = datetime(2026, 12, 2, 10, 0)


@pytest.fixture
def ctx(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'end.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="센터A"), models.Center(id=2, name="센터B"),
        models.User(id=1, email="m@e.com", hashed_password="x", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@e.com", hashed_password="x", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=4, email="m2@e.com", hashed_password="x", full_name="타센터장", role="center_manager", center_id=2),
        models.Resident(id=1, center_id=1, name="김1", age=80, health_status="stable", care_grade=1, client_type="일반"),
        models.Schedule(id=1, caregiver_id=2, resident_id=1, center_id=1, scheduled_date=BEFORE, duration_minutes=60, status="scheduled"),
    ])
    db.commit()
    db.close()
    app = FastAPI()
    app.include_router(residents.router, prefix="/api/v1/residents")
    app.include_router(schedule.router, prefix="/api/v1/schedule")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app), Session


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MGR = auth(1, "center_manager", "m@e.com")
CG = auth(2, "caregiver", "c@e.com")
OTHER_MGR = auth(4, "center_manager", "m2@e.com")


def end(client, headers=MGR, reason="퇴소", ended_on=ENDED.isoformat()):
    return client.post("/api/v1/residents/1/end", json={"ended_on": ended_on, "reason": reason}, headers=headers)


def new_schedule(client, when):
    return client.post("/api/v1/schedule/", json={
        "caregiver_id": 2, "resident_id": 1, "center_id": 1, "scheduled_date": when.isoformat(),
        "duration_minutes": 60, "service_type": "basic_care", "benefit_type": "home_care",
    }, headers=MGR)


def test_end_records_date_and_reason_and_keeps_existing_schedule(ctx):
    client, Session = ctx
    r = end(client)
    assert r.status_code == 200
    assert r.json()["data"] == {"id": 1, "ended_on": "2026-12-01", "end_reason": "퇴소"}
    db = Session()
    assert db.get(models.Resident, 1).ended_on == ENDED
    assert db.get(models.Schedule, 1) is not None
    db.close()


def test_end_twice_is_rejected(ctx):
    client, _ = ctx
    assert end(client).status_code == 200
    assert end(client).status_code == 409


def test_end_rejects_unknown_reason(ctx):
    client, _ = ctx
    assert end(client, reason="이사").status_code == 400


def test_caregiver_and_other_center_cannot_end(ctx):
    client, _ = ctx
    assert end(client, headers=CG).status_code == 403
    assert end(client, headers=OTHER_MGR).status_code in (403, 404)


def test_new_schedule_after_end_date_is_blocked_but_on_or_before_is_allowed(ctx):
    client, _ = ctx
    end(client)
    assert new_schedule(client, AFTER).status_code == 409
    assert new_schedule(client, datetime(2026, 12, 1, 9, 0)).status_code == 200


def test_recurring_schedule_stops_at_end_date(ctx):
    client, Session = ctx
    end(client)
    r = client.post("/api/v1/schedule/recurring", json={
        "caregiver_id": 2, "resident_id": 1, "start_date": "2026-12-01", "end_date": "2026-12-31",
        "weekdays": [0, 1, 2, 3, 4, 5, 6], "start_time": "09:00", "duration_minutes": 60,
        "service_type": "basic_care", "benefit_type": "home_care",
    }, headers=MGR)
    assert r.status_code == 200
    db = Session()
    dates = {s.scheduled_date.date() for s in db.query(models.Schedule).filter(models.Schedule.resident_id == 1).all()}
    db.close()
    assert max(dates) == ENDED


def test_recurring_starting_after_end_is_blocked(ctx):
    client, _ = ctx
    end(client)
    r = client.post("/api/v1/schedule/recurring", json={
        "caregiver_id": 2, "resident_id": 1, "start_date": "2026-12-05", "end_date": "2026-12-31",
        "weekdays": [0], "start_time": "09:00", "duration_minutes": 60,
        "service_type": "basic_care", "benefit_type": "home_care",
    }, headers=MGR)
    assert r.status_code == 409


def test_reopen_clears_end_and_allows_schedule_again(ctx):
    client, _ = ctx
    end(client)
    assert client.post("/api/v1/residents/1/reopen", headers=MGR).status_code == 200
    assert new_schedule(client, AFTER).status_code == 200


def test_reopen_active_resident_is_rejected(ctx):
    client, _ = ctx
    assert client.post("/api/v1/residents/1/reopen", headers=MGR).status_code == 409


def test_resident_list_shows_end_info(ctx):
    client, _ = ctx
    end(client, reason="사망")
    item = client.get("/api/v1/residents/", headers=MGR).json()["residents"][0]
    assert item["ended_on"] == "2026-12-01"
    assert item["end_reason"] == "사망"
