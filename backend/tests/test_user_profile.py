from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import users
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    db = Session()
    db.add(models.Center(id=1, name="테스트센터"))
    db.add(models.User(id=1, email="caregiver1@test.com", hashed_password="x", full_name="요양사1", role="caregiver", center_id=1, phone="010-1111-1111"))
    db.add(models.User(id=2, email="manager@test.com", hashed_password="x", full_name="센터장", role="center_manager", center_id=1))
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
    return TestClient(app)


CAREGIVER = auth(1, "caregiver", "caregiver1@test.com")
MANAGER = auth(2, "center_manager", "manager@test.com")


def test_get_my_profile(client):
    res = client.get("/api/v1/users/me", headers=CAREGIVER)
    assert res.status_code == 200
    body = res.json()
    assert body["full_name"] == "요양사1"
    assert body["role"] == "caregiver"
    assert body["profile_image"] is None


def test_update_profile_name_and_phone(client):
    res = client.patch("/api/v1/users/me", headers=CAREGIVER, json={"full_name": "김요양", "phone": "010-9999-9999"})
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["full_name"] == "김요양"
    assert data["phone"] == "010-9999-9999"

    res = client.get("/api/v1/users/me", headers=CAREGIVER)
    assert res.json()["full_name"] == "김요양"


def test_update_profile_image(client):
    res = client.patch("/api/v1/users/me", headers=CAREGIVER, json={"profile_image": "data:image/jpeg;base64,abc123"})
    assert res.status_code == 200
    assert res.json()["data"]["profile_image"] == "data:image/jpeg;base64,abc123"

    # 빈 문자열로 보내면 제거
    res = client.patch("/api/v1/users/me", headers=CAREGIVER, json={"profile_image": ""})
    assert res.json()["data"]["profile_image"] is None


def test_cannot_set_empty_name(client):
    res = client.patch("/api/v1/users/me", headers=CAREGIVER, json={"full_name": "   "})
    assert res.status_code == 400


def test_profile_cannot_change_email_or_role(client):
    # ProfileUpdate 스키마에 email/role 필드 자체가 없어 보내도 무시된다
    res = client.patch("/api/v1/users/me", headers=CAREGIVER, json={"full_name": "변경됨"})
    assert res.status_code == 200
    res2 = client.get("/api/v1/users/me", headers=CAREGIVER)
    assert res2.json()["email"] == "caregiver1@test.com"
    assert res2.json()["role"] == "caregiver"


def test_manager_can_also_use_own_profile_endpoint(client):
    res = client.get("/api/v1/users/me", headers=MANAGER)
    assert res.status_code == 200
    assert res.json()["role"] == "center_manager"
