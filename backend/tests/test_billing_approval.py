from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import billing
from app.database import Base, get_db
from app.api.users import create_access_token

PAGE = Path(__file__).resolve().parents[1] / "static" / "pages" / "billing_management.html"


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    db = Session()
    db.add(models.Center(id=1, name="테스트센터"))
    db.add(models.User(id=1, email="manager@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="caregiver1@test.com", full_name="요양사1", role="caregiver", center_id=1))
    db.add(models.BillingRecord(
        id=1, caregiver_id=2, resident_id=1, center_id=1, service_type="basic_care",
        amount=67043, approval_status="pending", recorded_date=datetime(2026, 10, 3),
    ))
    db.add(models.BillingRecord(
        id=2, caregiver_id=2, resident_id=1, center_id=1, service_type="basic_care",
        amount=67043, approval_status="approved", recorded_date=datetime(2026, 10, 3),
    ))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(billing.router, prefix="/api/v1/billing")

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


def test_manager_approves_flagged_claim_without_reason(client):
    response = client.post("/api/v1/billing/1/approve", json={"user_id": 1, "user_role": "center_manager"})
    assert response.status_code == 200
    assert response.json()["approval_status"] == "approved"


def test_approve_rejects_non_pending_claim(client):
    response = client.post("/api/v1/billing/2/approve", json={"user_id": 1, "user_role": "center_manager"})
    assert response.status_code == 400


def test_caregiver_cannot_approve(client):
    response = client.post("/api/v1/billing/1/approve", json={"user_id": 2, "user_role": "caregiver"}, headers=auth(2, "caregiver", "caregiver1@test.com"))
    assert response.status_code == 403


def test_manager_rejects_pending_claim_with_reason(client):
    response = client.post(
        "/api/v1/billing/1/reject",
        json={"user_id": 1, "user_role": "center_manager", "reason": "시간 기록 불일치"},
    )
    assert response.status_code == 200
    assert response.json()["approval_status"] == "rejected"


def test_approve_page_does_not_ask_for_reason():
    script = PAGE.read_text(encoding="utf-8")
    approve = script[script.index("async function approveBilling"):script.index("async function rejectBilling")]
    assert "prompt(" not in approve
    assert "확인 사유" not in script


def test_reject_page_asks_for_non_empty_reason():
    script = PAGE.read_text(encoding="utf-8")
    reject = script[script.index("async function rejectBilling"):script.index("async function submitToNHIS")]
    assert "prompt('거절 사유" in reject
    assert "reason.trim()" in reject


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}
