from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import copay
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
    db.add(models.User(id=1, email="manager@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="caregiver1@test.com", full_name="요양사1", role="caregiver", center_id=1))
    db.add(models.Resident(id=1, center_id=1, name="김이용", client_type="일반"))
    # 승인된 청구 두 건: 본인부담금 = (total_cost - amount) 합 = (34120-29000) + (17450-14800) = 5120 + 2650 = 7770
    db.add(models.BillingRecord(
        id=1, caregiver_id=2, resident_id=1, center_id=1, service_type="basic_care",
        total_cost=34120, amount=29000, approval_status="approved",
        recorded_date=datetime(2026, 10, 3), year_month="2026-10",
    ))
    db.add(models.BillingRecord(
        id=2, caregiver_id=2, resident_id=1, center_id=1, service_type="basic_care",
        total_cost=17450, amount=14800, approval_status="approved",
        recorded_date=datetime(2026, 10, 10), year_month="2026-10",
    ))
    # 반려된 청구는 본인부담금 집계에서 빠져야 한다
    db.add(models.BillingRecord(
        id=3, caregiver_id=2, resident_id=1, center_id=1, service_type="basic_care",
        total_cost=100000, amount=80000, approval_status="rejected",
        recorded_date=datetime(2026, 10, 15), year_month="2026-10",
    ))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(copay.router, prefix="/api/v1/copay")

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


def test_summary_computes_copay_from_approved_billing_only(client):
    res = client.get("/api/v1/copay/summary?year_month=2026-10", headers=MANAGER)
    assert res.status_code == 200
    data = res.json()
    assert len(data["invoices"]) == 1
    inv = data["invoices"][0]
    assert inv["resident_name"] == "김이용"
    assert inv["total_amount"] == 7770  # 반려 건(20000)은 제외
    assert inv["paid_amount"] == 0
    assert inv["status"] == "unpaid"


def test_caregiver_cannot_see_summary(client):
    res = client.get("/api/v1/copay/summary?year_month=2026-10", headers=CAREGIVER)
    assert res.status_code == 403


def test_partial_then_full_payment(client):
    res = client.post("/api/v1/copay/1/pay", headers=MANAGER, json={
        "year_month": "2026-10", "amount": 3000, "payment_method": "현금",
    })
    assert res.status_code == 200
    assert res.json()["data"]["status"] == "partial"
    assert res.json()["data"]["balance"] == 4770

    res = client.post("/api/v1/copay/1/pay", headers=MANAGER, json={
        "year_month": "2026-10", "amount": 4770, "payment_method": "계좌이체",
    })
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["status"] == "paid"
    assert body["balance"] == 0
    assert body["paid_amount"] == 7770


def test_status_recalculates_when_billing_is_later_rejected(client):
    """승인된 청구 1건을 다 수납한 뒤, 다른 청구가 반려되어 총액이 줄어들면 상태가 그대로 'paid'를 유지해야 한다."""
    client.post("/api/v1/copay/1/pay", headers=MANAGER, json={"year_month": "2026-10", "amount": 7770})
    res = client.get("/api/v1/copay/summary?year_month=2026-10", headers=MANAGER)
    inv = res.json()["invoices"][0]
    assert inv["status"] == "paid"
    assert inv["balance"] == 0

    # 청구 1건(34120-29000=5120)이 반려되면 총액이 2650으로 줄어든다 - 이미 7770을 냈으니 여전히 완납 상태여야 한다
    db = client.app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db]
    session = next(db())
    record = session.query(__import__("app.models", fromlist=["BillingRecord"]).BillingRecord).get(1)
    record.approval_status = "rejected"
    session.commit()
    session.close()

    res = client.get("/api/v1/copay/summary?year_month=2026-10", headers=MANAGER)
    inv = res.json()["invoices"][0]
    assert inv["total_amount"] == 2650
    assert inv["status"] == "paid"  # 7770 >= 2650 이므로 여전히 완납
    assert inv["balance"] == 0


def test_history_lists_invoice_after_payment(client):
    client.post("/api/v1/copay/1/pay", headers=MANAGER, json={
        "year_month": "2026-10", "amount": 1000,
    })
    res = client.get("/api/v1/copay/resident/1/history", headers=MANAGER)
    assert res.status_code == 200
    invoices = res.json()["invoices"]
    assert len(invoices) == 1
    assert invoices[0]["year_month"] == "2026-10"
    assert invoices[0]["paid_amount"] == 1000
