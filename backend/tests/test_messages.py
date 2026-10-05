from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import messages, notifications
from app.api.users import create_access_token
from app.database import Base, get_db


@pytest.fixture
def setup(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.Center(id=1, name="센터A"))
    db.add(models.Center(id=2, name="센터B"))
    db.add(models.User(id=1, email="manager@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="caregiver1@test.com", full_name="요양사1", role="caregiver", center_id=1))
    db.add(models.User(id=3, email="guardian@test.com", full_name="보호자", role="guardian", center_id=1))
    db.add(models.User(id=4, email="outsider@test.com", full_name="타센터 보호자", role="guardian", center_id=2))
    db.add(models.User(id=5, email="other-manager@test.com", full_name="타센터장", role="center_manager", center_id=2))
    db.add(models.Resident(id=1, center_id=1, name="김1", age=80, health_status="stable", care_grade=1,
                           client_type="일반", guardian_id=3))
    db.add(models.DailyRecord(id=1, caregiver_id=2, resident_id=1, recorded_date=datetime(2026, 10, 5, 9), duration_minutes=60))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(messages.router, prefix="/api/v1/messages")
    app.include_router(notifications.router, prefix="/api/v1/notifications")

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.Session = Session
    return client


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


GUARDIAN = auth(3, "guardian", "guardian@test.com")
CAREGIVER = auth(2, "caregiver", "caregiver1@test.com")
MANAGER = auth(1, "center_manager", "manager@test.com")
OUTSIDER = auth(4, "guardian", "outsider@test.com")
OTHER_MANAGER = auth(5, "center_manager", "other-manager@test.com")


def send(client, body, headers):
    return client.post("/api/v1/messages/residents/1", json={"body": body}, headers=headers)


def test_guardian_message_is_visible_to_caregiver_and_manager(setup):
    assert send(setup, "식사는 잘 드셨나요?", GUARDIAN).status_code == 200
    for headers in (CAREGIVER, MANAGER):
        body = setup.get("/api/v1/messages/residents/1", headers=headers).json()
        assert body["messages"][0]["body"] == "식사는 잘 드셨나요?"
        assert body["messages"][0]["sender_role"] == "guardian"


def test_caregiver_reply_is_visible_to_guardian_and_notifies_them(setup):
    send(setup, "오늘 상태가 어떤가요?", GUARDIAN)
    assert send(setup, "네, 편안하게 지내셨습니다.", CAREGIVER).status_code == 200
    body = setup.get("/api/v1/messages/residents/1", headers=GUARDIAN).json()
    assert [m["sender_role"] for m in body["messages"]] == ["guardian", "caregiver"]
    unread = setup.get("/api/v1/notifications/mine", headers=GUARDIAN).json()
    assert unread["unread_count"] == 1
    assert unread["notifications"][0]["kind"] == "message_received"


def test_unlinked_guardian_and_other_center_cannot_read_or_post(setup):
    assert setup.get("/api/v1/messages/residents/1", headers=OUTSIDER).status_code == 403
    assert send(setup, "몰래 보냅니다", OUTSIDER).status_code == 403
    assert setup.get("/api/v1/messages/residents/1", headers=OTHER_MANAGER).status_code == 403


def test_empty_message_is_rejected(setup):
    assert send(setup, "   ", GUARDIAN).status_code == 400


def test_only_manager_can_delete_and_deleted_message_disappears(setup):
    send(setup, "잘못 보낸 메시지", GUARDIAN)
    message_id = setup.get("/api/v1/messages/residents/1", headers=GUARDIAN).json()["messages"][0]["id"]
    assert setup.delete(f"/api/v1/messages/{message_id}", headers=CAREGIVER).status_code == 403
    assert setup.delete(f"/api/v1/messages/{message_id}", headers=GUARDIAN).status_code == 403
    assert setup.delete(f"/api/v1/messages/{message_id}", headers=MANAGER).status_code == 200
    assert setup.get("/api/v1/messages/residents/1", headers=CAREGIVER).json()["messages"] == []


def test_deleted_message_row_is_kept_for_audit(setup):
    send(setup, "보관 확인", GUARDIAN)
    message_id = setup.get("/api/v1/messages/residents/1", headers=MANAGER).json()["messages"][0]["id"]
    setup.delete(f"/api/v1/messages/{message_id}", headers=MANAGER)
    db = setup.Session()
    row = db.query(models.ResidentMessage).filter(models.ResidentMessage.id == message_id).first()
    assert row is not None and row.is_deleted is True
    db.close()
