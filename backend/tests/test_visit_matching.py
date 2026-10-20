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

DAY = datetime(2026, 10, 27)  # 미래 날짜: 지난 날짜면 "예정" 대신 "미기록"이 되어 오늘 날짜에 따라 결과가 달라짐


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
    # 화면의 '기록 보기'가 보여 줄 실제 기록 내용: 계획이 아니라 저장된 기록이어야 한다
    assert items[1]["record"]["id"] == 2 and items[1]["record"]["duration_minutes"] == 60
    assert items[1]["record"]["resident_id"] == items[1]["resident_id"]  # 같은 이용자의 기록이어야 한다


def test_plan_with_record_but_no_departure_is_not_complete(setup):
    db_session = setup.Session()
    s = db_session.query(models.Schedule).filter(models.Schedule.id == 1).first()
    s.left_at = None
    db_session.add(models.DailyRecord(id=2, caregiver_id=2, resident_id=1, recorded_date=DAY.replace(hour=9, minute=30), duration_minutes=60))
    db_session.commit()
    db_session.close()
    items = items_by_schedule(setup)
    assert items[1]["state"] != "완료"


def test_record_chosen_for_a_planned_visit_links_to_it_even_outside_the_time_window(setup):
    items = items_by_schedule(setup)
    planned = next(i for i in items.values() if i["planned"])
    db_session = setup.Session()
    # 기록 시각이 방문 시간대(시작 60분 전 ~ 종료 3시간 후) 밖이어도, 화면에서 고른 방문이면 그 방문에 붙는다
    db_session.add(models.DailyRecord(id=77, caregiver_id=2, resident_id=planned["resident_id"],
                                      recorded_date=DAY.replace(hour=20), duration_minutes=60, schedule_id=planned["schedule_id"]))
    db_session.commit()
    db_session.close()
    after = items_by_schedule(setup)[planned["schedule_id"]]
    assert after["daily_record_id"] == 77 and after["record"]["id"] == 77
