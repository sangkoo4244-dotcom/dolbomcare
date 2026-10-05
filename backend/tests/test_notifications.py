from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import billing, notifications, resident_changes, schedule
from app.api.users import create_access_token
from app.database import Base, get_db


@pytest.fixture
def setup(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.Center(id=1, name="테스트센터"))
    db.add(models.User(id=1, email="manager@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="caregiver1@test.com", full_name="요양사1", role="caregiver", center_id=1))
    db.add(models.User(id=3, email="caregiver2@test.com", full_name="요양사2", role="caregiver", center_id=1))
    db.add(models.Resident(id=1, center_id=1, name="김1", age=80, health_status="stable", care_grade=1, client_type="일반"))
    db.add(models.Schedule(
        id=1, caregiver_id=2, resident_id=1, center_id=1, service_type="basic_care",
        scheduled_date=datetime(2026, 10, 7, 9), duration_minutes=60, status="proposed",
    ))
    db.add(models.ResidentChangeRequest(
        id=1, resident_id=1, center_id=1, requested_by=2, field="name", new_value="김철수", status="pending",
    ))
    db.add(models.BillingRecord(
        id=1, caregiver_id=2, resident_id=1, center_id=1, service_type="basic_care",
        amount=100, approval_status="pending", year_month="2026-10", recorded_date=datetime(2026, 10, 5),
    ))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(schedule.router, prefix="/api/v1/schedule")
    app.include_router(resident_changes.router, prefix="/api/v1/residents")
    app.include_router(billing.router, prefix="/api/v1/billing")
    app.include_router(notifications.router, prefix="/api/v1/notifications")

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def token_for(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


CAREGIVER1 = token_for(2, "caregiver", "caregiver1@test.com")
CAREGIVER2 = token_for(3, "caregiver", "caregiver2@test.com")
MANAGER = token_for(1, "center_manager", "manager@test.com")


def test_caregiver_is_notified_when_plan_is_rejected(setup):
    setup.post("/api/v1/schedule/1/reject", json={"reason": "방문 시간 조정 필요", "user_id": 1, "user_role": "center_manager"}, headers=MANAGER)
    body = setup.get("/api/v1/notifications/mine", headers=CAREGIVER1).json()
    assert body["unread_count"] == 1
    assert "방문 시간 조정 필요" in body["notifications"][0]["message"]


def test_caregiver_is_notified_when_change_request_is_approved_or_rejected(setup):
    setup.post("/api/v1/residents/change-requests/1/approve", headers=MANAGER)
    body = setup.get("/api/v1/notifications/mine", headers=CAREGIVER1).json()
    assert body["unread_count"] == 1
    assert "승인" in body["notifications"][0]["message"]


def test_change_request_rejection_includes_reason(setup):
    setup.post("/api/v1/residents/change-requests/1/reject", json={"reason": "근거 부족"}, headers=MANAGER)
    body = setup.get("/api/v1/notifications/mine", headers=CAREGIVER1).json()
    assert "근거 부족" in body["notifications"][0]["message"]


def test_caregiver_only_sees_own_notifications(setup):
    setup.post("/api/v1/schedule/1/reject", json={"reason": "조정", "user_id": 1, "user_role": "center_manager"}, headers=MANAGER)
    body = setup.get("/api/v1/notifications/mine", headers=CAREGIVER2).json()
    assert body["unread_count"] == 0
    assert body["notifications"] == []


def test_marking_read_reduces_unread_count(setup):
    setup.post("/api/v1/schedule/1/reject", json={"reason": "조정", "user_id": 1, "user_role": "center_manager"}, headers=MANAGER)
    notification_id = setup.get("/api/v1/notifications/mine", headers=CAREGIVER1).json()["notifications"][0]["id"]
    assert setup.post(f"/api/v1/notifications/{notification_id}/read", headers=CAREGIVER1).status_code == 200
    assert setup.get("/api/v1/notifications/mine", headers=CAREGIVER1).json()["unread_count"] == 0


def test_caregiver_cannot_mark_another_users_notification(setup):
    setup.post("/api/v1/schedule/1/reject", json={"reason": "조정", "user_id": 1, "user_role": "center_manager"}, headers=MANAGER)
    notification_id = setup.get("/api/v1/notifications/mine", headers=CAREGIVER1).json()["notifications"][0]["id"]
    assert setup.post(f"/api/v1/notifications/{notification_id}/read", headers=CAREGIVER2).status_code == 404


def test_read_all_clears_unread(setup):
    setup.post("/api/v1/schedule/1/reject", json={"reason": "조정", "user_id": 1, "user_role": "center_manager"}, headers=MANAGER)
    setup.post("/api/v1/residents/change-requests/1/approve", headers=MANAGER)
    assert setup.post("/api/v1/notifications/read-all", headers=CAREGIVER1).status_code == 200
    assert setup.get("/api/v1/notifications/mine", headers=CAREGIVER1).json()["unread_count"] == 0


def test_caregiver_is_notified_when_claim_is_rejected(setup):
    setup.post(
        "/api/v1/billing/1/reject",
        json={"reason": "방문 기록 시간이 맞지 않습니다", "user_id": 1, "user_role": "center_manager"},
        headers=MANAGER,
    )
    body = setup.get("/api/v1/notifications/mine", headers=CAREGIVER1).json()
    assert body["unread_count"] == 1
    assert "방문 기록 시간이 맞지 않습니다" in body["notifications"][0]["message"]
    assert body["notifications"][0]["kind"] == "claim_rejected"


def test_caregiver_is_notified_when_plan_is_approved(setup):
    setup.post("/api/v1/schedule/1/approve", json={"user_id": 1, "user_role": "center_manager"}, headers=MANAGER)
    body = setup.get("/api/v1/notifications/mine", headers=CAREGIVER1).json()
    assert body["unread_count"] == 1
    assert body["notifications"][0]["kind"] == "plan_approved"


def test_caregiver_is_notified_when_claim_is_approved(setup):
    setup.post("/api/v1/billing/1/approve", json={"user_id": 1, "user_role": "center_manager"}, headers=MANAGER)
    body = setup.get("/api/v1/notifications/mine", headers=CAREGIVER1).json()
    assert body["unread_count"] == 1
    assert body["notifications"][0]["kind"] == "claim_approved"
