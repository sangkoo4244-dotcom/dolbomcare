from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import resident_media
from app.database import Base, get_db
from app.api.users import create_access_token

TINY_PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="


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
    db.add(models.User(id=1, email="manager@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="caregiver1@test.com", full_name="요양사1", role="caregiver", center_id=1))
    db.add(models.User(id=3, email="guardian@test.com", full_name="보호자", role="guardian"))
    db.add(models.User(id=4, email="other_guardian@test.com", full_name="다른보호자", role="guardian"))
    db.add(models.Resident(id=1, center_id=1, name="김이용", guardian_id=3))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(resident_media.router, prefix="/api/v1/resident-media")

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
GUARDIAN = auth(3, "guardian", "guardian@test.com")
OTHER_GUARDIAN = auth(4, "guardian", "other_guardian@test.com")


def test_caregiver_and_guardian_can_both_upload(client):
    res = client.post("/api/v1/resident-media/", headers=CAREGIVER, json={
        "resident_id": 1, "image_data": TINY_PNG, "caption": "오늘 산책",
    })
    assert res.status_code == 200
    res = client.post("/api/v1/resident-media/", headers=GUARDIAN, json={
        "resident_id": 1, "image_data": TINY_PNG,
    })
    assert res.status_code == 200

    res = client.get("/api/v1/resident-media/resident/1", headers=MANAGER)
    data = res.json()
    assert data["staff_count"] == 1
    assert data["guardian_count"] == 1
    assert len(data["media"]) == 2


def test_unrelated_guardian_cannot_view_or_upload(client):
    res = client.get("/api/v1/resident-media/resident/1", headers=OTHER_GUARDIAN)
    assert res.status_code == 403
    res = client.post("/api/v1/resident-media/", headers=OTHER_GUARDIAN, json={
        "resident_id": 1, "image_data": TINY_PNG,
    })
    assert res.status_code == 403


def test_non_image_data_rejected(client):
    res = client.post("/api/v1/resident-media/", headers=CAREGIVER, json={
        "resident_id": 1, "image_data": "not-a-data-url",
    })
    assert res.status_code == 400


def test_oversized_image_rejected(client):
    huge = "data:image/png;base64," + ("A" * 5_000_000)
    res = client.post("/api/v1/resident-media/", headers=CAREGIVER, json={
        "resident_id": 1, "image_data": huge,
    })
    assert res.status_code == 400


def test_guardian_can_delete_own_but_not_staff_photo(client):
    staff_photo = client.post("/api/v1/resident-media/", headers=CAREGIVER, json={
        "resident_id": 1, "image_data": TINY_PNG,
    }).json()["data"]
    guardian_photo = client.post("/api/v1/resident-media/", headers=GUARDIAN, json={
        "resident_id": 1, "image_data": TINY_PNG,
    }).json()["data"]

    assert client.delete(f"/api/v1/resident-media/{staff_photo['id']}", headers=GUARDIAN).status_code == 403
    assert client.delete(f"/api/v1/resident-media/{guardian_photo['id']}", headers=GUARDIAN).status_code == 200


def test_manager_can_delete_anyones_photo(client):
    guardian_photo = client.post("/api/v1/resident-media/", headers=GUARDIAN, json={
        "resident_id": 1, "image_data": TINY_PNG,
    }).json()["data"]
    assert client.delete(f"/api/v1/resident-media/{guardian_photo['id']}", headers=MANAGER).status_code == 200
