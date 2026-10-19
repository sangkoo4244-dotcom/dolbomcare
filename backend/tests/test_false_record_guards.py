"""허위 기록을 막는 장치 검증: 제출·승인된 청구가 있는 기록은 삭제할 수 없어야 하고,
요양보호사는 자기 기록만 지울 수 있어야 한다. 초안 기록은 정상적으로 지울 수 있어야 한다."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import records
from app.api.users import create_access_token
from app.database import Base, get_db

NOW = datetime(2026, 10, 19, 10, 0)


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


CAREGIVER = auth(2, "caregiver", "c@test.com")
MANAGER = auth(1, "center_manager", "m@test.com")


def _record(db, rid, status):
    db.add(models.DailyRecord(id=rid, caregiver_id=2, resident_id=1, recorded_date=NOW,
                              service_type="basic_care", duration_minutes=60, benefit_type="home_care"))
    db.add(models.BillingRecord(id=rid, daily_record_id=rid, caregiver_id=2, resident_id=1, center_id=1,
                                service_type="basic_care", amount=67043, approval_status=status, recorded_date=NOW))


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'guard.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.Center(id=1, name="센터"))
    db.add(models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1))
    db.add(models.Resident(id=1, center_id=1, name="김이용", care_grade=2))
    _record(db, 1, "approved")   # 승인된 청구가 있는 기록
    _record(db, 2, "draft")      # 아직 제출 전인 기록
    _record(db, 3, "approved")   # 일괄 삭제 시도용
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(records.router, prefix="/api/v1/records")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return Session, TestClient(app)


def _exists(Session, model, rid):
    s = Session()
    found = s.query(model).filter(model.id == rid).first() is not None
    s.close()
    return found


def test_caregiver_cannot_delete_record_with_approved_claim(env):
    Session, client = env
    r = client.delete("/api/v1/records/daily/1", headers=CAREGIVER)
    assert r.status_code == 400
    assert _exists(Session, models.DailyRecord, 1)
    assert _exists(Session, models.BillingRecord, 1)


def test_manager_cannot_silently_delete_approved_claim_either(env):
    Session, client = env
    r = client.delete("/api/v1/records/daily/1", headers=MANAGER)
    assert r.status_code == 400
    assert _exists(Session, models.BillingRecord, 1)


def test_caregiver_can_still_delete_own_draft_record(env):
    Session, client = env
    r = client.delete("/api/v1/records/daily/2", headers=CAREGIVER)
    assert r.status_code == 200
    assert not _exists(Session, models.DailyRecord, 2)


def test_batch_delete_skips_approved_claim_records(env):
    Session, client = env
    r = client.post("/api/v1/records/batch-delete", json={"record_ids": [1, 3], "user_id": 2, "user_role": "caregiver"}, headers=CAREGIVER)
    assert r.status_code == 200
    assert _exists(Session, models.DailyRecord, 1)
    assert _exists(Session, models.DailyRecord, 3)
