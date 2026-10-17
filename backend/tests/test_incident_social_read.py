"""사회복지사는 사고 보고를 센터 전체로 열람만 할 수 있고, 작성·재발방지 입력은 못 한다."""
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import incidents
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@t.kr")
CAREGIVER_A = auth(2, "caregiver", "c@t.kr")
CAREGIVER_B = auth(4, "caregiver", "d@t.kr")
SOCIAL = auth(3, "social_worker", "s@t.kr")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'inc.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A센터"),
        models.User(id=1, email="m@t.kr", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@t.kr", full_name="요양사A", role="caregiver", center_id=1),
        models.User(id=3, email="s@t.kr", full_name="사회복지사", role="social_worker", center_id=1),
        models.User(id=4, email="d@t.kr", full_name="요양사B", role="caregiver", center_id=1),
        models.Resident(id=1, center_id=1, name="김이용", age=80, health_status="stable", care_grade=2, client_type="일반"),
        models.IncidentReport(id=1, center_id=1, resident_id=1, reporter_id=2, occurred_date=date.today(),
                              incident_type="fall", description="화장실에서 넘어짐", action_taken="병원 진료"),
        models.IncidentReport(id=2, center_id=1, resident_id=1, reporter_id=4, occurred_date=date.today(),
                              incident_type="medication", description="투약 시간 착오", action_taken="보호자 연락"),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(incidents.router, prefix="/api/v1/incidents")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def test_social_worker_sees_all_center_incidents(env):
    _, client = env
    r = client.get("/api/v1/incidents", headers=SOCIAL)
    assert r.status_code == 200
    assert {x["id"] for x in r.json()["reports"]} == {1, 2}


def test_caregiver_still_sees_only_own_incidents(env):
    _, client = env
    r = client.get("/api/v1/incidents", headers=CAREGIVER_A)
    assert {x["id"] for x in r.json()["reports"]} == {1}


def test_social_worker_cannot_create_or_update_incidents(env):
    _, client = env
    body = {"resident_id": 1, "occurred_date": date.today().isoformat(), "incident_type": "fall",
            "description": "x", "action_taken": "y"}
    assert client.post("/api/v1/incidents", json=body, headers=SOCIAL).status_code == 403
    assert client.put("/api/v1/incidents/1/progress", json={"prevention": "x"}, headers=SOCIAL).status_code == 403
