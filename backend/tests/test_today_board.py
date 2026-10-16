"""오늘 방문 현황판: 도착·퇴실·기록으로 상태를 나누고, 취소 건은 빼며, 센터장만 본다."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import today_board
from app.api.users import create_access_token
from app.database import Base, get_db

DAY = "2026-10-10"


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MANAGER = auth(1, "center_manager", "m@test.com")
CG = auth(2, "caregiver", "c@test.com")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'tb.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    d = datetime(2026, 10, 10)
    db.add_all([
        models.Center(id=1, name="A"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1),
        models.Resident(id=1, center_id=1, name="이용자1", care_grade=2),
        models.Resident(id=2, center_id=1, name="이용자2", care_grade=2),
    ])
    db.flush()
    done = models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=d.replace(hour=9), duration_minutes=60, status="scheduled")
    working = models.Schedule(caregiver_id=2, resident_id=2, center_id=1, scheduled_date=d.replace(hour=10), duration_minutes=60, status="scheduled",
                              arrived_at=d.replace(hour=10, minute=2))
    missed = models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=d.replace(hour=11), duration_minutes=60, status="scheduled")
    left = models.Schedule(caregiver_id=2, resident_id=2, center_id=1, scheduled_date=d.replace(hour=13), duration_minutes=60, status="scheduled",
                           arrived_at=d.replace(hour=13), left_at=d.replace(hour=14))
    cancelled = models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=d.replace(hour=15), duration_minutes=60, status="cancelled")
    db.add_all([done, working, missed, left, cancelled])
    db.flush()
    db.add(models.DailyRecord(resident_id=1, caregiver_id=2, recorded_date=d.replace(hour=9), duration_minutes=60, care_items="cleaning", schedule_id=done.id))
    db.commit()
    app = FastAPI()
    app.include_router(today_board.router, prefix="/api/v1/today-board")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_board_splits_visits_by_state_and_skips_cancelled(env):
    data = env.get("/api/v1/today-board", params={"day": DAY}, headers=MANAGER).json()["data"]
    by_time = {r["planned"]: r["status"] for r in data["rows"]}
    assert by_time == {"09:00": "recorded", "10:00": "in_progress", "11:00": "check", "13:00": "left_unrecorded"}
    assert data["total"] == 4
    assert data["record_rate"] == 25


def test_empty_day_has_no_rows_and_caregiver_is_refused(env):
    data = env.get("/api/v1/today-board", params={"day": "2099-01-01"}, headers=MANAGER).json()["data"]
    assert data["total"] == 0 and data["record_rate"] is None
    assert env.get("/api/v1/today-board", params={"day": DAY}, headers=CG).status_code == 403
