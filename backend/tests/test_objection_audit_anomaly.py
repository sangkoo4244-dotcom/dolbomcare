"""허위 기록 방지 3종 검증: 보호자 이의 제기(청구 승인 보류), 기록 수정·삭제 이력, 이상 패턴 찾기."""
from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.anomaly import find_anomalies
from app.api import anomalies, billing, records, visit_objections
from app.api.users import create_access_token
from app.database import Base, get_db

NOW = datetime.now()
YESTERDAY = NOW - timedelta(days=1)


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MANAGER = auth(1, "center_manager", "m@test.com")
CAREGIVER = auth(2, "caregiver", "c@test.com")
GUARDIAN = auth(5, "guardian", "g@test.com")
OTHER_GUARDIAN = auth(6, "guardian", "g2@test.com")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'vaa.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.Center(id=1, name="센터"))
    db.add(models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1))
    db.add(models.User(id=3, email="c3@test.com", full_name="요양사3", role="caregiver", center_id=1))
    db.add(models.User(id=5, email="g@test.com", full_name="보호자", role="guardian"))
    db.add(models.User(id=6, email="g2@test.com", full_name="다른 보호자", role="guardian"))
    db.add(models.Resident(id=1, center_id=1, name="김이용", care_grade=2, guardian_id=5))
    db.add(models.Resident(id=2, center_id=1, name="박이용", care_grade=3))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(records.router, prefix="/api/v1/records")
    app.include_router(billing.router, prefix="/api/v1/billing")
    app.include_router(visit_objections.router, prefix="/api/v1/visit-objections")
    app.include_router(anomalies.router, prefix="/api/v1/anomalies")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return Session, TestClient(app)


def _add_record(Session, rid, caregiver_id, resident_id, when, minutes=60, schedule_id=None, status="pending"):
    s = Session()
    s.add(models.DailyRecord(id=rid, caregiver_id=caregiver_id, resident_id=resident_id, recorded_date=when,
                             service_type="basic_care", duration_minutes=minutes, schedule_id=schedule_id,
                             benefit_type="home_care"))
    s.add(models.BillingRecord(id=rid, daily_record_id=rid, caregiver_id=caregiver_id, resident_id=resident_id,
                               center_id=1, service_type="basic_care", amount=67043, approval_status=status,
                               recorded_date=when))
    s.commit()
    s.close()


# ---- 1. 보호자 이의 제기 ----

def test_only_the_linked_guardian_can_report_and_future_dates_are_refused(env):
    _, client = env
    body = {"resident_id": 1, "visit_date": YESTERDAY.date().isoformat(), "memo": "그 날 방문 없었습니다"}
    assert client.post("/api/v1/visit-objections", json=body, headers=OTHER_GUARDIAN).status_code == 403
    assert client.post("/api/v1/visit-objections", json=body, headers=CAREGIVER).status_code == 403
    future = {**body, "visit_date": (NOW + timedelta(days=3)).date().isoformat()}
    assert client.post("/api/v1/visit-objections", json=future, headers=GUARDIAN).status_code == 400
    assert client.post("/api/v1/visit-objections", json=body, headers=GUARDIAN).status_code == 200


def test_open_objection_holds_approval_until_resolved(env):
    Session, client = env
    _add_record(Session, 10, 2, 1, YESTERDAY)
    client.post("/api/v1/visit-objections", json={"resident_id": 1, "visit_date": YESTERDAY.date().isoformat(),
                                                  "memo": "방문 없었음"}, headers=GUARDIAN)
    held = client.post("/api/v1/billing/10/approve", headers=MANAGER,
                       json={"user_id": 1, "user_role": "center_manager", "reason": "확인"})
    assert held.status_code == 400
    assert "신고" in held.json()["detail"]

    objection_id = client.get("/api/v1/visit-objections", headers=MANAGER).json()["objections"][0]["id"]
    assert client.post(f"/api/v1/visit-objections/{objection_id}/resolve", headers=MANAGER,
                       json={"resolution_note": "방문 기록과 일정 확인, 실제 방문 맞음"}).status_code == 200
    assert client.post(f"/api/v1/visit-objections/{objection_id}/resolve", headers=MANAGER,
                       json={"resolution_note": "again"}).status_code == 400
    ok = client.post("/api/v1/billing/10/approve", headers=MANAGER,
                     json={"user_id": 1, "user_role": "center_manager", "reason": "확인"})
    assert ok.status_code == 200


