from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import resident_changes, residents
from app.api.users import create_access_token
from app.database import Base, get_db


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chg.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.Center(id=1, name="센터A"))
    db.add(models.User(id=1, email="manager@example.com", hashed_password="x", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="caregiver@example.com", hashed_password="x", full_name="요양사", role="caregiver", center_id=1))
    db.add(models.Resident(id=1, center_id=1, name="김1", age=80, health_status="stable", care_grade=1, client_type="일반",
                           recognition_start=None, recognition_end=None))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(resident_changes.router, prefix="/api/v1/residents")
    app.include_router(residents.router, prefix="/api/v1/residents")

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MANAGER = auth(1, "center_manager", "manager@example.com")
CAREGIVER = auth(2, "caregiver", "caregiver@example.com")


def test_caregiver_edits_address_and_guardian_directly(client):
    response = client.put("/api/v1/residents/1", json={"address": "서울시 새주소 2번지", "guardian_name": "새보호자", "guardian_phone": "010-1111-2222"}, headers=CAREGIVER)
    assert response.status_code == 200


def test_caregiver_cannot_edit_billing_fields_directly(client):
    assert client.put("/api/v1/residents/1", json={"care_grade": 5}, headers=CAREGIVER).status_code == 403


def test_caregiver_request_is_applied_only_after_manager_approves(client):
    created = client.post("/api/v1/residents/1/change-requests", json={"field": "care_grade", "value": "3"}, headers=CAREGIVER)
    assert created.status_code == 200
    request_id = created.json()["data"]["id"]

    pending = client.get("/api/v1/residents/change-requests", headers=MANAGER).json()["requests"]
    assert [r["id"] for r in pending] == [request_id]

    client.post(f"/api/v1/residents/change-requests/{request_id}/approve", headers=MANAGER)
    resident = client.get("/api/v1/residents/1", headers=MANAGER).json()
    assert resident["care_grade"] == 3


def test_rejected_request_leaves_resident_unchanged(client):
    request_id = client.post("/api/v1/residents/1/change-requests", json={"field": "client_type", "value": "기초생활보장"}, headers=CAREGIVER).json()["data"]["id"]
    assert client.post(f"/api/v1/residents/change-requests/{request_id}/reject", json={"reason": "서류 미제출"}, headers=MANAGER).status_code == 200
    assert client.get("/api/v1/residents/1", headers=MANAGER).json()["client_type"] == "일반"


def test_reject_requires_reason(client):
    request_id = client.post("/api/v1/residents/1/change-requests", json={"field": "care_grade", "value": "2"}, headers=CAREGIVER).json()["data"]["id"]
    assert client.post(f"/api/v1/residents/change-requests/{request_id}/reject", json={"reason": " "}, headers=MANAGER).status_code == 400


def test_invalid_value_is_refused_before_saving(client):
    assert client.post("/api/v1/residents/1/change-requests", json={"field": "care_grade", "value": "9"}, headers=CAREGIVER).status_code == 400


def test_caregiver_cannot_approve_requests(client):
    request_id = client.post("/api/v1/residents/1/change-requests", json={"field": "care_grade", "value": "2"}, headers=CAREGIVER).json()["data"]["id"]
    assert client.post(f"/api/v1/residents/change-requests/{request_id}/approve", headers=CAREGIVER).status_code == 403


def test_caregiver_sees_own_requests_with_outcome_and_reason(client):
    approved = client.post("/api/v1/residents/1/change-requests", json={"field": "care_grade", "value": "2"}, headers=CAREGIVER).json()["data"]["id"]
    rejected = client.post("/api/v1/residents/1/change-requests", json={"field": "client_type", "value": "의료급여"}, headers=CAREGIVER).json()["data"]["id"]
    client.post(f"/api/v1/residents/change-requests/{approved}/approve", headers=MANAGER)
    client.post(f"/api/v1/residents/change-requests/{rejected}/reject", json={"reason": "서류 확인 필요"}, headers=MANAGER)

    mine = client.get("/api/v1/residents/change-requests/mine", headers=CAREGIVER).json()["requests"]
    by_id = {r["id"]: r for r in mine}
    assert by_id[approved]["status"] == "approved"
    assert by_id[rejected]["status"] == "rejected"
    assert by_id[rejected]["reason"] == "서류 확인 필요"


def test_manager_list_for_caregiver_mine_is_empty_for_manager(client):
    client.post("/api/v1/residents/1/change-requests", json={"field": "care_grade", "value": "2"}, headers=CAREGIVER)
    assert client.get("/api/v1/residents/change-requests/mine", headers=MANAGER).json()["requests"] == []
