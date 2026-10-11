from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import residents
from app.api.users import create_access_token
from app.database import Base, get_db


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'res.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.Center(id=1, name="센터A"))
    db.add(models.User(id=1, email="manager@example.com", hashed_password="x", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="caregiver@example.com", hashed_password="x", full_name="요양사", role="caregiver", center_id=1))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(residents.router, prefix="/api/v1/residents")

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    c = TestClient(app)
    token = create_access_token({"sub": "manager@example.com", "uid": 1, "role": "center_manager"}, timedelta(hours=1))
    c.headers.update({"Authorization": f"Bearer {token}"})
    return c


def body(**overrides):
    base = {"name": "김1", "age": 80, "health_status": "stable", "center_id": 1, "care_grade": 1, "client_type": "일반"}
    base.update(overrides)
    return base


def test_create_accepts_valid_recognition_period(client):
    response = client.post("/api/v1/residents/", json=body(recognition_start="2026-01-01", recognition_end="2027-12-31"))
    assert response.status_code == 200


def test_create_rejects_end_before_start(client):
    response = client.post("/api/v1/residents/", json=body(recognition_start="2026-06-01", recognition_end="2026-01-01"))
    assert response.status_code == 400


def test_create_rejects_bad_date_format(client):
    response = client.post("/api/v1/residents/", json=body(recognition_start="2026/01/01"))
    assert response.status_code == 400


def test_update_rejects_end_before_existing_start(client):
    created = client.post("/api/v1/residents/", json=body(recognition_start="2026-01-01", recognition_end="2027-12-31")).json()
    resident_id = created["data"]["id"]
    response = client.put(f"/api/v1/residents/{resident_id}", json={"recognition_end": "2025-12-31"})
    assert response.status_code == 400


def test_caregiver_can_only_change_health_status(client):
    from datetime import timedelta
    from app.api.users import create_access_token
    created = client.post("/api/v1/residents/", json=body(recognition_start="2026-01-01", recognition_end="2027-12-31")).json()
    resident_id = created["data"]["id"]
    caregiver = {"Authorization": "Bearer " + create_access_token({"sub": "caregiver@example.com", "uid": 2, "role": "caregiver"}, timedelta(hours=1))}
    assert client.put(f"/api/v1/residents/{resident_id}", json={"health_status": "warning"}, headers=caregiver).status_code == 200
    assert client.put(f"/api/v1/residents/{resident_id}", json={"care_grade": 5}, headers=caregiver).status_code == 403
    assert client.put(f"/api/v1/residents/{resident_id}", json={"client_type": "기초생활보장"}, headers=caregiver).status_code == 403
    assert client.put(f"/api/v1/residents/{resident_id}", json={"recognition_end": "2030-01-01"}, headers=caregiver).status_code == 403
    assert client.put(f"/api/v1/residents/{resident_id}", json={"primary_caregiver_id": 2}, headers=caregiver).status_code == 403


def test_manager_assigns_caregiver_and_list_filters_by_it(client):
    created1 = client.post("/api/v1/residents/", json=body(name="김1")).json()
    created2 = client.post("/api/v1/residents/", json=body(name="이2")).json()
    id1, id2 = created1["data"]["id"], created2["data"]["id"]

    assert client.put(f"/api/v1/residents/{id1}", json={"primary_caregiver_id": 2}).status_code == 200

    all_residents = client.get("/api/v1/residents/?center_id=1").json()["residents"]
    assert {r["id"] for r in all_residents} == {id1, id2}

    mine = client.get("/api/v1/residents/?caregiver_id=2").json()["residents"]
    assert [r["id"] for r in mine] == [id1]
    assert mine[0]["primary_caregiver_name"] == "요양사"

    unassign = client.put(f"/api/v1/residents/{id1}", json={"primary_caregiver_id": None})
    assert unassign.status_code == 200
    assert client.get("/api/v1/residents/?caregiver_id=2").json()["residents"] == []
