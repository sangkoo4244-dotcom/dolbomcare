"""연차·휴가 신청: 직원이 신청하면 센터장이 승인·반려하고, 결과를 신청자에게 알린다. 다른 센터는 볼 수 없다."""
from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import leave
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@t.kr")
CAREGIVER = auth(2, "caregiver", "c@t.kr")
SOCIAL = auth(3, "social_worker", "s@t.kr")
OTHER_MANAGER = auth(7, "center_manager", "o@t.kr")
FUTURE = (date.today() + timedelta(days=5)).isoformat()


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'leave.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A센터"), models.Center(id=2, name="B센터"),
        models.User(id=1, email="m@t.kr", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@t.kr", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=3, email="s@t.kr", full_name="사회복지사", role="social_worker", center_id=1),
        models.User(id=7, email="o@t.kr", full_name="타센터장", role="center_manager", center_id=2),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(leave.router, prefix="/api/v1/leave")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def test_caregiver_requests_and_manager_sees_it_with_visit_count(env):
    db, client = env
    r = client.post("/api/v1/leave/requests", json={"leave_date": FUTURE, "leave_type": "annual", "reason": "가족 행사"}, headers=CAREGIVER)
    assert r.status_code == 200, r.text
    pending = client.get("/api/v1/leave/requests", headers=MANAGER).json()["data"]
    assert len(pending) == 1 and pending[0]["staff_name"] == "요양사" and pending[0]["status"] == "pending"
    assert pending[0]["scheduled_visits"] == 0
    notes = db.query(models.Notification).filter(models.Notification.user_id == 1, models.Notification.kind == "leave_requested").all()
    assert len(notes) == 1


def test_duplicate_and_past_dates_are_refused(env):
    _, client = env
    assert client.post("/api/v1/leave/requests", json={"leave_date": FUTURE, "leave_type": "annual"}, headers=CAREGIVER).status_code == 200
    assert client.post("/api/v1/leave/requests", json={"leave_date": FUTURE, "leave_type": "annual"}, headers=CAREGIVER).status_code == 409
    past = (date.today() - timedelta(days=1)).isoformat()
    assert client.post("/api/v1/leave/requests", json={"leave_date": past, "leave_type": "annual"}, headers=CAREGIVER).status_code == 400


def test_approve_notifies_staff_and_removes_from_pending(env):
    db, client = env
    rid = client.post("/api/v1/leave/requests", json={"leave_date": FUTURE, "leave_type": "half_am"}, headers=CAREGIVER).json()["data"]["id"]
    assert client.post(f"/api/v1/leave/requests/{rid}/approve", json={}, headers=MANAGER).status_code == 200
    assert client.get("/api/v1/leave/requests", headers=MANAGER).json()["data"] == []
    approved = client.get("/api/v1/leave/requests?status=approved", headers=MANAGER).json()["data"]
    assert approved[0]["decided_by_name"] == "센터장"
    assert db.query(models.Notification).filter(models.Notification.user_id == 2, models.Notification.kind == "leave_decided").count() == 1


def test_reject_needs_reason_and_reason_reaches_staff(env):
    db, client = env
    rid = client.post("/api/v1/leave/requests", json={"leave_date": FUTURE, "leave_type": "annual"}, headers=CAREGIVER).json()["data"]["id"]
    assert client.post(f"/api/v1/leave/requests/{rid}/reject", json={"note": " "}, headers=MANAGER).status_code == 400
    assert client.post(f"/api/v1/leave/requests/{rid}/reject", json={"note": "그날 방문 집중"}, headers=MANAGER).status_code == 200
    note = db.query(models.Notification).filter(models.Notification.user_id == 2, models.Notification.kind == "leave_decided").first()
    assert "그날 방문 집중" in note.message


def test_caregiver_can_cancel_only_pending_own_request(env):
    _, client = env
    rid = client.post("/api/v1/leave/requests", json={"leave_date": FUTURE, "leave_type": "annual"}, headers=CAREGIVER).json()["data"]["id"]
    assert client.post(f"/api/v1/leave/requests/{rid}/cancel", headers=SOCIAL).status_code == 404
    assert client.post(f"/api/v1/leave/requests/{rid}/cancel", headers=CAREGIVER).status_code == 200
    mine = client.get("/api/v1/leave/requests/mine", headers=CAREGIVER).json()["data"]
    assert mine[0]["status"] == "cancelled"


def test_other_center_manager_cannot_decide(env):
    _, client = env
    rid = client.post("/api/v1/leave/requests", json={"leave_date": FUTURE, "leave_type": "annual"}, headers=CAREGIVER).json()["data"]["id"]
    assert client.post(f"/api/v1/leave/requests/{rid}/approve", json={}, headers=OTHER_MANAGER).status_code == 404
    assert client.get("/api/v1/leave/requests", headers=OTHER_MANAGER).json()["data"] == []


def test_social_worker_can_request_but_not_approve(env):
    _, client = env
    assert client.post("/api/v1/leave/requests", json={"leave_date": FUTURE, "leave_type": "other"}, headers=SOCIAL).status_code == 200
    rid = client.get("/api/v1/leave/requests", headers=MANAGER).json()["data"][0]["id"]
    assert client.post(f"/api/v1/leave/requests/{rid}/approve", json={}, headers=SOCIAL).status_code == 403


def test_pending_request_lists_affected_visits(env):
    db, client = env
    from datetime import datetime as dt
    db.add(models.Resident(id=1, center_id=1, name="김이용", age=80, health_status="stable", care_grade=2, client_type="일반"))
    db.add(models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=dt.combine(date.today() + timedelta(days=5), dt.min.time()).replace(hour=10, minute=30), duration_minutes=60, status="planned"))
    db.commit()
    client.post("/api/v1/leave/requests", json={"leave_date": FUTURE, "leave_type": "annual"}, headers=CAREGIVER)
    row = client.get("/api/v1/leave/requests", headers=MANAGER).json()["data"][0]
    assert row["scheduled_visits"] == 1
    assert row["visits"] == [{"time": "10:30", "resident_name": "김이용", "duration_minutes": 60}]
