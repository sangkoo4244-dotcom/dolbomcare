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


MANAGER = auth(1, "center_manager", "m@test.com")
CAREGIVER = auth(2, "caregiver", "c@test.com")
OTHER_CAREGIVER = auth(3, "caregiver", "c2@test.com")
GUARDIAN = auth(9, "guardian", "g@test.com")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([models.Center(id=1, name="센터"), models.Center(id=2, name="다른센터"),
                models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
                models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1),
                models.User(id=3, email="c2@test.com", full_name="요양사2", role="caregiver", center_id=1),
                models.User(id=9, email="g@test.com", full_name="보호자", role="guardian", center_id=1),
                models.Resident(id=1, center_id=1, name="김이용"), models.Resident(id=3, center_id=2, name="타센터")])
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


def body(**kw):
    base = {"resident_id": 1, "occurred_date": date.today().isoformat(), "incident_type": "fall",
            "description": "화장실에서 미끄러져 넘어짐", "action_taken": "부축해 앉히고 통증 확인 후 센터에 연락"}
    base.update(kw)
    return base


def test_caregiver_report_notifies_manager_and_flags_missing_followup(env):
    db, client = env
    res = client.post("/api/v1/incidents", json=body(), headers=CAREGIVER).json()["data"]
    assert res["incident_type_label"] == "낙상" and len(res["issues"]) == 2
    assert db.query(models.Notification).filter(models.Notification.user_id == 1, models.Notification.kind == "incident_reported").count() == 1


def test_validation(env):
    _, client = env
    post = lambda **kw: client.post("/api/v1/incidents", json=body(**kw), headers=MANAGER).status_code
    assert post(description="넘어짐") == 400
    assert post(incident_type="x") == 400
    assert post(occurred_date=(date.today() + timedelta(days=1)).isoformat()) == 400
    assert post(resident_id=3) == 404


def test_progress_clears_issues_and_late_notice_is_flagged(env):
    _, client = env
    rid = client.post("/api/v1/incidents", json=body(), headers=MANAGER).json()["data"]["id"]
    ok = client.put(f"/api/v1/incidents/{rid}/progress", json={"guardian_notified_date": date.today().isoformat(), "prevention": "화장실 미끄럼 방지 매트 설치"}, headers=MANAGER).json()["data"]
    assert ok["issues"] == []
    old = client.post("/api/v1/incidents", json=body(occurred_date=(date.today() - timedelta(days=5)).isoformat()), headers=MANAGER).json()["data"]["id"]
    late = client.put(f"/api/v1/incidents/{old}/progress", json={"guardian_notified_date": date.today().isoformat(), "prevention": "보행 보조기 사용"}, headers=MANAGER).json()["data"]
    assert any("늦었습니다" in i for i in late["issues"])
    assert client.put(f"/api/v1/incidents/{old}/progress", json={"guardian_notified_date": (date.today() - timedelta(days=9)).isoformat()}, headers=MANAGER).status_code == 400


def test_visibility_and_roles(env):
    _, client = env
    client.post("/api/v1/incidents", json=body(), headers=CAREGIVER)
    assert len(client.get("/api/v1/incidents", headers=MANAGER).json()["reports"]) == 1
    assert len(client.get("/api/v1/incidents", headers=CAREGIVER).json()["reports"]) == 1
    assert client.get("/api/v1/incidents", headers=OTHER_CAREGIVER).json()["reports"] == []
    assert client.get("/api/v1/incidents", headers=GUARDIAN).status_code == 403
    rid = client.get("/api/v1/incidents", headers=MANAGER).json()["reports"][0]["id"]
    assert client.put(f"/api/v1/incidents/{rid}/progress", json={"prevention": "x"}, headers=CAREGIVER).status_code == 403
