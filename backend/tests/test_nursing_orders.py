"""방문간호지시서 보관: 센터장이 올리고, 같은 센터 직원이 보며, 파일 형식·크기를 막는다."""
import base64
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import nursing_orders
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@test.com")
CAREGIVER = auth(2, "caregiver", "c@test.com")
OTHER_MANAGER = auth(5, "center_manager", "o@test.com")
GUARDIAN = auth(9, "guardian", "g@test.com")
PNG = base64.b64encode(b"\x89PNG-fake").decode()


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'no.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A"), models.Center(id=2, name="B"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=5, email="o@test.com", full_name="타센터장", role="center_manager", center_id=2),
        models.User(id=9, email="g@test.com", full_name="보호자", role="guardian", center_id=None),
        models.Resident(id=1, center_id=1, name="김이용", care_grade=2),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(nursing_orders.router, prefix="/api/v1/nursing-orders")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def body(**kw):
    base = {"resident_id": 1, "issued_date": "2026-10-01", "order_no": "2026-001", "physician": "○○의원 김의사"}
    base.update(kw)
    return base


def test_manager_keeps_order_and_caregiver_can_read_it(env):
    _, client = env
    r = client.post("/api/v1/nursing-orders", json=body(file_name="지시서.png", file_type="image/png", file_data=PNG), headers=MANAGER)
    assert r.status_code == 200, r.text
    oid = r.json()["data"]["id"]
    rows = client.get("/api/v1/nursing-orders", params={"resident_id": 1}, headers=CAREGIVER).json()["data"]
    assert rows[0]["order_no"] == "2026-001" and rows[0]["has_file"] is True
    f = client.get(f"/api/v1/nursing-orders/{oid}/file", headers=CAREGIVER).json()["data"]
    assert f["file_data"] == PNG and f["file_type"] == "image/png"


def test_file_type_and_size_are_checked(env):
    _, client = env
    assert client.post("/api/v1/nursing-orders", json=body(file_type="text/html", file_data=PNG), headers=MANAGER).status_code == 400
    big = base64.b64encode(b"x" * (3 * 1024 * 1024 + 1)).decode()
    assert client.post("/api/v1/nursing-orders", json=body(file_type="image/png", file_data=big), headers=MANAGER).status_code == 400
    assert client.post("/api/v1/nursing-orders", json=body(file_type="image/png", file_data="!!not-base64!!"), headers=MANAGER).status_code == 400


def test_only_manager_writes_and_others_are_refused(env):
    _, client = env
    assert client.post("/api/v1/nursing-orders", json=body(), headers=CAREGIVER).status_code == 403
    assert client.post("/api/v1/nursing-orders", json=body(), headers=GUARDIAN).status_code == 403
    assert client.get("/api/v1/nursing-orders", params={"resident_id": 1}, headers=GUARDIAN).status_code == 403


def test_other_center_cannot_see_or_delete(env):
    _, client = env
    oid = client.post("/api/v1/nursing-orders", json=body(), headers=MANAGER).json()["data"]["id"]
    assert client.get("/api/v1/nursing-orders", params={"resident_id": 1}, headers=OTHER_MANAGER).status_code == 404
    assert client.delete(f"/api/v1/nursing-orders/{oid}", headers=OTHER_MANAGER).status_code == 404
    assert client.delete(f"/api/v1/nursing-orders/{oid}", headers=MANAGER).status_code == 200


def test_claim_helper_flags_a_nursing_visit_without_a_filed_order(env):
    db, client = env
    from app.api import claim_helper
    from datetime import datetime
    from app.models import BillingRecord, DailyRecord
    month = datetime.now().strftime("%Y-%m")
    rec = DailyRecord(resident_id=1, caregiver_id=2, recorded_date=datetime.now().replace(day=1, hour=10, minute=0, second=0, microsecond=0),
                      duration_minutes=30, benefit_type="home_nursing", care_items="cleaning", nursing_order_note="지시서 확인 메모")
    db.add(rec)
    db.flush()
    db.add(BillingRecord(daily_record_id=rec.id, caregiver_id=2, resident_id=1, center_id=1, amount=10, total_cost=42880,
                         approval_status="approved", recorded_date=rec.recorded_date, year_month=month, benefit_type="home_nursing"))
    db.commit()
    app = FastAPI()
    app.include_router(claim_helper.router, prefix="/api/v1/claim-helper")
    app.dependency_overrides[get_db] = client.app.dependency_overrides[get_db]
    c = TestClient(app)
    flags = [f for r in c.get("/api/v1/claim-helper", params={"year_month": month}, headers=MANAGER).json()["residents"] for v in r["visits"] for f in v["flags"]]
    assert "nursing_order_not_filed" in flags
    # 지시서를 보관하면 이 플래그는 사라진다
    client.post("/api/v1/nursing-orders", json=body(), headers=MANAGER)
    flags = [f for r in c.get("/api/v1/claim-helper", params={"year_month": month}, headers=MANAGER).json()["residents"] for v in r["visits"] for f in v["flags"]]
    assert "nursing_order_not_filed" not in flags
