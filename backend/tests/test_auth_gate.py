from datetime import datetime, timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import billing, records, salary
from app.api.users import create_access_token
from app.auth import get_current_user
from app.database import Base, get_db


@pytest.fixture
def setup(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.Center(id=1, name="테스트센터"))
    db.add(models.User(id=1, email="manager@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="caregiver1@test.com", full_name="요양사1", role="caregiver", center_id=1))
    db.add(models.User(id=3, email="caregiver2@test.com", full_name="요양사2", role="caregiver", center_id=1))
    db.add(models.Resident(id=1, center_id=1, name="김1", age=80, health_status="stable", care_grade=1, client_type="일반"))
    db.add(models.BillingRecord(
        id=1, caregiver_id=2, resident_id=1, center_id=1, service_type="basic_care",
        amount=100, approval_status="pending", year_month="2026-10", recorded_date=datetime(2026, 10, 5),
    ))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(billing.router, prefix="/api/v1/billing", dependencies=[Depends(get_current_user)])
    app.include_router(records.router, prefix="/api/v1/records", dependencies=[Depends(get_current_user)])
    app.include_router(salary.router, prefix="/api/v1/salary", dependencies=[Depends(get_current_user)])

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def token_for(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


CAREGIVER1 = token_for(2, "caregiver", "caregiver1@test.com")
CAREGIVER2 = token_for(3, "caregiver", "caregiver2@test.com")
MANAGER = token_for(1, "center_manager", "manager@test.com")


def test_anonymous_request_is_rejected(setup):
    assert setup.get("/api/v1/billing/").status_code == 401
    assert setup.get("/api/v1/salary/current", params={"caregiver_id": 2}).status_code == 401


def test_forged_manager_role_in_body_does_not_grant_approval(setup):
    response = setup.post(
        "/api/v1/billing/1/approve",
        json={"user_id": 1, "user_role": "center_manager"},
        headers=CAREGIVER1,
    )
    assert response.status_code == 403


def test_caregiver_cannot_read_another_caregivers_salary(setup):
    response = setup.get("/api/v1/salary/monthly/2026-10", params={"caregiver_id": 2}, headers=CAREGIVER2)
    assert response.status_code == 403


def test_caregiver_sees_only_own_billing_list(setup):
    response = setup.get("/api/v1/billing/", params={"center_id": 1, "caregiver_id": 3}, headers=CAREGIVER2)
    assert response.status_code == 200
    assert all(r["caregiver_id"] == 3 for r in response.json()["records"])


def test_manager_can_read_any_caregiver_salary(setup):
    response = setup.get("/api/v1/salary/monthly/2026-10", params={"caregiver_id": 2}, headers=MANAGER)
    assert response.status_code == 200


def test_record_is_created_for_the_signed_in_caregiver(setup):
    response = setup.post(
        "/api/v1/records/create",
        json={"caregiver_id": 3, "resident_id": 1, "service_type": "basic_care", "care_items": "", "duration_minutes": 60},
        headers=CAREGIVER1,
    )
    assert response.status_code == 200
    record_id = response.json()["data"]["record_id"]
    stored = setup.get(f"/api/v1/records/daily/{record_id}", headers=MANAGER).json()
    assert stored["caregiver_id"] == 2


def test_caregiver_cannot_read_another_caregivers_record(setup):
    created = setup.post(
        "/api/v1/records/create",
        json={"caregiver_id": 2, "resident_id": 1, "service_type": "basic_care", "care_items": "", "duration_minutes": 60},
        headers=CAREGIVER1,
    )
    record_id = created.json()["data"]["record_id"]
    response = setup.get(f"/api/v1/records/daily/{record_id}", headers=CAREGIVER2)
    assert response.status_code == 403


def test_caregiver_can_read_own_record(setup):
    created = setup.post(
        "/api/v1/records/create",
        json={"caregiver_id": 2, "resident_id": 1, "service_type": "basic_care", "care_items": "", "duration_minutes": 60},
        headers=CAREGIVER1,
    )
    record_id = created.json()["data"]["record_id"]
    response = setup.get(f"/api/v1/records/daily/{record_id}", headers=CAREGIVER1)
    assert response.status_code == 200
