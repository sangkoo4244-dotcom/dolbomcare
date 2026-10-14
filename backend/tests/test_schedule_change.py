from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import schedule
from app.api.users import create_access_token
from app.database import Base, get_db

WHEN = datetime.now().replace(microsecond=0) + timedelta(days=2)


@pytest.fixture
def ctx(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'sc.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="센터A"), models.Center(id=2, name="센터B"),
        models.User(id=1, email="m@e.com", hashed_password="x", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@e.com", hashed_password="x", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=3, email="c2@e.com", hashed_password="x", full_name="다른요양사", role="caregiver", center_id=1),
        models.User(id=4, email="m2@e.com", hashed_password="x", full_name="타센터장", role="center_manager", center_id=2),
        models.Resident(id=1, center_id=1, name="김1", age=80, health_status="stable", care_grade=1, client_type="일반"),
        models.Schedule(id=1, caregiver_id=2, resident_id=1, center_id=1, scheduled_date=WHEN, duration_minutes=60, status="scheduled"),
    ])
    db.commit()
    db.close()
    app = FastAPI()
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
NEW = (WHEN + timedelta(hours=3)).isoformat()


def request_change(client, headers=CG, reason="병원 진료"):
    return client.post("/api/v1/schedule/1/change-request", json={"scheduled_date": NEW, "reason": reason}, headers=headers)


def test_original_stays_until_approved_then_moves(ctx):
    client, Session = ctx
    assert request_change(client).status_code == 200
    db = Session()
    s = db.query(models.Schedule).get(1)
    assert s.scheduled_date == WHEN and s.change_date is not None
    assert db.query(models.Notification).filter_by(user_id=1, kind="schedule_change_requested").count() == 1
    assert len(client.get("/api/v1/schedule/change-requests", headers=MGR).json()["items"]) == 1
    assert client.post("/api/v1/schedule/1/change-approve", headers=MGR).status_code == 200
    db.expire_all()
    s = db.query(models.Schedule).get(1)
    assert s.scheduled_date == datetime.fromisoformat(NEW) and s.change_date is None
    assert db.query(models.Notification).filter_by(user_id=2, kind="schedule_change_approved").count() == 1


def test_reject_needs_reason_and_keeps_original(ctx):
    client, Session = ctx
    request_change(client)
    assert client.post("/api/v1/schedule/1/change-reject", json={"user_id": 1, "user_role": "center_manager", "reason": ""}, headers=MGR).status_code == 400
    assert client.post("/api/v1/schedule/1/change-reject", json={"user_id": 1, "user_role": "center_manager", "reason": "그날은 어렵습니다"}, headers=MGR).status_code == 200
    s = Session().query(models.Schedule).get(1)
    assert s.scheduled_date == WHEN and s.change_date is None


def test_reason_required_and_only_owner(ctx):
    client, _ = ctx
    assert request_change(client, reason="  ").status_code == 400
    assert request_change(client, headers=auth(3, "caregiver", "c2@e.com")).status_code == 403
    assert request_change(client, headers=MGR).status_code == 403


def test_cannot_change_after_arrival(ctx):
    client, Session = ctx
    db = Session()
    db.query(models.Schedule).get(1).arrived_at = datetime.now()
    db.commit()
    assert request_change(client).status_code == 400


def test_other_center_manager_cannot_decide(ctx):
    client, _ = ctx
    request_change(client)
    assert client.post("/api/v1/schedule/1/change-approve", headers=auth(4, "center_manager", "m2@e.com")).status_code == 404


def test_caregiver_can_withdraw(ctx):
    client, Session = ctx
    request_change(client)
    assert client.post("/api/v1/schedule/1/change-cancel", headers=CG).status_code == 200
    assert Session().query(models.Schedule).get(1).change_date is None


def test_service_and_items_change_applies_only_on_approval(ctx):
    client, Session = ctx
    db = Session()
    s = db.query(models.Schedule).get(1)
    s.service_type, s.planned_items = "basic_care", "meal_assist"
    db.commit()
    body = {"scheduled_date": WHEN.isoformat(), "service_type": "medical_care", "planned_items": "meal_assist,bath", "reason": "상태 변화"}
    assert client.post("/api/v1/schedule/1/change-request", json=body, headers=CG).status_code == 200
    db.expire_all()
    s = db.query(models.Schedule).get(1)
    assert (s.service_type, s.planned_items) == ("basic_care", "meal_assist")  # 승인 전에는 그대로
    item = client.get("/api/v1/schedule/change-requests", headers=MGR).json()["items"][0]
    assert item["to_service_type"] == "medical_care" and item["to_items"] == ["meal_assist", "bath"]
    assert client.post("/api/v1/schedule/1/change-approve", headers=MGR).status_code == 200
    db.expire_all()
    s = db.query(models.Schedule).get(1)
    assert (s.service_type, s.planned_items, s.scheduled_date) == ("medical_care", "meal_assist,bath", WHEN)
    assert s.change_service_type is None and s.change_planned_items is None


def test_request_identical_to_current_is_rejected(ctx):
    client, Session = ctx
    s = Session().query(models.Schedule).get(1)
    body = {"scheduled_date": WHEN.isoformat(), "service_type": s.service_type, "reason": "그냥"}
    assert client.post("/api/v1/schedule/1/change-request", json=body, headers=CG).status_code == 400
