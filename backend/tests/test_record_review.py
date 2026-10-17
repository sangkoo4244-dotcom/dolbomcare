"""사회복지사 기록 확인: 요양보호사 제공 기록을 사회복지사가 확인하거나 보완 요청하고, 고친 기록은 다시 확인 대기가 된다."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import record_review, records
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@t.kr")
CAREGIVER = auth(2, "caregiver", "c@t.kr")
SOCIAL = auth(3, "social_worker", "s@t.kr")
OTHER_SOCIAL = auth(7, "social_worker", "o@t.kr")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'rr.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A센터", service_types="방문요양"),
        models.Center(id=2, name="B센터", service_types="방문요양"),
        models.User(id=1, email="m@t.kr", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@t.kr", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=3, email="s@t.kr", full_name="사회복지사", role="social_worker", center_id=1),
        models.User(id=7, email="o@t.kr", full_name="타센터 복지사", role="social_worker", center_id=2),
        models.Resident(id=1, center_id=1, name="김이용", age=80, health_status="stable", care_grade=2, client_type="일반"),
        models.Resident(id=2, center_id=2, name="박타센터", age=80, health_status="stable", care_grade=2, client_type="일반"),
    ])
    db.add_all([
        models.DailyRecord(id=1, resident_id=1, caregiver_id=2, recorded_date=datetime.now(), duration_minutes=60,
                           service_type="basic_care", benefit_type="home_care", notes="식사 도움"),
        models.DailyRecord(id=2, resident_id=2, caregiver_id=2, recorded_date=datetime.now(), duration_minutes=60,
                           service_type="basic_care", benefit_type="home_care", notes="타센터 기록"),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(record_review.router, prefix="/api/v1/record-review")
    app.include_router(records.router, prefix="/api/v1/records")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def test_social_worker_sees_center_records_as_pending(env):
    _, client = env
    r = client.get("/api/v1/record-review/records", headers=SOCIAL)
    assert r.status_code == 200
    data = r.json()["data"]
    assert [i["id"] for i in data["items"]] == [1]  # 타센터 기록(2번)은 안 보인다
    assert data["items"][0]["status"] == "pending"
    assert data["items"][0]["caregiver_name"] == "요양사"
    assert data["counts"] == {"pending": 1, "confirmed": 0, "returned": 0}


def test_manager_can_view_but_not_confirm(env):
    _, client = env
    assert client.get("/api/v1/record-review/records", headers=MANAGER).status_code == 200
    assert client.post("/api/v1/record-review/records/1/confirm", headers=MANAGER).status_code == 403
    assert client.post("/api/v1/record-review/records/1/return", json={"note": "x"}, headers=MANAGER).status_code == 403


def test_caregiver_cannot_see_or_confirm(env):
    _, client = env
    assert client.get("/api/v1/record-review/records", headers=CAREGIVER).status_code == 403
    assert client.post("/api/v1/record-review/records/1/confirm", headers=CAREGIVER).status_code == 403


def test_confirm_moves_record_out_of_pending(env):
    _, client = env
    assert client.post("/api/v1/record-review/records/1/confirm", headers=SOCIAL).status_code == 200
    data = client.get("/api/v1/record-review/records", headers=SOCIAL).json()["data"]
    assert data["items"] == []
    confirmed = client.get("/api/v1/record-review/records?status=confirmed", headers=SOCIAL).json()["data"]["items"]
    assert confirmed[0]["status"] == "confirmed"
    assert confirmed[0]["reviewed_by_name"] == "사회복지사"


def test_return_requires_note_and_notifies_caregiver(env):
    db, client = env
    assert client.post("/api/v1/record-review/records/1/return", json={"note": "  "}, headers=SOCIAL).status_code == 400
    assert client.post("/api/v1/record-review/records/1/return", json={"note": "식사량 기록 보완 필요"}, headers=SOCIAL).status_code == 200
    returned = client.get("/api/v1/record-review/records?status=returned", headers=SOCIAL).json()["data"]["items"]
    assert returned[0]["review_note"] == "식사량 기록 보완 필요"
    note = db.query(models.Notification).filter(models.Notification.user_id == 2, models.Notification.kind == "record_returned").first()
    assert note is not None and "식사량 기록 보완 필요" in note.message


def test_other_center_social_worker_cannot_touch_record(env):
    _, client = env
    assert client.post("/api/v1/record-review/records/1/confirm", headers=OTHER_SOCIAL).status_code == 404
    assert client.post("/api/v1/record-review/records/1/return", json={"note": "x"}, headers=OTHER_SOCIAL).status_code == 404


def test_caregiver_edit_sends_returned_record_back_to_pending(env):
    db, client = env
    client.post("/api/v1/record-review/records/1/return", json={"note": "보완"}, headers=SOCIAL)
    r = client.patch("/api/v1/records/daily/1", json={"notes": "식사 도움, 식사량 80% 기록"}, headers=CAREGIVER)
    assert r.status_code == 200, r.text
    pending = client.get("/api/v1/record-review/records", headers=SOCIAL).json()["data"]["items"]
    assert [i["id"] for i in pending] == [1]
    assert pending[0]["review_note"] is None


def test_return_is_refused_when_billing_is_already_approved(env):
    db, client = env
    db.add(models.BillingRecord(daily_record_id=1, caregiver_id=2, resident_id=1, center_id=1, service_type="basic_care",
                                amount=10000, approval_status="approved", recorded_date=datetime.now()))
    db.commit()
    r = client.post("/api/v1/record-review/records/1/return", json={"note": "보완"}, headers=SOCIAL)
    assert r.status_code == 400
    assert "센터장" in r.json()["detail"]
    assert client.post("/api/v1/record-review/records/1/confirm", headers=SOCIAL).status_code == 200  # 확인은 막지 않는다
