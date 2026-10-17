"""운영위원회 회의록과 비품 관리대장: 센터장만 쓰고, 다른 센터는 보이지 않으며, 폐기한 비품은 되돌리지 않는다."""
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import committee, equipment
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@t.kr")
OTHER_MANAGER = auth(7, "center_manager", "o@t.kr")
CAREGIVER = auth(2, "caregiver", "c@t.kr")
MEETING = {"meeting_date": date.today().isoformat(), "title": "3분기 운영위원회", "attendees": "센터장, 사회복지사",
           "agenda": "방문 일정 조정", "minutes": "야간 방문 일정 논의", "decisions": "다음 달부터 시행"}


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'cm.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A센터"), models.Center(id=2, name="B센터"),
        models.User(id=1, email="m@t.kr", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@t.kr", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=7, email="o@t.kr", full_name="타센터장", role="center_manager", center_id=2),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(committee.router, prefix="/api/v1/committee")
    app.include_router(equipment.router, prefix="/api/v1/equipment")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_meeting_create_list_update(env):
    assert env.post("/api/v1/committee", json=MEETING, headers=MANAGER).status_code == 200
    rows = env.get("/api/v1/committee", headers=MANAGER).json()["data"]
    assert rows[0]["title"] == "3분기 운영위원회" and rows[0]["author_name"] == "센터장"
    mid = rows[0]["id"]
    assert env.put(f"/api/v1/committee/{mid}", json={**MEETING, "decisions": "수정된 의결"}, headers=MANAGER).status_code == 200
    assert env.get("/api/v1/committee", headers=MANAGER).json()["data"][0]["decisions"] == "수정된 의결"


def test_meeting_title_required_and_other_center_hidden(env):
    assert env.post("/api/v1/committee", json={**MEETING, "title": "  "}, headers=MANAGER).status_code == 400
    env.post("/api/v1/committee", json=MEETING, headers=MANAGER)
    assert env.get("/api/v1/committee", headers=OTHER_MANAGER).json()["data"] == []
    mid = env.get("/api/v1/committee", headers=MANAGER).json()["data"][0]["id"]
    assert env.put(f"/api/v1/committee/{mid}", json=MEETING, headers=OTHER_MANAGER).status_code == 404


def test_caregiver_cannot_use_committee(env):
    assert env.get("/api/v1/committee", headers=CAREGIVER).status_code == 403
    assert env.post("/api/v1/committee", json=MEETING, headers=CAREGIVER).status_code == 403


def test_equipment_register_filter_and_dispose(env):
    assert env.post("/api/v1/equipment", json={"name": "욕창예방 매트리스", "quantity": 2, "location": "1층 침실"}, headers=MANAGER).status_code == 200
    assert env.post("/api/v1/equipment", json={"name": "  ", "quantity": 1}, headers=MANAGER).status_code == 400
    assert env.post("/api/v1/equipment", json={"name": "휠체어", "quantity": 0}, headers=MANAGER).status_code == 400
    rows = env.get("/api/v1/equipment", headers=MANAGER).json()["data"]
    assert len(rows) == 1 and rows[0]["status_label"] == "사용중" and rows[0]["quantity"] == 2
    eid = rows[0]["id"]
    assert env.post(f"/api/v1/equipment/{eid}/status", json={"status": "repair"}, headers=MANAGER).status_code == 200
    assert env.post(f"/api/v1/equipment/{eid}/status", json={"status": "disposed"}, headers=MANAGER).status_code == 200
    disposed = env.get("/api/v1/equipment?status=disposed", headers=MANAGER).json()["data"]
    assert disposed[0]["disposed_date"] == date.today().isoformat()
    assert env.post(f"/api/v1/equipment/{eid}/status", json={"status": "in_use"}, headers=MANAGER).status_code == 400


def test_equipment_other_center_and_caregiver_refused(env):
    env.post("/api/v1/equipment", json={"name": "체중계"}, headers=MANAGER)
    assert env.get("/api/v1/equipment", headers=OTHER_MANAGER).json()["data"] == []
    assert env.get("/api/v1/equipment", headers=CAREGIVER).status_code == 403


def test_meeting_notifies_staff_on_create_and_on_date_change_only(env):
    from app.database import get_db as _gd
    db = next(env.app.dependency_overrides[_gd]())
    env.post("/api/v1/committee", json=MEETING, headers=MANAGER)
    staff = {n.user_id for n in db.query(models.Notification).filter(models.Notification.kind == "staff_meeting").all()}
    assert staff == {2}  # 요양보호사만 있고 센터장은 제외 (사회복지사 계정은 이 테스트 픽스처에 없음)
    mid = env.get("/api/v1/committee", headers=MANAGER).json()["data"][0]["id"]
    env.put(f"/api/v1/committee/{mid}", json={**MEETING, "decisions": "내용만 수정"}, headers=MANAGER)
    assert db.query(models.Notification).filter(models.Notification.kind == "staff_meeting").count() == 1
    new_date = (date.today() + timedelta(days=3)).isoformat()
    env.put(f"/api/v1/committee/{mid}", json={**MEETING, "meeting_date": new_date}, headers=MANAGER)
    assert db.query(models.Notification).filter(models.Notification.kind == "staff_meeting").count() == 2
