"""방문 지도: 시간 순서로 번호를 매기고, 요양보호사는 자기 방문만 보며, 좌표는 한 번만 구해 저장한다."""
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

DAY = "2026-10-12"


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MANAGER = auth(1, "center_manager", "m@test.com")
CG = auth(2, "caregiver", "c@test.com")
CG_OTHER = auth(3, "caregiver", "o@test.com")


@pytest.fixture
def env(tmp_path, monkeypatch):
    calls = []

    def fake_geocode(address):
        calls.append(address)
        return (37.5 + len(calls) / 1000, 127.0)

    monkeypatch.setattr(visit_map, "geocode_address", fake_geocode)
    engine = create_engine(f"sqlite:///{tmp_path / 'map.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    d = datetime(2026, 10, 12)
    db.add_all([
        models.Center(id=1, name="A"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=3, email="o@test.com", full_name="다른요양사", role="caregiver", center_id=1),
        models.Resident(id=1, center_id=1, name="이용자1", address="서울 종로구 1"),
        models.Resident(id=2, center_id=1, name="이용자2", address="서울 종로구 2"),
    ])
    db.flush()
    db.add_all([
        models.Schedule(caregiver_id=2, resident_id=2, center_id=1, scheduled_date=d.replace(hour=14), duration_minutes=60, status="scheduled"),
        models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=d.replace(hour=9), duration_minutes=60, status="scheduled"),
        models.Schedule(caregiver_id=3, resident_id=1, center_id=1, scheduled_date=d.replace(hour=10), duration_minutes=60, status="scheduled"),
        models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=d.replace(hour=16), duration_minutes=60, status="cancelled"),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(visit_map.router, prefix="/api/v1/visit-map")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    return TestClient(app), calls


def test_manager_sees_the_day_in_time_order_without_cancelled_visits(env):
    client, _ = env
    visits = client.get("/api/v1/visit-map/day", params={"day": DAY}, headers=MANAGER).json()["data"]["visits"]
    assert [v["time"] for v in visits] == ["09:00", "10:00", "14:00"]
    assert [v["number"] for v in visits] == [1, 2, 3]


def test_caregiver_sees_only_their_own_visits(env):
    client, _ = env
    mine = client.get("/api/v1/visit-map/day", params={"day": DAY}, headers=CG).json()["data"]["visits"]
    assert [v["time"] for v in mine] == ["09:00", "14:00"]
    other = client.get("/api/v1/visit-map/day", params={"day": DAY}, headers=CG_OTHER).json()["data"]["visits"]
    assert [v["time"] for v in other] == ["10:00"]


def test_each_address_is_converted_once_and_then_reused(env):
    client, calls = env
    client.get("/api/v1/visit-map/day", params={"day": DAY}, headers=MANAGER)
    first_count = len(calls)
    assert first_count == 2  # 이용자 1·2의 주소 두 건만 변환
    again = client.get("/api/v1/visit-map/day", params={"day": DAY}, headers=MANAGER).json()["data"]["visits"]
    assert len(calls) == first_count  # 두 번째 조회에서는 다시 바꾸지 않는다
    assert all(v["latitude"] is not None for v in again)


def test_social_worker_sees_home_visit_plans_of_the_day_in_entry_order(env):
    client, _ = env
    from app import models as m
    db_session = client.app.dependency_overrides[visit_map.get_db]()
    db = next(db_session)
    db.add(m.User(id=4, email="s@test.com", full_name="사회복지사", role="social_worker", center_id=1))
    db.add_all([
        m.SocialVisitPlan(center_id=1, resident_id=2, author_id=4, planned_date=datetime(2026, 10, 12).date(), note="상담"),
        m.SocialVisitPlan(center_id=1, resident_id=1, author_id=4, planned_date=datetime(2026, 10, 12).date()),
    ])
    db.commit()
    social = auth(4, "social_worker", "s@test.com")
    visits = client.get("/api/v1/visit-map/day", params={"day": DAY}, headers=social).json()["data"]
    assert visits["kind"] == "social" and [v["resident"] for v in visits["visits"]] == ["이용자2", "이용자1"]
    assert visits["visits"][0]["note"] == "상담"
