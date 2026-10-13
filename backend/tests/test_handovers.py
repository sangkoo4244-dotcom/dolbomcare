from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import handovers
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@test.com")
CG_A = auth(2, "caregiver", "a@test.com")
CG_B = auth(3, "caregiver", "b@test.com")
CG_C = auth(4, "caregiver", "c@test.com")
GUARDIAN = auth(9, "guardian", "g@test.com")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([models.Center(id=1, name="센터"), models.Center(id=2, name="다른센터"),
                models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
                models.User(id=2, email="a@test.com", full_name="요양사A", role="caregiver", center_id=1),
                models.User(id=3, email="b@test.com", full_name="요양사B", role="caregiver", center_id=1),
                models.User(id=4, email="c@test.com", full_name="요양사C", role="caregiver", center_id=1),
                models.User(id=5, email="x@test.com", full_name="타센터", role="caregiver", center_id=2),
                models.User(id=9, email="g@test.com", full_name="보호자", role="guardian", center_id=1),
                models.Resident(id=1, center_id=1, name="김이용"), models.Resident(id=3, center_id=2, name="타센터이용자")])
    db.commit()
    app = FastAPI()
    app.include_router(handovers.router, prefix="/api/v1/handovers")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def body(**kw):
    base = {"resident_id": 1, "to_caregiver_id": 3, "content": "최근 무릎이 아파 보행 시 부축 필요, 아침 식사는 죽을 선호"}
    base.update(kw)
    return base


def test_note_reaches_only_recipient_and_notifies(env):
    db, client = env
    client.post("/api/v1/handovers", json=body(), headers=CG_A)
    assert db.query(models.Notification).filter(models.Notification.user_id == 3, models.Notification.kind == "handover_received").count() == 1
    mine = client.get("/api/v1/handovers", headers=CG_B).json()
    assert len(mine["notes"]) == 1 and mine["unread_for_me"] == 1 and mine["notes"][0]["author_name"] == "요양사A"
    assert client.get("/api/v1/handovers", headers=CG_C).json()["notes"] == []        # 제3의 요양보호사에게는 안 보임
    assert len(client.get("/api/v1/handovers", headers=CG_A).json()["notes"]) == 1    # 쓴 사람은 봄
    assert len(client.get("/api/v1/handovers", headers=MANAGER).json()["notes"]) == 1


def test_only_recipient_can_acknowledge_once(env):
    _, client = env
    nid = client.post("/api/v1/handovers", json=body(), headers=CG_A).json()["data"]["id"]
    assert client.post(f"/api/v1/handovers/{nid}/ack", headers=CG_C).status_code == 404
    assert client.post(f"/api/v1/handovers/{nid}/ack", headers=CG_A).status_code == 404
    assert client.post(f"/api/v1/handovers/{nid}/ack", headers=CG_B).status_code == 200
    assert client.post(f"/api/v1/handovers/{nid}/ack", headers=CG_B).status_code == 200
    got = client.get("/api/v1/handovers", headers=CG_B).json()
    assert got["unread_for_me"] == 0 and got["notes"][0]["acknowledged_at"]


def test_validation_and_tenant(env):
    _, client = env
    post = lambda **kw: client.post("/api/v1/handovers", json=body(**kw), headers=CG_A).status_code
    assert post(content="무릎 아픔") == 400
    assert post(resident_id=3) == 404
    assert post(to_caregiver_id=5) == 404
    assert post(to_caregiver_id=2) == 404
    assert post(to_caregiver_id=None) == 200          # 받는 사람 없이 센터에 남기는 것도 가능
    assert client.post("/api/v1/handovers", json=body(), headers=GUARDIAN).status_code == 403
    assert client.get("/api/v1/handovers", headers=GUARDIAN).status_code == 403
