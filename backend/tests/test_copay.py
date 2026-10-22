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
    db.add(models.Center(id=2, name="다른센터"))
    db.add(models.User(id=1, email="manager@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="caregiver1@test.com", full_name="요양사1", role="caregiver", center_id=1))
    db.add(models.User(id=3, email="guardian@test.com", full_name="보호자", role="guardian"))
    db.add(models.User(id=4, email="other_guardian@test.com", full_name="남의보호자", role="guardian"))
    db.add(models.User(id=5, email="other_caregiver@test.com", full_name="다른센터요양사", role="caregiver", center_id=2))
    db.add(models.Resident(id=1, center_id=1, name="김이용", client_type="일반", guardian_id=3))
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
GUARDIAN = auth(3, "guardian", "guardian@test.com")
OTHER_GUARDIAN = auth(4, "guardian", "other_guardian@test.com")
OTHER_CENTER_CAREGIVER = auth(5, "caregiver", "other_caregiver@test.com")


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
    record = session.get(models.BillingRecord, 1)
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


def test_annual_statement_sums_only_paid_amounts_for_the_year(client):
    client.post("/api/v1/copay/1/pay", headers=MANAGER, json={"year_month": "2026-10", "amount": 3000})
    client.post("/api/v1/copay/1/pay", headers=MANAGER, json={"year_month": "2026-10", "amount": 4770})

    res = client.get("/api/v1/copay/resident/1/annual-statement?year=2026", headers=MANAGER)
    assert res.status_code == 200
    data = res.json()
    assert data["resident_name"] == "김이용"
    assert data["center_name"] == "테스트센터"
    assert data["year"] == 2026
    assert len(data["monthly"]) == 12
    october = next(m for m in data["monthly"] if m["year_month"] == "2026-10")
    assert october["paid_amount"] == 7770
    other_months = [m for m in data["monthly"] if m["year_month"] != "2026-10"]
    assert all(m["paid_amount"] == 0 for m in other_months)
    assert data["total_paid"] == 7770


def test_annual_statement_accessible_to_same_center_staff(client):
    res = client.get("/api/v1/copay/resident/1/annual-statement?year=2026", headers=CAREGIVER)
    assert res.status_code == 200


def test_annual_statement_rejects_other_center_staff(client):
    res = client.get("/api/v1/copay/resident/1/annual-statement?year=2026", headers=OTHER_CENTER_CAREGIVER)
    assert res.status_code == 404


def test_linked_guardian_can_self_serve_annual_statement(client):
    """보호자가 본인이 연결된 이용자의 연말정산 납부확인서를 센터에 요청하지 않고 직접 발급받을 수 있어야 한다."""
    client.post("/api/v1/copay/1/pay", headers=MANAGER, json={"year_month": "2026-10", "amount": 7770})
    res = client.get("/api/v1/copay/resident/1/annual-statement?year=2026", headers=GUARDIAN)
    assert res.status_code == 200
    assert res.json()["total_paid"] == 7770


def test_unrelated_guardian_cannot_see_annual_statement(client):
    res = client.get("/api/v1/copay/resident/1/annual-statement?year=2026", headers=OTHER_GUARDIAN)
    assert res.status_code == 403


def test_linked_guardian_can_see_copay_history(client):
    client.post("/api/v1/copay/1/pay", headers=MANAGER, json={"year_month": "2026-10", "amount": 1000})
    res = client.get("/api/v1/copay/resident/1/history", headers=GUARDIAN)
    assert res.status_code == 200
    assert res.json()["invoices"][0]["paid_amount"] == 1000


def test_unrelated_guardian_cannot_see_copay_history(client):
    res = client.get("/api/v1/copay/resident/1/history", headers=OTHER_GUARDIAN)
    assert res.status_code == 403


def test_copay_still_counts_visits_already_reimbursed_and_archived(client):
    """공단 환급까지 끝나 자동 보관된 청구도 이용자 본인부담금은 받아야 한다 (보관 여부로 빠지면 덜 받게 된다)."""
    session = next(client.app.dependency_overrides[get_db]())
    bill = session.get(models.BillingRecord, 2)
    bill.approval_status = "reimbursed"
    bill.is_archived = True
    session.commit()
    data = client.get("/api/v1/copay/summary?year_month=2026-10", headers=MANAGER).json()
    assert data["invoices"][0]["total_amount"] == 7770


def test_remind_sends_the_unpaid_balance_to_the_guardian_only_until_paid(client, tmp_path):
    test_client = client
    Session = sessionmaker(bind=create_engine(f"sqlite:///{tmp_path / 'test.db'}"))
    manager = auth(1, "center_manager", "manager@test.com")
    caregiver = auth(2, "caregiver", "caregiver1@test.com")
    assert test_client.post("/api/v1/copay/remind", params={"year_month": "2026-10"}, headers=caregiver).status_code == 403
    first = test_client.post("/api/v1/copay/remind", params={"year_month": "2026-10"}, headers=manager).json()["data"]
    assert first["sent"] == 1 and first["no_guardian"] == []
    db = Session()
    note = db.query(models.Notification).filter(models.Notification.kind == "copay_reminder").one()
    assert note.user_id == 3 and "7,770원" in note.message
    db.close()
    test_client.post("/api/v1/copay/1/pay", json={"year_month": "2026-10", "amount": 7770, "payment_method": "계좌이체"}, headers=manager)
    after = test_client.post("/api/v1/copay/remind", params={"year_month": "2026-10"}, headers=manager).json()["data"]
    assert after["sent"] == 0  # 전액 수납되면 더 보내지 않는다
