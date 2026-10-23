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
    engine = create_engine(f"sqlite:///{tmp_path / 'memo.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.Center(id=1, name="센터A"))
    db.add(models.User(id=1, email="manager@example.com", hashed_password="x", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="caregiver@example.com", hashed_password="x", full_name="요양사", role="caregiver", center_id=1))
    db.add(models.Resident(id=1, center_id=1, name="김1", age=80, health_status="stable", care_grade=1, client_type="일반",
                           recognition_start=None, recognition_end=None))
    db.add(models.Schedule(id=1, caregiver_id=2, resident_id=1, center_id=1, scheduled_date=datetime(2026, 10, 24, 9, 0),
                           duration_minutes=60, status="proposed", service_type="basic_care"))
    db.add(models.Schedule(id=2, caregiver_id=2, resident_id=1, center_id=1, scheduled_date=datetime(2026, 10, 25, 9, 0),
                           duration_minutes=60, status="scheduled", service_type="basic_care"))
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


def memo_body(memo):
    return {"user_id": 1, "user_role": "center_manager", "memo": memo}


def test_manager_saves_memo_and_status_stays_proposed(client):
    response = client.post("/api/v1/schedule/1/review-memo", json=memo_body("  시간대 확인 필요  "), headers=MANAGER)
    assert response.status_code == 200
    assert response.json()["schedule_status"] == "proposed"

    items = client.get("/api/v1/schedule/proposals?center_id=1", headers=MANAGER).json()["items"]
    plan = next(i for i in items if i["schedule_id"] == 1)
    assert plan["status"] == "proposed"
    assert plan["review_memo"] == "시간대 확인 필요"


def test_blank_memo_clears_it(client):
    client.post("/api/v1/schedule/1/review-memo", json=memo_body("메모"), headers=MANAGER)
    client.post("/api/v1/schedule/1/review-memo", json=memo_body("   "), headers=MANAGER)
    items = client.get("/api/v1/schedule/proposals?center_id=1", headers=MANAGER).json()["items"]
    assert next(i for i in items if i["schedule_id"] == 1)["review_memo"] is None


def test_caregiver_cannot_save_memo(client):
    assert client.post("/api/v1/schedule/1/review-memo", json=memo_body("메모"), headers=CAREGIVER).status_code == 403


def test_memo_only_for_pending_plans(client):
    assert client.post("/api/v1/schedule/2/review-memo", json=memo_body("메모"), headers=MANAGER).status_code == 400


def test_approve_still_works_after_memo(client):
    client.post("/api/v1/schedule/1/review-memo", json=memo_body("확인 완료"), headers=MANAGER)
    response = client.post("/api/v1/schedule/1/approve", json={"user_id": 1, "user_role": "center_manager", "reason": ""}, headers=MANAGER)
    assert response.status_code == 200
    assert response.json()["schedule_status"] == "scheduled"
