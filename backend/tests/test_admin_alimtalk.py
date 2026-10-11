from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import admin
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

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


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
