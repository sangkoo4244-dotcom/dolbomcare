from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import users
from app.api.users import get_password_hash
from app.database import Base, get_db


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    db = Session()
    db.add(models.Center(id=1, name="테스트센터"))
    db.add(models.User(
        id=1, email="caregiver1@test.com", hashed_password=get_password_hash("oldpassword1"),
        full_name="요양사1", role="caregiver", center_id=1,
    ))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(users.router, prefix="/api/v1/users")

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    test_client.Session = Session
    return test_client


def test_forgot_password_gives_same_message_for_known_and_unknown_email(client, monkeypatch):
    """계정 존재 여부가 응답으로 새어나가면 안 된다 - 메시지가 똑같아야 한다."""
    monkeypatch.setattr(users, "send_email", lambda **kwargs: False)
    known = client.post("/api/v1/users/forgot-password", json={"email": "caregiver1@test.com"})
    unknown = client.post("/api/v1/users/forgot-password", json={"email": "nobody@test.com"})
    assert known.status_code == 200
    assert unknown.status_code == 200
    assert known.json()["message"] == unknown.json()["message"]


def test_forgot_password_sends_email_with_token_link(client, monkeypatch):
    sent = {}

    def fake_send_email(to, subject, body):
        sent["to"] = to
        sent["body"] = body
        return True

    monkeypatch.setattr(users, "send_email", fake_send_email)
    res = client.post("/api/v1/users/forgot-password", json={"email": "caregiver1@test.com"})
    assert res.status_code == 200
    assert sent["to"] == "caregiver1@test.com"
    assert "reset_password.html?token=" in sent["body"]


def test_forgot_password_does_not_send_email_for_unknown_address(client, monkeypatch):
    called = {"count": 0}

    def fake_send_email(**kwargs):
        called["count"] += 1
        return True

    monkeypatch.setattr(users, "send_email", fake_send_email)
    client.post("/api/v1/users/forgot-password", json={"email": "nobody@test.com"})
    assert called["count"] == 0


def _request_token(client, monkeypatch, email):
    captured = {}

    def fake_send_email(to, subject, body):
        captured["token"] = body.split("token=")[1].split("\n")[0]
        return True

    monkeypatch.setattr(users, "send_email", fake_send_email)
    client.post("/api/v1/users/forgot-password", json={"email": email})
    return captured["token"]


def test_reset_password_with_valid_token_works(client, monkeypatch):
    token = _request_token(client, monkeypatch, "caregiver1@test.com")

    res = client.post("/api/v1/users/reset-password", json={"token": token, "new_password": "newpassword2"})
    assert res.status_code == 200

    old_login = client.post("/api/v1/users/login", json={"email": "caregiver1@test.com", "password": "oldpassword1"})
    assert old_login.status_code == 401

    new_login = client.post("/api/v1/users/login", json={"email": "caregiver1@test.com", "password": "newpassword2"})
    assert new_login.status_code == 200


def test_reset_password_rejects_unknown_token(client):
    res = client.post("/api/v1/users/reset-password", json={"token": "not-a-real-token", "new_password": "newpassword2"})
    assert res.status_code == 400


def test_reset_password_rejects_expired_token(client, monkeypatch):
    token = _request_token(client, monkeypatch, "caregiver1@test.com")

    session = client.Session()
    reset_row = session.query(models.PasswordResetToken).filter(models.PasswordResetToken.token == token).first()
    reset_row.expires_at = datetime.utcnow() - timedelta(minutes=1)
    session.commit()
    session.close()

    res = client.post("/api/v1/users/reset-password", json={"token": token, "new_password": "newpassword2"})
    assert res.status_code == 400


def test_reset_password_rejects_short_password(client, monkeypatch):
    token = _request_token(client, monkeypatch, "caregiver1@test.com")
    res = client.post("/api/v1/users/reset-password", json={"token": token, "new_password": "1234"})
    assert res.status_code == 400


def test_reset_password_token_is_single_use(client, monkeypatch):
    token = _request_token(client, monkeypatch, "caregiver1@test.com")
    first = client.post("/api/v1/users/reset-password", json={"token": token, "new_password": "newpassword2"})
    assert first.status_code == 200
    second = client.post("/api/v1/users/reset-password", json={"token": token, "new_password": "anotherpass3"})
    assert second.status_code == 400


def test_new_forgot_password_request_invalidates_old_token(client, monkeypatch):
    """비밀번호 찾기를 두 번 누르면, 먼저 받은 메일의 링크는 더 이상 쓸 수 없어야 한다."""
    first_token = _request_token(client, monkeypatch, "caregiver1@test.com")
    _request_token(client, monkeypatch, "caregiver1@test.com")  # 두 번째 요청

    res = client.post("/api/v1/users/reset-password", json={"token": first_token, "new_password": "newpassword2"})
    assert res.status_code == 400
