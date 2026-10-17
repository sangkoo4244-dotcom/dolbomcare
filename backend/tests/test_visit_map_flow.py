"""방문 지도 흐름: 오늘 일정이 시간 순서로 번호가 매겨지고, 좌표가 있으면 점이 찍히며, 주소만 있거나 주소가 없으면 점 없이 목록에 나온다.
요양보호사는 자기 방문만, 센터장은 센터 전체를 본다. (카카오 주소 변환은 키가 필요해 여기서는 키 없음 상태로 검사)"""
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
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@t.kr")
CAREGIVER = auth(2, "caregiver", "c@t.kr")
OTHER_CAREGIVER = auth(4, "caregiver", "d@t.kr")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'vm.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    today = datetime.now().replace(second=0, microsecond=0)
    at = lambda h: today.replace(hour=h, minute=0)
    db.add_all([
        models.Center(id=1, name="A센터"),
        models.User(id=1, email="m@t.kr", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@t.kr", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=4, email="d@t.kr", full_name="다른요양사", role="caregiver", center_id=1),
        models.Resident(id=1, center_id=1, name="좌표있음", age=80, health_status="stable", care_grade=2, client_type="일반",
                        address="서울시 A구 1길 1", latitude=37.5, longitude=127.0),
        models.Resident(id=2, center_id=1, name="주소만", age=80, health_status="stable", care_grade=2, client_type="일반",
                        address="서울시 B구 2길 2"),
        models.Resident(id=3, center_id=1, name="주소없음", age=80, health_status="stable", care_grade=2, client_type="일반"),
        models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=at(10), duration_minutes=60, status="planned"),
        models.Schedule(caregiver_id=2, resident_id=2, center_id=1, scheduled_date=at(9), duration_minutes=60, status="planned"),
        models.Schedule(caregiver_id=2, resident_id=3, center_id=1, scheduled_date=at(14), duration_minutes=60, status="planned"),
        models.Schedule(caregiver_id=4, resident_id=1, center_id=1, scheduled_date=at(11), duration_minutes=60, status="planned"),
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
    return TestClient(app)


def test_caregiver_sees_own_visits_in_time_order_with_points_where_available(env):
    visits = env.get("/api/v1/visit-map/day", headers=CAREGIVER).json()["data"]["visits"]
    assert [v["resident"] for v in visits] == ["주소만", "좌표있음", "주소없음"]  # 09시, 10시, 14시
    assert [v["number"] for v in visits] == [1, 2, 3]
    assert visits[1]["latitude"] == 37.5 and visits[1]["longitude"] == 127.0  # 저장된 좌표 사용
    assert visits[0]["latitude"] is None and visits[0]["address"] == "서울시 B구 2길 2"  # 키 없음 → 점 없이 주소만
    assert visits[2]["address"] is None  # 주소 없음 → 목록에만


def test_manager_sees_whole_center(env):
    visits = env.get("/api/v1/visit-map/day", headers=MANAGER).json()["data"]["visits"]
    assert len(visits) == 4
    assert [v["time"] for v in visits] == ["09:00", "10:00", "11:00", "14:00"]


def test_other_caregiver_sees_only_their_visit(env):
    visits = env.get("/api/v1/visit-map/day", headers=OTHER_CAREGIVER).json()["data"]["visits"]
    assert [v["resident"] for v in visits] == ["좌표있음"] and visits[0]["number"] == 1
