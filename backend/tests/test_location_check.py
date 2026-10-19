"""도착·퇴실 위치 확인 검증: 이용자 주소와 휴대폰 위치를 비교하고, 좌표는 저장하지 않으며,
위치가 멀거나 없으면 센터장 확인 대상이 되는지 확인한다."""
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
from app.geo import distance_m, judge
from app.review import gate_reason_for

HOME = (37.5665, 126.9780)
NEAR = (37.5667, 126.9781)   # 약 20m
FAR = (37.5800, 126.9780)    # 약 1.6km
NOW = datetime.now().replace(second=0, microsecond=0)


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MANAGER = auth(1, "center_manager", "m@t.kr")
CAREGIVER = auth(2, "caregiver", "a@t.kr")


def test_distance_is_about_right():
    assert 10 <= distance_m(*HOME, *NEAR) <= 40
    assert 1500 <= distance_m(*HOME, *FAR) <= 1700


def test_judge_outcomes():
    assert judge(*HOME, *NEAR, accuracy=10)[0] == "ok"
    assert judge(*HOME, *FAR, accuracy=10)[0] == "far"
    assert judge(*HOME, None, None, None)[0] == "no_location"
    assert judge(None, None, *NEAR, accuracy=10)[0] == "no_resident_coords"


def test_accuracy_gives_some_room_but_not_unlimited():
    # 약 150m 떨어져 있어도 휴대폰 오차가 100m면 허용한다
    dist = (37.5665 + 0.00135, 126.9780)  # 약 150m
    assert judge(*HOME, *dist, accuracy=100)[0] == "ok"
    assert judge(*HOME, *dist, accuracy=0)[0] == "far"


class _Sched:
    def __init__(self, arrived, check):
        self.arrived_at = arrived
        self.arrive_check = check


def test_far_or_missing_location_needs_manager_confirmation():
    assert gate_reason_for(_Sched(NOW, "far"), None, NOW) == "위치 확인 필요"
    assert gate_reason_for(_Sched(NOW, "no_location"), None, NOW) == "위치 확인 필요"
    assert gate_reason_for(_Sched(NOW, "ok"), None, NOW) is None
    assert gate_reason_for(_Sched(NOW, "no_resident_coords"), None, NOW) is None


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'geo.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.Center(id=1, name="센터"))
    db.add(models.User(id=1, email="m@t.kr", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="a@t.kr", full_name="요양사", role="caregiver", center_id=1))
    db.add(models.Resident(id=1, center_id=1, name="이용자1", care_grade=2, latitude=HOME[0], longitude=HOME[1]))
    db.add(models.Resident(id=2, center_id=1, name="이용자2", care_grade=2))
    db.add(models.Schedule(id=1, caregiver_id=2, resident_id=1, center_id=1, scheduled_date=NOW,
                           duration_minutes=60, status="scheduled"))
    db.add(models.Schedule(id=2, caregiver_id=2, resident_id=2, center_id=1, scheduled_date=NOW,
                           duration_minutes=60, status="scheduled"))
    db.add(models.Schedule(id=3, caregiver_id=2, resident_id=1, center_id=1, scheduled_date=NOW,
                           duration_minutes=60, status="scheduled"))
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
    c = TestClient(app)
    c.Session = Session
    return c


def _check(client, sid):
    s = client.Session()
    row = s.query(models.Schedule).filter(models.Schedule.id == sid).first()
    result = (row.arrive_check, row.arrive_distance_m, row.arrived_at)
    s.close()
    return result


def test_arrival_near_home_is_ok_and_coordinates_are_not_stored(client):
    r = client.post("/api/v1/schedule/1/arrive", headers=CAREGIVER,
                    json={"lat": NEAR[0], "lng": NEAR[1], "accuracy": 10})
    assert r.status_code == 200, r.text
    check, dist, arrived = _check(client, 1)
    assert check == "ok" and dist is not None and arrived is not None
    s = client.Session()
    row = s.query(models.Schedule).filter(models.Schedule.id == 1).first()
    assert not any(isinstance(v, float) and abs(v - NEAR[0]) < 1e-9 for v in row.__dict__.values())
    s.close()


def test_arrival_far_from_home_is_marked_far(client):
    client.post("/api/v1/schedule/1/arrive", headers=CAREGIVER, json={"lat": FAR[0], "lng": FAR[1], "accuracy": 10})
    assert _check(client, 1)[0] == "far"


def test_arrival_without_location_is_marked_no_location(client):
    client.post("/api/v1/schedule/3/arrive", headers=CAREGIVER)
    assert _check(client, 3)[0] == "no_location"


def test_resident_without_coordinates_is_not_judged(client):
    client.post("/api/v1/schedule/2/arrive", headers=CAREGIVER, json={"lat": FAR[0], "lng": FAR[1], "accuracy": 10})
    assert _check(client, 2)[0] == "no_resident_coords"


def test_departure_location_is_checked_too(client):
    client.post("/api/v1/schedule/1/arrive", headers=CAREGIVER, json={"lat": NEAR[0], "lng": NEAR[1], "accuracy": 10})
    client.post("/api/v1/schedule/1/depart", headers=CAREGIVER, json={"lat": FAR[0], "lng": FAR[1], "accuracy": 10})
    s = client.Session()
    row = s.query(models.Schedule).filter(models.Schedule.id == 1).first()
    assert row.depart_check == "far"
    s.close()


def test_record_links_to_the_nearest_visit_of_the_day(client):
    # 같은 이용자의 두 방문(10:00, 15:00). 15시 기록은 아침 방문이 아니라 15시 방문에 연결되어야 한다.
    s = client.Session()
    morning = s.query(models.Schedule).filter(models.Schedule.id == 1).first()
    morning.scheduled_date = NOW.replace(hour=10, minute=0)
    morning.left_at = NOW.replace(hour=10, minute=50)
    afternoon = s.query(models.Schedule).filter(models.Schedule.id == 3).first()
    afternoon.scheduled_date = NOW.replace(hour=15, minute=0)
    s.commit()
    from app.review import find_schedule
    found = find_schedule(s, 2, 1, NOW.replace(hour=15, minute=40))
    s.close()
    assert found is not None and found.id == 3


def test_arrival_for_a_visit_on_another_day_is_refused(client):
    s = client.Session()
    row = s.query(models.Schedule).filter(models.Schedule.id == 1).first()
    row.scheduled_date = NOW + timedelta(days=1)
    s.commit()
    s.close()
    r = client.post("/api/v1/schedule/1/arrive", headers=CAREGIVER, json={"lat": NEAR[0], "lng": NEAR[1], "accuracy": 10})
    assert r.status_code == 400
    assert "당일" in r.json()["detail"]
    assert _check(client, 1)[2] is None


def test_departure_for_a_visit_on_another_day_is_refused(client):
    client.post("/api/v1/schedule/1/arrive", headers=CAREGIVER, json={"lat": NEAR[0], "lng": NEAR[1], "accuracy": 10})
    s = client.Session()
    row = s.query(models.Schedule).filter(models.Schedule.id == 1).first()
    row.scheduled_date = NOW - timedelta(days=1)
    s.commit()
    s.close()
    r = client.post("/api/v1/schedule/1/depart", headers=CAREGIVER, json={"lat": FAR[0], "lng": FAR[1], "accuracy": 10})
    assert r.status_code == 400
    assert "당일" in r.json()["detail"]
