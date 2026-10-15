from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import billing
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MGR_1 = auth(1, "center_manager", "m1@test.com")
MGR_2 = auth(2, "center_manager", "m2@test.com")
CG_1 = auth(3, "caregiver", "c1@test.com")
WHO = {"user_id": 2, "user_role": "center_manager"}


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'b.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="가센터"), models.Center(id=2, name="나센터"),
        models.User(id=1, email="m1@test.com", full_name="가센터장", role="center_manager", center_id=1),
        models.User(id=2, email="m2@test.com", full_name="나센터장", role="center_manager", center_id=2),
        models.User(id=3, email="c1@test.com", full_name="가요양", role="caregiver", center_id=1),
        models.Resident(id=1, center_id=1, name="김일", care_grade=3, client_type="일반"),
    ])
    db.flush()
    db.add(models.BillingRecord(id=1, caregiver_id=3, resident_id=1, center_id=1, amount=48470, total_cost=57020, approval_status="pending",
                                status="pending", service_type="basic_care", recorded_date=datetime.now(), year_month=datetime.now().strftime("%Y-%m")))
    db.commit()
    app = FastAPI()
    app.include_router(billing.router, prefix="/api/v1/billing")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


@pytest.mark.parametrize("method,path,body", [
    ("post", "/api/v1/billing/1/approve", WHO),
    ("post", "/api/v1/billing/1/reject", {**WHO, "reason": "다른 센터가 반려"}),
    ("post", "/api/v1/billing/1/submit-to-nhis", WHO),
    ("post", "/api/v1/billing/1/confirm-reimbursement", WHO),
    ("patch", "/api/v1/billing/1/cancel-nhis-submission", WHO),
    ("patch", "/api/v1/billing/1", {**WHO, "approval_status": "draft"}),
    ("delete", "/api/v1/billing/1", None),
])
def test_another_centers_manager_cannot_touch_the_bill(env, method, path, body):
    db, client = env
    kwargs = {"headers": MGR_2} if body is None else {"headers": MGR_2, "json": body}
    r = getattr(client, method)(path, **kwargs)
    assert r.status_code in (403, 404), (path, r.status_code, r.text)
    bill = db.query(models.BillingRecord).filter_by(id=1).one()
    db.refresh(bill)
    assert bill.approval_status == "pending" and bill.amount == 48470


def test_own_centers_manager_still_can_approve_and_reject(env):
    db, client = env
    who = {"user_id": 1, "user_role": "center_manager"}
    assert client.post("/api/v1/billing/1/approve", json=who, headers=MGR_1).status_code == 200
    assert client.post("/api/v1/billing/1/reject", json={**who, "reason": "시간 확인"}, headers=MGR_1).status_code == 200


def test_listing_is_limited_to_my_center_even_if_another_center_id_is_asked(env):
    _, client = env
    mine = client.get("/api/v1/billing/?center_id=1", headers=MGR_1).json()
    assert [r["id"] for r in mine["records"]] == [1] if isinstance(mine, dict) else [r["id"] for r in mine] == [1]
    for query in ("?center_id=1", ""):
        other = client.get("/api/v1/billing/" + query, headers=MGR_2).json()
        rows = other["records"] if isinstance(other, dict) else other
        assert rows == []


def test_legacy_aggregates_and_creation_are_manager_only_and_scoped(env):
    db, client = env
    ym = datetime.now().strftime("%Y-%m")
    assert client.get(f"/api/v1/billing/monthly/{ym}", headers=MGR_1).json()["total_records"] == 1
    assert client.get(f"/api/v1/billing/monthly/{ym}", headers=MGR_2).json()["total_records"] == 0
    assert client.get(f"/api/v1/billing/monthly/{ym}", headers=CG_1).status_code == 403
    assert client.get("/api/v1/billing/today", headers=CG_1).status_code == 403
    body = {"caregiver_id": 3, "resident_id": 1, "service_type": "basic_care", "recorded_date": datetime.now().isoformat()}
    assert client.post("/api/v1/billing/record", json=body, headers=MGR_2).status_code == 404
