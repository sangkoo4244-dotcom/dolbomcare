"""출퇴근: 직원은 자기 기록만 남기고, 센터장은 방문과 출근이 어긋난 날을 본다."""
from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import attendance
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MANAGER = auth(1, "center_manager", "m@test.com")
CG = auth(2, "caregiver", "c@test.com")
GUARDIAN = auth(9, "guardian", "g@test.com")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'att.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=9, email="g@test.com", full_name="보호자", role="guardian", center_id=None),
        models.Resident(id=1, center_id=1, name="이용자", care_grade=2),
        # 방문 기록은 있는데 출근 기록은 없는 날
        models.DailyRecord(resident_id=1, caregiver_id=2, recorded_date=datetime(2026, 10, 5, 10, 0), duration_minutes=60, care_items="cleaning"),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(attendance.router, prefix="/api/v1/attendance")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def test_clock_in_and_out_and_no_double_clock_in(env):
    _, client = env
    assert client.post("/api/v1/attendance/clock-in", headers=CG).status_code == 200
    assert client.post("/api/v1/attendance/clock-in", headers=CG).status_code == 400  # 이미 출근 중
    assert client.post("/api/v1/attendance/clock-out", headers=CG).status_code == 200
    assert client.post("/api/v1/attendance/clock-out", headers=CG).status_code == 400  # 출근 기록 없음
    mine = client.get("/api/v1/attendance/me", params={"year_month": date.today().strftime("%Y-%m")}, headers=CG).json()["data"]
    assert len(mine["items"]) == 1 and mine["open"] is False


def test_guardian_cannot_clock_and_month_format_is_checked(env):
    _, client = env
    assert client.post("/api/v1/attendance/clock-in", headers=GUARDIAN).status_code == 403
    assert client.get("/api/v1/attendance/me", params={"year_month": "2026-13"}, headers=CG).status_code == 400


def test_manager_sees_visits_without_clock_in(env):
    _, client = env
    data = client.get("/api/v1/attendance/center", params={"year_month": "2026-10"}, headers=MANAGER).json()["data"]
    row = next(r for r in data["staff"] if r["staff_id"] == 2)
    assert row["visit_days_without_clock_in"] == 1  # 10/5 방문은 있는데 출근 기록 없음
    assert client.get("/api/v1/attendance/center", params={"year_month": "2026-10"}, headers=CG).status_code == 403
