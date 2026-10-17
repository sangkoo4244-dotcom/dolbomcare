"""수급자 관찰일지와 프로그램 의견수렴·반영 기록: 같은 센터 직원만 쓰고, 의견은 낸 사람과 반영 내용을 함께 남기며, 고치는 것은 작성자나 센터장만 한다."""
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import resident_logs
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@t.kr")
CAREGIVER = auth(2, "caregiver", "c@t.kr")
OTHER_CAREGIVER = auth(4, "caregiver", "d@t.kr")
SOCIAL = auth(3, "social_worker", "s@t.kr")
GUARDIAN = auth(5, "guardian", "g@t.kr")
OTHER_CENTER = auth(7, "caregiver", "o@t.kr")
TODAY = date.today().isoformat()


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'rl.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A센터"), models.Center(id=2, name="B센터"),
        models.User(id=1, email="m@t.kr", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@t.kr", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=3, email="s@t.kr", full_name="사회복지사", role="social_worker", center_id=1),
        models.User(id=4, email="d@t.kr", full_name="다른요양사", role="caregiver", center_id=1),
        models.User(id=5, email="g@t.kr", full_name="보호자", role="guardian", center_id=1),
        models.User(id=7, email="o@t.kr", full_name="타센터요양사", role="caregiver", center_id=2),
        models.Resident(id=1, center_id=1, name="김이용", age=80, health_status="stable", care_grade=2, client_type="일반"),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(resident_logs.router, prefix="/api/v1/resident-logs")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def obs(**kw):
    return {"resident_id": 1, "log_date": TODAY, "kind": "observation", "content": "식사량이 평소보다 적음", **kw}


def fb(**kw):
    return {"resident_id": 1, "log_date": TODAY, "kind": "feedback", "source": "보호자",
            "content": "야간 방문 시간을 늦춰 달라는 요청", "action": "다음 달 일정에 반영", **kw}


def test_observation_create_and_list(env):
    assert env.post("/api/v1/resident-logs", json=obs(), headers=CAREGIVER).status_code == 200
    r = env.get("/api/v1/resident-logs?resident_id=1&kind=observation", headers=SOCIAL)
    data = r.json()["data"]
    assert data["resident_name"] == "김이용" and len(data["items"]) == 1
    assert data["items"][0]["author_name"] == "요양사" and data["items"][0]["action"] == ""


def test_feedback_keeps_source_and_action_and_kinds_are_separate(env):
    assert env.post("/api/v1/resident-logs", json=fb(), headers=SOCIAL).status_code == 200
    assert env.get("/api/v1/resident-logs?resident_id=1&kind=observation", headers=SOCIAL).json()["data"]["items"] == []
    item = env.get("/api/v1/resident-logs?resident_id=1&kind=feedback", headers=SOCIAL).json()["data"]["items"][0]
    assert item["source"] == "보호자" and item["action"] == "다음 달 일정에 반영"


def test_feedback_requires_source_and_observation_drops_it(env):
    assert env.post("/api/v1/resident-logs", json=fb(source=None), headers=SOCIAL).status_code == 400
    assert env.post("/api/v1/resident-logs", json=obs(source="보호자"), headers=CAREGIVER).status_code == 200
    item = env.get("/api/v1/resident-logs?resident_id=1&kind=observation", headers=CAREGIVER).json()["data"]["items"][0]
    assert item["source"] == ""


def test_blank_content_refused(env):
    assert env.post("/api/v1/resident-logs", json=obs(content="  "), headers=CAREGIVER).status_code == 400


def test_guardian_and_other_center_refused(env):
    assert env.post("/api/v1/resident-logs", json=obs(), headers=GUARDIAN).status_code == 403
    assert env.get("/api/v1/resident-logs?resident_id=1&kind=observation", headers=GUARDIAN).status_code == 403
    assert env.get("/api/v1/resident-logs?resident_id=1&kind=observation", headers=OTHER_CENTER).status_code == 404
    assert env.post("/api/v1/resident-logs", json=obs(), headers=OTHER_CENTER).status_code == 404


def test_only_author_or_manager_can_edit(env):
    env.post("/api/v1/resident-logs", json=obs(), headers=CAREGIVER)
    lid = env.get("/api/v1/resident-logs?resident_id=1&kind=observation", headers=MANAGER).json()["data"]["items"][0]["id"]
    assert env.put(f"/api/v1/resident-logs/{lid}", json=obs(content="수정"), headers=OTHER_CAREGIVER).status_code == 403
    assert env.put(f"/api/v1/resident-logs/{lid}", json=obs(content="작성자 수정"), headers=CAREGIVER).status_code == 200
    assert env.put(f"/api/v1/resident-logs/{lid}", json=obs(content="센터장 수정"), headers=MANAGER).status_code == 200
    assert env.get("/api/v1/resident-logs?resident_id=1&kind=observation", headers=MANAGER).json()["data"]["items"][0]["content"] == "센터장 수정"
