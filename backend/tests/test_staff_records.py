from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import staff_records
from app.database import Base, get_db
from app.api.users import create_access_token


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
    db.add(models.Center(id=2, name="다른센터"))
    db.add(models.User(id=1, email="manager@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="caregiver1@test.com", full_name="요양사1", role="caregiver", center_id=1))
    db.add(models.User(id=3, email="other@test.com", full_name="다른센터직원", role="caregiver", center_id=2))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(staff_records.router, prefix="/api/v1/staff-records")

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


def test_caregiver_cannot_create_or_list(client):
    res = client.post("/api/v1/staff-records/", headers=CAREGIVER, json={
        "staff_id": 2, "record_type": "health_checkup", "record_date": "2026-10-01",
    })
    assert res.status_code == 403
    res = client.get("/api/v1/staff-records/staff/2", headers=CAREGIVER)
    assert res.status_code == 403


def test_create_and_list_grouped_by_type(client):
    res = client.post("/api/v1/staff-records/", headers=MANAGER, json={
        "staff_id": 2, "record_type": "continuing_education", "record_date": "2026-09-15",
        "title": "2026년 보수교육", "detail": "8시간 이수", "amount": 8,
    })
    assert res.status_code == 200
    assert res.json()["data"]["recorded_by_name"] == "센터장"

    res = client.post("/api/v1/staff-records/", headers=MANAGER, json={
        "staff_id": 2, "record_type": "annual_leave", "record_date": "2026-10-05",
        "title": "연차 사용", "amount": 1,
    })
    assert res.status_code == 200

    res = client.get("/api/v1/staff-records/staff/2", headers=MANAGER)
    assert res.status_code == 200
    data = res.json()["records"]
    assert set(data.keys()) == set(staff_records.RECORD_TYPES.keys())
    assert len(data["continuing_education"]["items"]) == 1
    assert data["continuing_education"]["items"][0]["amount"] == 8
    assert len(data["annual_leave"]["items"]) == 1
    assert data["health_checkup"]["items"] == []


def test_invalid_record_type_rejected(client):
    res = client.post("/api/v1/staff-records/", headers=MANAGER, json={
        "staff_id": 2, "record_type": "not_a_type", "record_date": "2026-10-01",
    })
    assert res.status_code == 400


def test_cannot_access_other_centers_staff(client):
    res = client.get("/api/v1/staff-records/staff/3", headers=MANAGER)
    assert res.status_code == 404
    res = client.post("/api/v1/staff-records/", headers=MANAGER, json={
        "staff_id": 3, "record_type": "grievance", "record_date": "2026-10-01",
    })
    assert res.status_code == 404


def test_delete_record(client):
    created = client.post("/api/v1/staff-records/", headers=MANAGER, json={
        "staff_id": 2, "record_type": "grievance", "record_date": "2026-10-01", "status": "open",
    }).json()["data"]
    res = client.delete(f"/api/v1/staff-records/{created['id']}", headers=MANAGER)
    assert res.status_code == 200
    data = client.get("/api/v1/staff-records/staff/2", headers=MANAGER).json()["records"]
    assert data["grievance"]["items"] == []
