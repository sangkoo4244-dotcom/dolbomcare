"""확인이 필요한 기록: 오늘 일정에 없는 기록(계획 외)과 오늘이 아닌 날짜의 소급 기록은
센터장이 실제 방문 여부를 적어야 승인된다. 일정이 있고 오늘 기록인 정상 건은 막지 않는다."""
from datetime import datetime, timedelta
from datetime import date as date_cls

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import billing
from app.api.users import create_access_token
from app.database import Base, get_db
from app.review import gate_reason_for

NOW = datetime(2026, 10, 19, 10, 0)


def test_no_schedule_is_unplanned():
    assert gate_reason_for(None, None, NOW) == "계획 외 기록"


def test_scheduled_same_day_record_is_not_gated():
    assert gate_reason_for(object(), None, NOW) is None
    assert gate_reason_for(object(), NOW, NOW) is None


def test_backdated_record_is_gated_even_with_schedule():
    assert gate_reason_for(object(), NOW - timedelta(days=2), NOW) == "소급 기록"


def test_unplanned_and_backdated_are_both_listed():
    assert gate_reason_for(None, NOW - timedelta(days=1), NOW) == "계획 외 기록 · 소급 기록"


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gate.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.Center(id=1, name="테스트센터"))
    db.add(models.User(id=1, email="manager@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="caregiver1@test.com", full_name="요양사1", role="caregiver", center_id=1))
    db.add(models.BillingRecord(id=1, caregiver_id=2, resident_id=1, center_id=1, service_type="basic_care",
                                amount=67043, approval_status="pending", recorded_date=datetime(2026, 10, 19),
                                gate_reason="계획 외 기록"))
    db.add(models.BillingRecord(id=2, caregiver_id=2, resident_id=1, center_id=1, service_type="basic_care",
                                amount=67043, approval_status="pending", recorded_date=datetime(2026, 10, 19)))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(billing.router, prefix="/api/v1/billing")

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    c = TestClient(app)
    c.headers.update(auth(1, "center_manager", "manager@test.com"))
    return c


def test_gated_claim_needs_manager_note_to_approve(client):
    r = client.post("/api/v1/billing/1/approve", json={"user_id": 1, "user_role": "center_manager", "reason": ""})
    assert r.status_code == 400
    assert "확인" in r.json()["detail"]
    ok = client.post("/api/v1/billing/1/approve", json={"user_id": 1, "user_role": "center_manager", "reason": "보호자 확인, 방문함"})
    assert ok.status_code == 200
    assert ok.json()["approval_status"] == "approved"


def test_normal_claim_still_approves_without_note(client):
    r = client.post("/api/v1/billing/2/approve", json={"user_id": 1, "user_role": "center_manager"})
    assert r.status_code == 200
