"""수급자별 이용 일정 지도와 전체 방문 일정 리포트: 기간 안의 방문을 센는지, 센터장만 보는지, 상태가 오늘 방문 현황과 같은지 본다."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import visit_map
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MANAGER = auth(1, "center_manager", "m@test.com")
CG = auth(2, "caregiver", "c@test.com")
D = datetime(2026, 10, 10)


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'vr.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=3, email="c2@test.com", full_name="요양사2", role="caregiver", center_id=1),
        models.Resident(id=1, center_id=1, name="이용자1", care_grade=2, latitude=37.5, longitude=127.0, address="서울 중구 1"),
        models.Resident(id=2, center_id=1, name="이용자2", care_grade=2, latitude=37.6, longitude=127.1, address="서울 중구 2"),
    ])
    db.flush()
    done = models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=D.replace(hour=9), duration_minutes=60, status="scheduled")
    missed = models.Schedule(caregiver_id=2, resident_id=2, center_id=1, scheduled_date=D.replace(hour=11), duration_minutes=60, status="scheduled")
    other = models.Schedule(caregiver_id=3, resident_id=2, center_id=1, scheduled_date=D.replace(hour=13), duration_minutes=60, status="scheduled")
    cancelled = models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=D.replace(hour=15), duration_minutes=60, status="cancelled")
    outside = models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=datetime(2026, 11, 2, 9), duration_minutes=60, status="scheduled")
    db.add_all([done, missed, other, cancelled, outside])
    db.flush()
    db.add(models.DailyRecord(resident_id=1, caregiver_id=2, recorded_date=D.replace(hour=9), duration_minutes=60, care_items="cleaning", schedule_id=done.id))
    db.commit()
    db.close()
    app = FastAPI()
    app.include_router(visit_map.router, prefix="/api/v1/visit-map")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_report_counts_period_by_caregiver_and_status(env):
    data = env.get("/api/v1/visit-map/report", params={"start": "2026-10-10", "end": "2026-10-10"}, headers=MANAGER).json()["data"]
    assert data["total"] == 3  # 취소와 기간 밖 방문은 뺀다
    assert data["record_rate"] == 33
    assert data["totals"]["recorded"] == 1
    by = {r["caregiver"]: r for r in data["by_caregiver"]}
    assert by["요양사"] == {"caregiver": "요양사", "total": 2, "recorded": 1, "open": 1}
    assert by["요양사2"]["total"] == 1


def test_report_is_manager_only_and_checks_period(env):
    assert env.get("/api/v1/visit-map/report", params={"start": "2026-10-10", "end": "2026-10-10"}, headers=CG).status_code == 403
    assert env.get("/api/v1/visit-map/report", params={"start": "2026-10-11", "end": "2026-10-10"}, headers=MANAGER).status_code == 400


def test_resident_map_counts_visits_and_filters_by_caregiver(env):
    data = env.get("/api/v1/visit-map/resident-map", params={"start": "2026-10-10", "end": "2026-10-10"}, headers=MANAGER).json()["data"]
    counts = {r["resident"]: r["count"] for r in data["residents"]}
    assert counts == {"이용자2": 2, "이용자1": 1}
    assert data["residents"][0]["resident"] == "이용자2"  # 방문이 많은 수급자가 위
    only = env.get("/api/v1/visit-map/resident-map", params={"start": "2026-10-10", "end": "2026-10-10", "caregiver_id": 3}, headers=MANAGER).json()["data"]
    assert [(r["resident"], r["count"]) for r in only["residents"]] == [("이용자2", 1)]
    assert env.get("/api/v1/visit-map/resident-map", params={"start": "2026-10-10", "end": "2026-10-10"}, headers=CG).status_code == 403
