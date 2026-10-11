from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import centers
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
    db.add(models.Center(id=1, name="테스트센터", address="서울시", phone="02-0000-0000"))
    db.add(models.Center(id=2, name="다른센터"))
    db.add(models.User(id=1, email="manager@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="caregiver1@test.com", full_name="요양사1", role="caregiver", center_id=1))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(centers.router, prefix="/api/v1/centers")

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


MANAGER = auth(1, "center_manager", "manager@test.com")
CAREGIVER = auth(2, "caregiver", "caregiver1@test.com")


def test_manager_can_view_own_center(client):
    res = client.get("/api/v1/centers/me", headers=MANAGER)
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "테스트센터"
    assert body["institution_code"] is None


def test_caregiver_cannot_view_or_edit_center(client):
    assert client.get("/api/v1/centers/me", headers=CAREGIVER).status_code == 403
    assert client.put("/api/v1/centers/me", headers=CAREGIVER, json={"name": "변경"}).status_code == 403


def test_manager_can_update_institution_code_and_other_fields(client):
    res = client.put("/api/v1/centers/me", headers=MANAGER, json={
        "name": "새 센터명", "address": "부산시", "phone": "051-0000-0000", "institution_code": "14139000308",
    })
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["name"] == "새 센터명"
    assert data["institution_code"] == "14139000308"

    # 반영 확인
    res = client.get("/api/v1/centers/me", headers=MANAGER)
    assert res.json()["address"] == "부산시"


def test_partial_update_does_not_clear_other_fields(client):
    client.put("/api/v1/centers/me", headers=MANAGER, json={"institution_code": "14139000308"})
    res = client.get("/api/v1/centers/me", headers=MANAGER)
    body = res.json()
    assert body["name"] == "테스트센터"  # 그대로 유지
    assert body["institution_code"] == "14139000308"
