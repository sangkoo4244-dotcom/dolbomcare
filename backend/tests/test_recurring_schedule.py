from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import schedule
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@test.com")
CAREGIVER = auth(2, "caregiver", "c@test.com")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([models.Center(id=1, name="센터"), models.Center(id=2, name="다른센터"),
                models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
                models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1),
                models.User(id=5, email="x@test.com", full_name="타센터요양사", role="caregiver", center_id=2),
                models.Resident(id=1, center_id=1, name="김이용"), models.Resident(id=3, center_id=2, name="타센터")])
    db.commit()
    app = FastAPI()
    app.include_router(schedule.router, prefix="/api/v1/schedule")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def body(**kw):
    base = {"caregiver_id": 2, "resident_id": 1, "weekdays": [0, 2, 4], "start_date": "2026-10-12", "end_date": "2026-10-25",
            "start_time": "09:30", "duration_minutes": 180}
    base.update(kw)
    return base


def test_creates_visits_on_selected_weekdays_and_notifies_caregiver(env):
    db, client = env
    res = client.post("/api/v1/schedule/recurring", json=body(), headers=MANAGER).json()
    assert res["created"] == 6 and res["skipped"] == 0   # 10/12(월) 기준 2주: 월수금 x 2
    rows = db.query(models.Schedule).order_by(models.Schedule.scheduled_date).all()
    assert rows[0].scheduled_date.isoformat() == "2026-10-12T09:30:00" and all(r.status == "scheduled" and r.center_id == 1 for r in rows)
    assert db.query(models.Notification).filter(models.Notification.user_id == 2).count() == 1


def test_running_twice_does_not_duplicate(env):
    db, client = env
    client.post("/api/v1/schedule/recurring", json=body(), headers=MANAGER)
    again = client.post("/api/v1/schedule/recurring", json=body(), headers=MANAGER).json()
    assert again["created"] == 0 and again["skipped"] == 6
    assert db.query(models.Schedule).count() == 6


def test_validation_tenant_and_role(env):
    _, client = env
    post = lambda who=MANAGER, **kw: client.post("/api/v1/schedule/recurring", json=body(**kw), headers=who).status_code
    assert post(weekdays=[]) == 400
    assert post(end_date="2026-10-01") == 400
    assert post(end_date="2027-03-01") == 400
    assert post(start_time="9시") == 400
    assert post(caregiver_id=5) == 404
    assert post(resident_id=3) == 404
    assert post(who=CAREGIVER) == 403
