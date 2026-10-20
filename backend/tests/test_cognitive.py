"""인지활동 계획표: 목록에 있는 활동만, 주 횟수·시간 범위를 지키고, 센터장·사회복지사만 저장한다."""
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import cognitive
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MANAGER = auth(1, "center_manager", "m@test.com")
SOCIAL = auth(3, "social_worker", "s@test.com")
CAREGIVER = auth(2, "caregiver", "c@test.com")
OTHER_MANAGER = auth(4, "center_manager", "o@test.com")


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'cog.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A"), models.Center(id=2, name="B"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=3, email="s@test.com", full_name="사회복지사", role="social_worker", center_id=1),
        models.User(id=4, email="o@test.com", full_name="타센터장", role="center_manager", center_id=2),
        models.Resident(id=1, center_id=1, name="이용자1"),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(cognitive.router, prefix="/api/v1/cognitive")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    return TestClient(app)


def plan(items):
    return {"resident_id": 1, "year_month": "2026-10", "items": items}


def test_social_worker_saves_a_plan_and_the_activity_sheet_reads_it_back(client):
    items = [{"code": "recall_talk", "frequency_per_week": 2, "minutes": 30, "note": "옛 사진 보기"},
             {"code": "hand_exercise", "frequency_per_week": 5, "minutes": 10}]
    assert client.put("/api/v1/cognitive/plan", json=plan(items), headers=SOCIAL).status_code == 200
    data = client.get("/api/v1/cognitive/plan", params={"resident_id": 1, "year_month": "2026-10"}, headers=MANAGER).json()["data"]
    assert data["resident_name"] == "이용자1" and [i["code"] for i in data["items"]] == ["recall_talk", "hand_exercise"]
    assert data["items"][0]["label"].startswith("회상 대화")
    again = [{"code": "music", "frequency_per_week": 1, "minutes": 20}]
    assert client.put("/api/v1/cognitive/plan", json=plan(again), headers=MANAGER).status_code == 200  # 같은 달은 덮어쓴다
    assert len(client.get("/api/v1/cognitive/plan", params={"resident_id": 1, "year_month": "2026-10"}, headers=MANAGER).json()["data"]["items"]) == 1


def test_rejects_unknown_activities_bad_ranges_and_duplicates(client):
    assert client.put("/api/v1/cognitive/plan", json=plan([{"code": "unknown", "frequency_per_week": 1, "minutes": 10}]), headers=MANAGER).status_code == 400
    assert client.put("/api/v1/cognitive/plan", json=plan([{"code": "music", "frequency_per_week": 8, "minutes": 10}]), headers=MANAGER).status_code == 422
    assert client.put("/api/v1/cognitive/plan", json=plan([{"code": "music", "frequency_per_week": 1, "minutes": 3}]), headers=MANAGER).status_code == 422
    dup = [{"code": "music", "frequency_per_week": 1, "minutes": 10}, {"code": "music", "frequency_per_week": 2, "minutes": 10}]
    assert client.put("/api/v1/cognitive/plan", json=plan(dup), headers=MANAGER).status_code == 400


def test_caregiver_and_other_centers_are_refused(client):
    assert client.get("/api/v1/cognitive/catalog", headers=CAREGIVER).status_code == 403
    assert client.put("/api/v1/cognitive/plan", json=plan([{"code": "music", "frequency_per_week": 1, "minutes": 10}]), headers=CAREGIVER).status_code == 403
    assert client.get("/api/v1/cognitive/plan", params={"resident_id": 1, "year_month": "2026-10"}, headers=OTHER_MANAGER).status_code == 404
    assert client.get("/api/v1/cognitive/plan", params={"resident_id": 1, "year_month": "2026-13"}, headers=MANAGER).status_code == 400


def test_previous_month_plan_is_offered_without_saving(client):
    client.put("/api/v1/cognitive/plan", json={"resident_id": 1, "year_month": "2026-08", "items": [
        {"code": "music", "frequency_per_week": 3, "minutes": 20}]}, headers=MANAGER)
    client.put("/api/v1/cognitive/plan", json={"resident_id": 1, "year_month": "2026-09", "items": [
        {"code": "walk", "frequency_per_week": 2, "minutes": 15}]}, headers=MANAGER)
    prev = client.get("/api/v1/cognitive/plan/previous?resident_id=1&year_month=2026-10", headers=MANAGER).json()["data"]
    assert prev["year_month"] == "2026-09" and [i["code"] for i in prev["items"]] == ["walk"]
    # 가져오기만 해서는 10월 계획이 저장되지 않는다
    own = client.get("/api/v1/cognitive/plan?resident_id=1&year_month=2026-10", headers=MANAGER).json()["data"]
    assert own["items"] == []


def test_no_previous_plan_and_refusals(client):
    empty = client.get("/api/v1/cognitive/plan/previous?resident_id=1&year_month=2026-10", headers=MANAGER).json()["data"]
    assert empty == {"year_month": None, "items": []}
    assert client.get("/api/v1/cognitive/plan/previous?resident_id=1&year_month=2026-13", headers=MANAGER).status_code == 400
    assert client.get("/api/v1/cognitive/plan/previous?resident_id=1&year_month=2026-10", headers=CAREGIVER).status_code == 403
    assert client.get("/api/v1/cognitive/plan/previous?resident_id=1&year_month=2026-10", headers=OTHER_MANAGER).status_code == 404
