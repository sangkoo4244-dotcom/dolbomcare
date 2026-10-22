"""승인된 연차는 그 날 방문 배정을 막고, 반차와 미승인 신청은 막지 않는다. 승인 후에도 같은 규칙이 적용된다."""
from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import schedule
from app.api.users import create_access_token
from app.database import Base, get_db

LEAVE_DAY = date(2026, 11, 2)
OPEN_DAY = date(2026, 11, 3)
MGR = {"Authorization": "Bearer " + create_access_token({"sub": "m@e.com", "uid": 1, "role": "center_manager"}, timedelta(hours=1))}


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'leave.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="센터A"),
        models.User(id=1, email="m@e.com", hashed_password="x", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@e.com", hashed_password="x", full_name="요양사", role="caregiver", center_id=1),
        models.Resident(id=1, center_id=1, name="김1", care_grade=1, client_type="일반"),
        models.LeaveRequest(center_id=1, staff_id=2, leave_date=LEAVE_DAY, leave_type="annual", status="approved"),
        models.LeaveRequest(center_id=1, staff_id=2, leave_date=OPEN_DAY, leave_type="half_am", status="approved"),
        models.LeaveRequest(center_id=1, staff_id=2, leave_date=date(2026, 11, 4), leave_type="annual", status="pending"),
    ])
    db.commit()
    db.close()
    app = FastAPI()
    app.include_router(schedule.router, prefix="/api/v1/schedule")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    test_client = TestClient(app)
    test_client.Session = Session
    return test_client


def body(day, hour=10):
    return {"caregiver_id": 2, "resident_id": 1, "center_id": 1,
            "scheduled_date": datetime(day.year, day.month, day.day, hour).isoformat(),
            "duration_minutes": 60, "service_type": "basic_care"}


def test_manual_visit_on_an_approved_annual_leave_day_is_refused(client):
    res = client.post("/api/v1/schedule/", json=body(LEAVE_DAY), headers=MGR)
    assert res.status_code == 409 and "휴가" in res.json()["detail"]


def test_visit_on_another_day_is_still_allowed(client):
    assert client.post("/api/v1/schedule/", json=body(OPEN_DAY), headers=MGR).status_code == 200


def test_half_day_and_pending_leave_do_not_block(client):
    half = date(2026, 11, 3)
    assert client.post("/api/v1/schedule/", json=body(half), headers=MGR).status_code == 200
    assert client.post("/api/v1/schedule/", json=body(date(2026, 11, 4)), headers=MGR).status_code == 200


def test_recurring_visits_skip_approved_leave_days_and_say_so(client):
    res = client.post("/api/v1/schedule/recurring", headers=MGR, json={
        "caregiver_id": 2, "resident_id": 1, "start_date": "2026-11-02", "end_date": "2026-11-03",
        "weekdays": [0, 1, 2, 3, 4, 5, 6], "start_time": "10:00", "duration_minutes": 60,
    })
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["created"] == 1 and data["skipped_leave"] == 1


def test_approving_a_plan_on_a_day_that_later_became_leave_is_refused(client):
    db = client.Session()
    plan = models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=datetime(2026, 11, 2, 10),
                           duration_minutes=60, status="proposed")
    db.add(plan)
    db.commit()
    plan_id = plan.id
    db.close()
    res = client.post(f"/api/v1/schedule/{plan_id}/approve", json={"user_id": 1, "user_role": "center_manager"}, headers=MGR)
    assert res.status_code == 409
