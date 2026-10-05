from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import statements
from app.api.users import create_access_token
from app.database import Base, get_db

YM = "2026-10"


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
        amount=1000000, approval_status="approved", year_month=YM, recorded_date=datetime(2026, 10, 5),
    ))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(statements.router, prefix="/api/v1/statements")

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.Session = Session
    return client


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "manager@test.com")
CAREGIVER1 = auth(2, "caregiver", "caregiver1@test.com")
CAREGIVER2 = auth(3, "caregiver", "caregiver2@test.com")


def confirm(client, caregiver_id=2, year_month=YM, headers=MANAGER):
    return client.post("/api/v1/statements/confirm", json={"caregiver_id": caregiver_id, "year_month": year_month}, headers=headers)


def test_confirmed_statement_uses_the_same_deduction_rules(setup):
    assert confirm(setup).status_code == 200
    statement = setup.get("/api/v1/statements/mine", headers=CAREGIVER1).json()["statements"][0]
    assert statement["billing_total"] == 1000000
    assert statement["income_tax"] == 33000
    assert statement["pension"] == 90000
    assert statement["health"] == 34900
    assert statement["employment"] == 6500
    assert statement["net"] == 1000000 - (33000 + 90000 + 34900 + 6500)


def test_caregiver_sees_only_confirmed_statements_and_only_their_own(setup):
    assert setup.get("/api/v1/statements/mine", headers=CAREGIVER1).json()["statements"] == []
    confirm(setup)
    assert setup.get("/api/v1/statements/mine", headers=CAREGIVER2).json()["statements"] == []


def test_statement_does_not_change_after_confirmation(setup):
    confirm(setup)
    db = setup.Session()
    db.add(models.BillingRecord(
        id=2, caregiver_id=2, resident_id=1, center_id=1, service_type="basic_care",
        amount=500000, approval_status="approved", year_month=YM, recorded_date=datetime(2026, 10, 20),
    ))
    db.commit()
    db.close()
    statement = setup.get("/api/v1/statements/mine", headers=CAREGIVER1).json()["statements"][0]
    assert statement["billing_total"] == 1000000


def test_only_manager_can_confirm_and_only_once(setup):
    assert confirm(setup, headers=CAREGIVER1).status_code == 403
    assert confirm(setup).status_code == 200
    assert confirm(setup).status_code == 400


def test_cannot_confirm_a_month_without_approved_claims(setup):
    assert confirm(setup, year_month="2026-09").status_code == 400