def test_guardian_sees_own_objections_and_caregiver_cannot_see_center_list(env):
    _, client = env
    client.post("/api/v1/visit-objections", json={"resident_id": 1, "visit_date": YESTERDAY.date().isoformat(),
                                                  "memo": "방문 없었음"}, headers=GUARDIAN)
    mine = client.get("/api/v1/visit-objections/mine", headers=GUARDIAN).json()["objections"]
    assert len(mine) == 1 and mine[0]["status"] == "open"
    assert client.get("/api/v1/visit-objections", headers=CAREGIVER).status_code == 403


# ---- 2. 기록 수정·삭제 이력 ----

def test_update_and_delete_leave_before_and_after_history(env):
    Session, client = env
    _add_record(Session, 20, 2, 1, YESTERDAY, status="draft")
    s = Session()
    s.query(models.DailyRecord).filter(models.DailyRecord.id == 20).first().notes = "처음 메모"
    s.commit()
    s.close()

    r = client.patch("/api/v1/records/daily/20", headers=CAREGIVER, json={"notes": "고친 메모"})
    assert r.status_code == 200, r.text
    r = client.delete("/api/v1/records/daily/20", headers=CAREGIVER)
    assert r.status_code == 200, r.text

    logs = client.get("/api/v1/records/audit", params={"record_id": 20}, headers=MANAGER).json()["logs"]
    actions = [l["action"] for l in logs]
    assert "update" in actions and "delete" in actions
    update = next(l for l in logs if l["action"] == "update")
    assert update["before"]["notes"] == "처음 메모"
    assert update["after"]["notes"] == "고친 메모"
    delete = next(l for l in logs if l["action"] == "delete")
    assert delete["before"]["notes"] == "고친 메모"  # 지워져도 지우기 직전 내용이 남는다


def test_audit_log_is_manager_only(env):
    _, client = env
    assert client.get("/api/v1/records/audit", headers=CAREGIVER).status_code == 403


# ---- 3. 이상 패턴 ----

def test_overlapping_records_for_two_residents_are_flagged(env):
    Session, _ = env
    base = NOW.replace(hour=10, minute=0, second=0, microsecond=0) - timedelta(days=2)
    _add_record(Session, 31, 2, 1, base, minutes=60)
    _add_record(Session, 32, 2, 2, base + timedelta(minutes=30), minutes=60)
    s = Session()
    found = find_anomalies(s, 1, NOW)
    s.close()
    assert any(f["kind"] == "overlap" and f["caregiver_id"] == 2 for f in found)


def test_same_resident_back_to_back_is_not_overlap(env):
    Session, _ = env
    base = NOW.replace(hour=10, minute=0, second=0, microsecond=0) - timedelta(days=2)
    _add_record(Session, 41, 2, 1, base, minutes=60)
    _add_record(Session, 42, 2, 1, base + timedelta(minutes=30), minutes=60)
    s = Session()
    found = find_anomalies(s, 1, NOW)
    s.close()
    assert not any(f["kind"] == "overlap" for f in found)


def test_repeated_unplanned_records_are_flagged_and_listed_for_manager(env):
    Session, client = env
    for i in range(3):
        _add_record(Session, 50 + i, 3, 1, NOW - timedelta(days=2 + i), minutes=60, schedule_id=None)
    found = client.get("/api/v1/anomalies", headers=MANAGER).json()["findings"]
    assert any(f["kind"] == "unplanned" and f["caregiver_id"] == 3 and f["count"] == 3 for f in found)


def test_record_on_approved_leave_day_is_flagged(env):
    Session, _ = env
    day = (NOW - timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0)
    s = Session()
    s.add(models.LeaveRequest(center_id=1, staff_id=2, leave_date=day.date(), leave_type="annual", status="approved"))
    s.commit()
    s.close()
    _add_record(Session, 60, 2, 1, day, minutes=60)
    s = Session()
    found = find_anomalies(s, 1, NOW)
    s.close()
    assert any(f["kind"] == "leave_day" and f["caregiver_id"] == 2 for f in found)
