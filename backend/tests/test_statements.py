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


def test_wage_ratio_applies_before_deductions_not_on_full_billing_amount(setup):
    """요양사 급여는 공단 청구액 전체가 아니라 계약된 비율만큼이어야 한다 (billing_total=센터 매출, wage_base=급여 산정 기준)."""
    db = setup.Session()
    db.query(models.User).filter(models.User.id == 2).update({"wage_ratio": 50})
    db.commit()
    db.close()

    assert confirm(setup).status_code == 200
    statement = setup.get("/api/v1/statements/mine", headers=CAREGIVER1).json()["statements"][0]
    assert statement["billing_total"] == 1000000
    assert statement["wage_ratio"] == 50
    assert statement["wage_base"] == 500000
    assert statement["income_tax"] == 16500
    assert statement["pension"] == 45000
    assert statement["health"] == 17450
    assert statement["employment"] == 3250
    assert statement["net"] == 500000 - (16500 + 45000 + 17450 + 3250)


def test_status_endpoint_reports_wage_ratio_and_base(setup):
    db = setup.Session()
    db.query(models.User).filter(models.User.id == 2).update({"wage_ratio": 60})
    db.commit()
    db.close()

    rows = setup.get(f"/api/v1/statements/status?year_month={YM}", headers=MANAGER).json()["caregivers"]
    row = next(r for r in rows if r["caregiver_id"] == 2)
    assert row["wage_ratio"] == 60
    assert row["wage_base"] == 600000

    other = next(r for r in rows if r["caregiver_id"] == 3)
    assert other["wage_ratio"] == 100  # 설정 안 하면 기존 동작과 동일(100%)


def add_approved_claim(client, claim_id, amount, caregiver_id=2):
    db = client.Session()
    db.add(models.BillingRecord(
        id=claim_id, caregiver_id=caregiver_id, resident_id=1, center_id=1, service_type="basic_care",
        amount=amount, approval_status="approved", year_month=YM, recorded_date=datetime(2026, 10, 20),
    ))
    db.commit()
    db.close()


def status_row(client, caregiver_id=2):
    rows = client.get("/api/v1/statements/status", params={"year_month": YM}, headers=MANAGER).json()["caregivers"]
    return next(r for r in rows if r["caregiver_id"] == caregiver_id)


def test_status_shows_confirmed_amount_and_flags_claims_added_after_confirmation(setup):
    confirm(setup)
    added_before = status_row(setup)
    assert added_before["confirmed"] and not added_before["stale"]
    add_approved_claim(setup, 2, 500000)
    row = status_row(setup)
    assert row["billing_total"] == 1000000  # 확정 당시 금액을 보여 준다
    assert row["live_billing_total"] == 1500000
    assert row["stale"] is True
    assert row["net"] == added_before["net"]


def test_reconfirm_updates_the_saved_amount_only_when_claims_changed(setup):
    confirm(setup)
    assert setup.post("/api/v1/statements/reconfirm", json={"caregiver_id": 2, "year_month": YM}, headers=MANAGER).status_code == 400
    add_approved_claim(setup, 2, 500000)
    r = setup.post("/api/v1/statements/reconfirm", json={"caregiver_id": 2, "year_month": YM}, headers=MANAGER)
    assert r.status_code == 200 and r.json()["statement"]["billing_total"] == 1500000
    row = status_row(setup)
    assert row["billing_total"] == 1500000 and row["stale"] is False
    assert setup.get("/api/v1/statements/mine", headers=CAREGIVER1).json()["statements"][0]["billing_total"] == 1500000


def test_reconfirm_needs_a_prior_confirmation_and_only_manager(setup):
    assert setup.post("/api/v1/statements/reconfirm", json={"caregiver_id": 2, "year_month": YM}, headers=MANAGER).status_code == 400
    confirm(setup)
    assert setup.post("/api/v1/statements/reconfirm", json={"caregiver_id": 2, "year_month": YM}, headers=CAREGIVER1).status_code == 403
