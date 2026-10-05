from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import schedule
from app.api.users import create_access_token
from app.database import Base, get_db

DAY = datetime(2026, 10, 20)


@pytest.fixture
def setup(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.Center(id=1, name="테스트센터"))
    db.add(models.User(id=2, email="caregiver1@test.com", full_name="요양사1", role="caregiver", center_id=1))
    db.add(models.Resident(id=1, center_id=1, name="김1", age=80, health_status="stable", care_grade=1, client_type="일반"))
    # 오전 9시 방문 (실제 09:00~10:00)
    db.add(models.Schedule(
        id=1, caregiver_id=2, resident_id=1, center_id=1, scheduled_date=DAY.replace(hour=9),
        duration_minutes=60, status="scheduled", arrived_at=DAY.replace(hour=9), left_at=DAY.replace(hour=10),
    ))
    # 오후 3시 방문 (아직 도착 전)
    db.add(models.Schedule(
        id=2, caregiver_id=2, resident_id=1, center_id=1, scheduled_date=DAY.replace(hour=15),
        duration_minutes=60, status="scheduled",
    ))
    # 오전 7시 36분에 먼저 저장된 기록 (방문 시간 전)
    db.add(models.DailyRecord(id=1, caregiver_id=2, resident_id=1, recorded_date=DAY.replace(hour=7, minute=36), duration_minutes=60))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(schedule.router, prefix="/api/v1/schedule")

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.Session = Session
    return client


def auth():
    token = create_access_token({"sub": "caregiver1@test.com", "uid": 2, "role": "caregiver"}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


def items_by_schedule(client):
    body = client.get(
        "/api/v1/schedule/caregiver-view",
        params={"caregiver_id": 2, "year_month": "2026-10", "user_id": 2, "user_role": "caregiver"},
        headers=auth(),
    ).json()
    return {i["schedule_id"]: i for i in body["items"] if i["schedule_id"]}


def test_record_saved_before_visit_does_not_complete_later_plan(setup):
    items = items_by_schedule(setup)
    assert items[2]["daily_record_id"] is None
    assert items[2]["state"] == "예정"


def test_record_inside_visit_window_completes_the_plan(setup):
    db_session = setup.Session()
    db_session.add(models.DailyRecord(id=2, caregiver_id=2, resident_id=1, recorded_date=DAY.replace(hour=9, minute=30), duration_minutes=60))
    db_session.commit()
    db_session.close()
    items = items_by_schedule(setup)
    assert items[1]["daily_record_id"] == 2
    assert items[1]["state"] == "완료"


def test_plan_with_record_but_no_departure_is_not_complete(setup):
    db_session = setup.Session()
    s = db_session.query(models.Schedule).filter(models.Schedule.id == 1).first()
    s.left_at = None
    db_session.add(models.DailyRecord(id=2, caregiver_id=2, resident_id=1, recorded_date=DAY.replace(hour=9, minute=30), duration_minutes=60))
    db_session.commit()
    db_session.close()
    items = items_by_schedule(setup)
    assert items[1]["state"] != "완료"
