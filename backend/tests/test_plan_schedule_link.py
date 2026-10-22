"""계획서가 없는 이용자에게 방문을 잡으면 알린다(막지는 않는다). 그 날짜 이전 계획서가 있으면 알림이 없다."""
from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import schedule
from app.api.users import create_access_token
from app.database import Base, get_db
from tests.test_visit_benefit_api import env  # noqa: F401  (env 픽스처 재사용)

MGR = {"Authorization": "Bearer " + create_access_token({"sub": "m@e.com", "uid": 1, "role": "center_manager"}, timedelta(hours=1))}
VISIT = date(2026, 11, 10)


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'plan.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="센터A"),
        models.User(id=1, email="m@e.com", hashed_password="x", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@e.com", hashed_password="x", full_name="요양사", role="caregiver", center_id=1),
        models.Resident(id=1, center_id=1, name="계획없음", care_grade=1, client_type="일반"),
        models.Resident(id=2, center_id=1, name="계획있음", care_grade=1, client_type="일반"),
        models.CarePlan(center_id=1, resident_id=2, author_id=1, written_date=date(2026, 11, 1), service_type="방문요양"),
    ])
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
    test_client = TestClient(app)
    return test_client


def body(resident_id):
    return {"caregiver_id": 2, "resident_id": resident_id, "center_id": 1,
            "scheduled_date": datetime(VISIT.year, VISIT.month, VISIT.day, 10).isoformat(),
            "duration_minutes": 60, "service_type": "basic_care"}


def test_visit_for_a_resident_without_a_plan_is_allowed_but_warned(client):
    data = client.post("/api/v1/schedule/", json=body(1), headers=MGR).json()
    assert data["status"] == "success"
    assert data["plan_warning"] and "계획서" in data["plan_warning"]


def test_visit_after_a_plan_was_written_has_no_warning(client):
    assert client.post("/api/v1/schedule/", json=body(2), headers=MGR).json()["plan_warning"] is None


def test_recurring_visits_warn_when_no_plan_exists_yet(client):
    res = client.post("/api/v1/schedule/recurring", headers=MGR, json={
        "caregiver_id": 2, "resident_id": 1, "start_date": "2026-11-10", "end_date": "2026-11-11",
        "weekdays": [0, 1, 2, 3, 4, 5, 6], "start_time": "10:00", "duration_minutes": 60,
    })
    assert res.status_code == 200, res.text
    assert res.json()["plan_warning"] is not None



def test_record_without_a_plan_still_saves_and_warns(env):
    from tests.test_visit_benefit_api import CG_A, payload
    db, client = env
    r = client.post("/api/v1/records/create", json=payload(benefit_type="home_care", duration_minutes=60), headers=CG_A)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["plan_warning"] and "계획서" in r.json()["data"]["plan_warning"]
    assert db.query(models.DailyRecord).count() == 1


def test_record_after_a_plan_has_no_warning(env):
    from tests.test_visit_benefit_api import CG_A, payload
    db, client = env
    db.add(models.CarePlan(center_id=1, resident_id=1, author_id=1, written_date=date(2020, 1, 1)))
    db.commit()
    r = client.post("/api/v1/records/create", json=payload(benefit_type="home_care", duration_minutes=60), headers=CG_A)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["plan_warning"] is None
