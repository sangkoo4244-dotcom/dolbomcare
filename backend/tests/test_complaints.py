"""민원·고충 대장: 접수, 처리 내용 필수, 처리일 순서, 권한, 같은 센터 기록만 보임."""
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import complaints
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@test.com")
SOCIAL = auth(3, "social_worker", "s@test.com")
CAREGIVER = auth(2, "caregiver", "c@test.com")
OTHER_MANAGER = auth(7, "center_manager", "o@test.com")
RECEIVED = date(2026, 10, 10).isoformat()
COMPLAINT = {"resident_id": 1, "complainant": "김영희(딸)", "received_date": RECEIVED, "category": "caregiver",
             "content": "방문 시간이 자주 바뀌어 불편합니다"}


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'complaint.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A"), models.Center(id=2, name="B"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=3, email="s@test.com", full_name="사회복지사", role="social_worker", center_id=1),
        models.User(id=7, email="o@test.com", full_name="타센터장", role="center_manager", center_id=2),
        models.Resident(id=1, center_id=1, name="김이용", care_grade=2),
        models.Resident(id=9, center_id=2, name="타센터이용", care_grade=2),
    ])
    db.commit()
    db.close()
    app = FastAPI()
    app.include_router(complaints.router, prefix="/api/v1/complaints")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_caregiver_cannot_use_the_complaint_book(client):
    assert client.post("/api/v1/complaints", json=COMPLAINT, headers=CAREGIVER).status_code == 403
    assert client.get("/api/v1/complaints", headers=CAREGIVER).status_code == 403


def test_record_then_resolve_with_action(client):
    assert client.post("/api/v1/complaints", json=COMPLAINT, headers=SOCIAL).status_code == 200
    rows = client.get("/api/v1/complaints", headers=MANAGER).json()["data"]
    assert len(rows) == 1 and rows[0]["status"] == "open" and rows[0]["resident_name"] == "김이용"
    assert rows[0]["category_label"] == "요양보호사" and rows[0]["days_open"] is not None
    cid = rows[0]["id"]

    assert client.put(f"/api/v1/complaints/{cid}/resolve", headers=MANAGER,
                      json={"action_taken": "  ", "resolved_date": "2026-10-12"}).status_code == 400
    assert client.put(f"/api/v1/complaints/{cid}/resolve", headers=MANAGER,
                      json={"action_taken": "방문 시간 고정 안내", "resolved_date": "2026-10-09"}).status_code == 400
    assert client.put(f"/api/v1/complaints/{cid}/resolve", headers=MANAGER,
                      json={"action_taken": "방문 시간 고정 안내", "resolved_date": "2026-10-12"}).status_code == 200

    assert client.get("/api/v1/complaints", headers=MANAGER).json()["data"] == []
    done = client.get("/api/v1/complaints?status=resolved", headers=MANAGER).json()["data"][0]
    assert done["action_taken"] == "방문 시간 고정 안내" and done["days_open"] is None
    assert client.put(f"/api/v1/complaints/{cid}/resolve", headers=MANAGER,
                      json={"action_taken": "다시", "resolved_date": "2026-10-13"}).status_code == 400


def test_general_complaint_without_resident_and_validation(client):
    body = {**COMPLAINT, "resident_id": None}
    assert client.post("/api/v1/complaints", json=body, headers=MANAGER).status_code == 200
    assert client.post("/api/v1/complaints", json={**COMPLAINT, "category": "unknown"}, headers=MANAGER).status_code == 400
    assert client.post("/api/v1/complaints", json={**COMPLAINT, "content": "   "}, headers=MANAGER).status_code == 400


def test_other_centers_resident_and_complaints_are_hidden(client):
    assert client.post("/api/v1/complaints", json={**COMPLAINT, "resident_id": 9}, headers=MANAGER).status_code == 404
    assert client.post("/api/v1/complaints", json=COMPLAINT, headers=MANAGER).status_code == 200
    cid = client.get("/api/v1/complaints", headers=MANAGER).json()["data"][0]["id"]
    assert client.get("/api/v1/complaints", headers=OTHER_MANAGER).json()["data"] == []
    assert client.put(f"/api/v1/complaints/{cid}/resolve", headers=OTHER_MANAGER,
                      json={"action_taken": "x", "resolved_date": "2026-10-12"}).status_code == 404
