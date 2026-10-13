from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import visit_precheck
from app.api.users import create_access_token
from app.database import Base, get_db
from app.visit_precheck import run_precheck

NOW = datetime(2026, 10, 13, 12, 0)


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def db_and_client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.Center(id=1, name="센터"))
    db.add(models.Center(id=2, name="다른센터"))
    db.add(models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1))
    db.add(models.Resident(id=1, center_id=1, name="만료자", recognition_end=date(2026, 9, 1)))
    db.add(models.Resident(id=2, center_id=1, name="임박자", recognition_end=date(2026, 10, 25)))
    db.add(models.Resident(id=3, center_id=1, name="정상자", recognition_end=date(2028, 1, 1)))
    db.add(models.Resident(id=4, center_id=2, name="타센터", recognition_end=date(2020, 1, 1)))
    db.commit()
    app = FastAPI()
    app.include_router(visit_precheck.router, prefix="/api/v1/visit-precheck")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def sched(db, rid, start, duration=60, arrived=None, left=None):
    db.add(models.Schedule(caregiver_id=2, resident_id=rid, center_id=1, scheduled_date=start,
                           duration_minutes=duration, arrived_at=arrived, left_at=left, status="scheduled"))
    db.commit()


def types(db, **kw):
    return [(i["type"], i["resident"]) for i in run_precheck(db, 1, now=NOW, **kw)["issues"]]


def test_recognition_expired_and_expiring_only_for_own_center(db_and_client):
    db, _ = db_and_client
    found = types(db)
    assert ("recognition_expired", "만료자") in found
    assert ("recognition_expiring", "임박자") in found
    assert not any(name in ("정상자", "타센터") for kind, name in found if kind.startswith("recognition"))
    assert ("care_plan_missing", "정상자") in found and not any(name == "타센터" for _, name in found)


def test_missing_record_missing_end_gap_and_over_10h(db_and_client):
    db, _ = db_and_client
    base = NOW - timedelta(days=2)
    sched(db, 3, base.replace(hour=9))                                                    # 도착·기록 없음
    sched(db, 3, base.replace(hour=11), arrived=base.replace(hour=11))                    # 퇴실 없음
    sched(db, 3, base.replace(hour=13), duration=60,
          arrived=base.replace(hour=13), left=base.replace(hour=14, minute=45))           # 45분 차이
    sched(db, 3, base.replace(hour=1), duration=60,
          arrived=base.replace(hour=1), left=base.replace(hour=12))                       # 11시간
    sched(db, 3, base.replace(hour=15), duration=60,
          arrived=base.replace(hour=15), left=base.replace(hour=16, minute=10))           # 10분 차이는 정상
    kinds = [t for t, _ in types(db)]
    assert kinds.count("missing_record") == 1
    assert kinds.count("missing_end") == 1
    assert kinds.count("time_gap") == 1
    assert kinds.count("over_10h") == 1


def test_future_and_old_schedules_are_ignored(db_and_client):
    db, _ = db_and_client
    sched(db, 3, NOW + timedelta(days=1))
    sched(db, 3, NOW - timedelta(days=30))
    assert [t for t, _ in types(db) if t == "missing_record"] == []


def test_endpoint_manager_only(db_and_client):
    _, client = db_and_client
    assert client.get("/api/v1/visit-precheck", headers=auth(1, "center_manager", "m@test.com")).status_code == 200
    assert client.get("/api/v1/visit-precheck", headers=auth(2, "caregiver", "c@test.com")).status_code == 403
