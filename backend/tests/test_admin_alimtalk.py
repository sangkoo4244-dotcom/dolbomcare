from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import admin
from app.api import users as users_api
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATFORM_ADMIN_EMAILS", "owner@eeumlogic.com")

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    db = Session()
    db.add(models.Center(id=1, name="테스트센터", alimtalk_balance=1000))
    db.add(models.User(id=1, email="owner@eeumlogic.com", full_name="운영자", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="manager@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(admin.router, prefix="/api/v1/admin")
    app.include_router(users_api.router, prefix="/api/v1/users")

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


def test_non_admin_manager_is_denied(client):
    headers = auth(2, "center_manager", "manager@test.com")
    assert client.get("/api/v1/admin/alimtalk-overview", headers=headers).status_code == 403
    assert client.post("/api/v1/admin/alimtalk-charge", headers=headers, json={"center_id": 1, "amount": 1000}).status_code == 403
    assert client.get("/api/v1/admin/is-admin", headers=headers).status_code == 403


def test_is_admin_true_for_admin_email(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    res = client.get("/api/v1/admin/is-admin", headers=headers)
    assert res.status_code == 200
    assert res.json()["is_admin"] is True


def test_admin_email_can_view_overview(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    res = client.get("/api/v1/admin/alimtalk-overview", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body[0]["center_name"] == "테스트센터"
    assert body[0]["balance"] == 1000


def test_admin_can_charge_balance(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    res = client.post("/api/v1/admin/alimtalk-charge", headers=headers, json={"center_id": 1, "amount": 5000})
    assert res.status_code == 200
    assert res.json()["balance"] == 6000


def test_charge_rejects_zero_amount(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    res = client.post("/api/v1/admin/alimtalk-charge", headers=headers, json={"center_id": 1, "amount": 0})
    assert res.status_code == 400


def test_non_admin_cannot_create_center(client):
    headers = auth(2, "center_manager", "manager@test.com")
    res = client.post("/api/v1/admin/centers", headers=headers, json={
        "center_name": "새 센터", "manager_name": "김센터장",
        "manager_email": "new@test.com", "manager_password": "password123",
    })
    assert res.status_code == 403


def test_admin_can_create_center_and_manager_can_login(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    res = client.post("/api/v1/admin/centers", headers=headers, json={
        "center_name": "새 센터", "manager_name": "김센터장",
        "manager_email": "new@test.com", "manager_password": "password123",
    })
    assert res.status_code == 200
    body = res.json()
    assert body["center_name"] == "새 센터"
    assert body["manager_email"] == "new@test.com"

    overview = client.get("/api/v1/admin/alimtalk-overview", headers=headers).json()
    assert any(r["center_name"] == "새 센터" for r in overview)


def test_create_center_rejects_duplicate_email(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    res = client.post("/api/v1/admin/centers", headers=headers, json={
        "center_name": "다른 센터", "manager_name": "박센터장",
        "manager_email": "manager@test.com", "manager_password": "password123",
    })
    assert res.status_code == 400


def test_create_center_rejects_short_password(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    res = client.post("/api/v1/admin/centers", headers=headers, json={
        "center_name": "다른 센터", "manager_name": "박센터장",
        "manager_email": "short@test.com", "manager_password": "1234",
    })
    assert res.status_code == 400


def test_create_center_rejects_blank_name(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    res = client.post("/api/v1/admin/centers", headers=headers, json={
        "center_name": "   ", "manager_name": "박센터장",
        "manager_email": "blank@test.com", "manager_password": "password123",
    })
    assert res.status_code == 400


def test_non_admin_cannot_delete_center(client):
    headers = auth(2, "center_manager", "manager@test.com")
    assert client.delete("/api/v1/admin/centers/1", headers=headers).status_code == 403


def test_delete_center_blocked_when_residents_exist(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    created = client.post("/api/v1/admin/centers", headers=headers, json={
        "center_name": "이용자있는센터", "manager_name": "정센터장",
        "manager_email": "has-residents@test.com", "manager_password": "password123",
    }).json()
    center_id = created["center_id"]

    session = client.Session()
    session.add(models.Resident(center_id=center_id, name="김어르신"))
    session.commit()
    session.close()

    res = client.delete(f"/api/v1/admin/centers/{center_id}", headers=headers)
    assert res.status_code == 400
    assert "이용자" in res.json()["detail"]


def test_delete_center_blocked_when_extra_staff_exists(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    # 테스트센터(id=1)는 fixture에서 이미 직원 2명(운영자 본인 + 센터장)이 속해 있다
    res = client.delete("/api/v1/admin/centers/1", headers=headers)
    assert res.status_code == 400
    assert "직원" in res.json()["detail"]


def test_delete_empty_center_succeeds_and_manager_cannot_login(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    created = client.post("/api/v1/admin/centers", headers=headers, json={
        "center_name": "삭제될센터", "manager_name": "임시센터장",
        "manager_email": "to-delete@test.com", "manager_password": "password123",
    }).json()
    center_id = created["center_id"]

    overview_before = client.get("/api/v1/admin/alimtalk-overview", headers=headers).json()
    assert any(r["center_id"] == center_id for r in overview_before)

    res = client.delete(f"/api/v1/admin/centers/{center_id}", headers=headers)
    assert res.status_code == 200

    overview_after = client.get("/api/v1/admin/alimtalk-overview", headers=headers).json()
    assert not any(r["center_id"] == center_id for r in overview_after)

    login = client.post("/api/v1/users/login", json={"email": "to-delete@test.com", "password": "password123"})
    assert login.status_code in (401, 404)
