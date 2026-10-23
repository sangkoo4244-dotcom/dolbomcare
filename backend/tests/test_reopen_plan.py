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


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'reopen.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.Center(id=1, name="센터A"))
    db.add(models.User(id=1, email="manager@example.com", hashed_password="x", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="caregiver@example.com", hashed_password="x", full_name="요양사", role="caregiver", center_id=1))
    db.add(models.Resident(id=1, center_id=1, name="김1", age=80, health_status="stable", care_grade=1, client_type="일반",
                           recognition_start=None, recognition_end=None))
    plans = [
        dict(id=1, status="rejected", review_note="시간 조정", day=24),
        dict(id=2, status="scheduled", day=25),
        dict(id=3, status="scheduled", day=26, arrived_at=datetime(2026, 10, 26, 9, 2)),
        dict(id=4, status="proposed", day=27),
        dict(id=5, status="scheduled", day=28),
    ]
    for p in plans:
        db.add(models.Schedule(id=p["id"], caregiver_id=2, resident_id=1, center_id=1,
                               scheduled_date=datetime(2026, 10, p["day"], 9, 0), duration_minutes=60,
                               status=p["status"], service_type="basic_care",
                               review_note=p.get("review_note"), arrived_at=p.get("arrived_at")))
    db.add(models.DailyRecord(id=1, resident_id=1, caregiver_id=2, recorded_date=datetime(2026, 10, 28, 10, 0), schedule_id=5))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(schedule.router, prefix="/api/v1/schedule")

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MANAGER = auth(1, "center_manager", "manager@example.com")
CAREGIVER = auth(2, "caregiver", "caregiver@example.com")
BODY = {"user_id": 1, "user_role": "center_manager", "reason": ""}


def status_of(client, schedule_id):
    items = client.get("/api/v1/schedule/proposals?center_id=1", headers=MANAGER).json()["items"]
    found = [i for i in items if i["schedule_id"] == schedule_id]
    return found[0]["status"] if found else None


def test_rejected_plan_returns_to_pending(client):
    response = client.post("/api/v1/schedule/1/reopen", json=BODY, headers=MANAGER)
    assert response.status_code == 200
    assert response.json()["schedule_status"] == "proposed"
    assert status_of(client, 1) == "proposed"


def test_approved_plan_without_visit_returns_to_pending(client):
    response = client.post("/api/v1/schedule/2/reopen", json=BODY, headers=MANAGER)
    assert response.status_code == 200
    assert response.json()["schedule_status"] == "proposed"


def test_approved_plan_with_arrival_cannot_be_reopened(client):
    response = client.post("/api/v1/schedule/3/reopen", json=BODY, headers=MANAGER)
    assert response.status_code == 400
    assert status_of(client, 3) is None  # 승인 대기 목록에는 나타나지 않는다 (상태 유지)


def test_approved_plan_with_record_cannot_be_reopened(client):
    response = client.post("/api/v1/schedule/5/reopen", json=BODY, headers=MANAGER)
    assert response.status_code == 400


def test_pending_plan_cannot_be_reopened(client):
    response = client.post("/api/v1/schedule/4/reopen", json=BODY, headers=MANAGER)
    assert response.status_code == 400


def test_caregiver_cannot_reopen(client):
    response = client.post("/api/v1/schedule/1/reopen", json=BODY, headers=CAREGIVER)
    assert response.status_code == 403
