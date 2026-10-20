"""시급 방식 급여: 제공 시간 × 시급으로 산정하고, 기본 비율 방식 요양사의 금액은 그대로 둔다.
제공 시간이 바뀌면 확정 명세가 '재확정 필요'로 표시되고, 재확정하면 새 시간 기준으로 바뀐다."""
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
from app.salary_rules import calc_deductions, calc_hourly_base

YM = "2026-10"


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MANAGER = auth(1, "center_manager", "manager@test.com")


def visit(db, caregiver_id, minutes, day=5):
    db.add(models.DailyRecord(resident_id=1, caregiver_id=caregiver_id, recorded_date=datetime(2026, 10, day),
                              duration_minutes=minutes, service_type="basic_care"))


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'hourly.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.Center(id=1, name="테스트센터"))
    db.add(models.User(id=1, email="manager@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="hourly@test.com", full_name="시급요양사", role="caregiver", center_id=1,
                       pay_method="hourly", hourly_wage=12000))
    db.add(models.User(id=3, email="ratio@test.com", full_name="비율요양사", role="caregiver", center_id=1, wage_ratio=100))
    db.add(models.Resident(id=1, center_id=1, name="김1", age=80, health_status="stable", care_grade=1, client_type="일반"))
    db.add(models.BillingRecord(id=1, caregiver_id=2, resident_id=1, center_id=1, service_type="basic_care",
                                amount=1000000, approval_status="approved", year_month=YM, recorded_date=datetime(2026, 10, 5)))
    db.add(models.BillingRecord(id=2, caregiver_id=3, resident_id=1, center_id=1, service_type="basic_care",
                                amount=500000, approval_status="approved", year_month=YM, recorded_date=datetime(2026, 10, 5)))
    visit(db, 2, 90)
    visit(db, 2, 90, day=6)
    visit(db, 3, 60)
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(statements.router, prefix="/api/v1/statements")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    client = TestClient(app)
    client.Session = Session
    return client


def test_hourly_base_is_minutes_times_wage_rounded():
    assert calc_hourly_base(180, 12000) == 36000
    assert calc_hourly_base(100, 10000) == 16667  # 1,000,000 / 60 = 16666.67 → 16667


def test_hourly_caregiver_is_paid_by_visit_minutes_not_billing(client):
    r = client.post("/api/v1/statements/confirm", json={"caregiver_id": 2, "year_month": YM}, headers=MANAGER)
    assert r.status_code == 200
    s = r.json()["statement"]
    assert s["pay_method"] == "hourly" and s["work_minutes"] == 180
    assert s["wage_ratio"] is None and s["wage_base"] == 36000
    assert s["net"] == 36000 - calc_deductions(36000)["total_deduction"]


def test_ratio_caregiver_keeps_the_old_calculation(client):
    s = client.post("/api/v1/statements/confirm", json={"caregiver_id": 3, "year_month": YM}, headers=MANAGER).json()["statement"]
    assert s["pay_method"] == "ratio" and s["work_minutes"] is None
    assert s["wage_ratio"] == 100 and s["wage_base"] == 500000


def test_more_visit_minutes_after_confirming_means_reconfirm(client):
    client.post("/api/v1/statements/confirm", json={"caregiver_id": 2, "year_month": YM}, headers=MANAGER)
    # 아무 것도 안 바뀌었으면 재확정을 막는다
    assert client.post("/api/v1/statements/reconfirm", json={"caregiver_id": 2, "year_month": YM}, headers=MANAGER).status_code == 400
    db = client.Session()
    visit(db, 2, 60, day=7)
    db.commit()
    db.close()
    row = [c for c in client.get(f"/api/v1/statements/status?year_month={YM}", headers=MANAGER).json()["caregivers"]
           if c["caregiver_id"] == 2][0]
    assert row["stale"] is True
    re = client.post("/api/v1/statements/reconfirm", json={"caregiver_id": 2, "year_month": YM}, headers=MANAGER)
    assert re.status_code == 200
    assert re.json()["statement"]["work_minutes"] == 240 and re.json()["statement"]["wage_base"] == 48000


def test_unconfirmed_hourly_preview_uses_current_minutes(client):
    row = [c for c in client.get(f"/api/v1/statements/status?year_month={YM}", headers=MANAGER).json()["caregivers"]
           if c["caregiver_id"] == 2][0]
    assert row["confirmed"] is False and row["pay_method"] == "hourly" and row["wage_base"] == 36000

