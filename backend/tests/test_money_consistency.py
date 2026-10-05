import re
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import billing, records, salary
from app.database import Base, get_db
from app.api.users import create_access_token

YM = "2026-10"
SEED = [
    ("approved", 100),
    ("submitted_to_nhis", 200),
    ("reimbursed", 300),
    ("pending", 400),
    ("draft", 500),
    ("rejected", 600),
]
REVENUE_TOTAL = 100 + 200 + 300


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    db = Session()
    db.add(models.Center(id=1, name="테스트센터"))
    db.add(models.User(id=1, email="manager@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="caregiver1@test.com", full_name="요양사1", role="caregiver", center_id=1))
    db.add(models.Resident(id=1, center_id=1, name="김1", age=80, health_status="stable", care_grade=1, client_type="일반"))
    for i, (status, amount) in enumerate(SEED, start=1):
        db.add(models.BillingRecord(
            id=i, caregiver_id=2, resident_id=1, center_id=1, service_type="basic_care",
            amount=amount, approval_status=status, year_month=YM,
            is_archived=(status == "reimbursed"),
            recorded_date=datetime(2026, 10, 5),
        ))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(billing.router, prefix="/api/v1/billing")
    app.include_router(records.router, prefix="/api/v1/records")
    app.include_router(salary.router, prefix="/api/v1/salary")

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.headers.update(auth(1, "center_manager", "manager@test.com"))
    return client


def test_monthly_statistics_counts_only_post_approval_money(client):
    body = client.get("/api/v1/records/monthly-statistics", params={"center_id": 1, "year": 2026, "month": 10}).json()
    assert body["total_summary"]["total_amount"] == REVENUE_TOTAL
    assert body["total_summary"]["approved_count"] == 3
    assert body["total_summary"]["pending_count"] == 1
    assert body["by_caregiver"][0]["total_amount"] == REVENUE_TOTAL


def test_monthly_summary_matches_statistics(client):
    body = client.get("/api/v1/records/monthly-summary", params={"center_id": 1, "year_month": YM}).json()
    assert body["summary"]["total_amount"] == REVENUE_TOTAL


def test_archived_reimbursed_claim_stays_in_money_but_not_in_worklist(client):
    worklist = client.get("/api/v1/billing/", params={"center_id": 1}).json()["records"]
    assert all(r["approval_status"] != "reimbursed" for r in worklist)
    money = client.get("/api/v1/billing/", params={"center_id": 1, "include_archived": "true"}).json()["records"]
    assert any(r["approval_status"] == "reimbursed" for r in money)


def test_monthly_salary_matches_revenue(client):
    body = client.get(f"/api/v1/salary/monthly/{YM}", params={"caregiver_id": 2}).json()
    assert body["total_amount"] == REVENUE_TOTAL


def test_manager_can_return_approved_claim_to_pending(client):
    client.post("/api/v1/billing/1/approve", json={"user_id": 1, "user_role": "center_manager"})
    response = client.patch("/api/v1/billing/1", json={"approval_status": "pending", "user_id": 1, "user_role": "center_manager"})
    assert response.status_code == 200
    assert response.json()["data"]["approval_status"] == "pending"


def test_caregiver_cannot_return_claim(client):
    response = client.patch("/api/v1/billing/1", json={"approval_status": "pending", "user_id": 2, "user_role": "caregiver"}, headers=auth(2, "caregiver", "caregiver1@test.com"))
    assert response.status_code == 403


def test_no_duplicate_routes_in_billing_router():
    seen = {}
    for route in billing.router.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                key = (method, re.sub(r"\{\w+\}", "{}", route.path_format))
                seen[key] = seen.get(key, 0) + 1
    duplicates = {k: v for k, v in seen.items() if v > 1}
    assert duplicates == {}


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}
