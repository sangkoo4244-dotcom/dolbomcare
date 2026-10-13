from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import needs_assessments
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@test.com")
CAREGIVER = auth(2, "caregiver", "c@test.com")


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.Center(id=1, name="센터"))
    db.add(models.Center(id=2, name="다른센터"))
    db.add(models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1))
    db.add(models.Resident(id=1, center_id=1, name="김이용"))
    db.add(models.Resident(id=2, center_id=2, name="타센터"))
    db.commit()
    app = FastAPI()
    app.include_router(needs_assessments.router, prefix="/api/v1/needs-assessments")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app)


OLD_STYLE = {"resident_id": 1, "diseases": "arthritis", "nutrition_status": "good", "mobility_status": "assisted",
             "function_status": {"eating": "alone"}, "notes": "기존 화면에서 저장"}

FULL = {**OLD_STYLE, "cognition_note": "날짜와 장소는 알지만 최근 일은 자주 잊으심", "communication_note": "청력이 약해 큰 소리로 말해야 함",
        "family_env_note": "아들 부부와 동거, 주간에는 혼자 계심", "subjective_needs": "식사 준비와 병원 동행을 원하심",
        "resource_use": "보건소 치매안심센터 이용 중", "overall_opinion": "보행 보조와 식사 준비가 필요하며 인지 저하 관찰이 필요함"}


def test_old_payload_still_saves_and_reports_missing_items(client):
    res = client.post("/api/v1/needs-assessments/", json=OLD_STYLE, headers=MANAGER)
    assert res.status_code == 200
    missing = res.json()["data"]["missing_items"]
    assert missing == ["인지상태", "의사소통", "가족 및 환경상태", "주관적 욕구", "자원이용", "총평"]


def test_full_payload_has_nothing_missing(client):
    data = client.post("/api/v1/needs-assessments/", json=FULL, headers=CAREGIVER).json()["data"]
    assert data["missing_items"] == []
    assert data["overall_opinion"].startswith("보행 보조")


def test_short_overall_opinion_does_not_count(client):
    data = client.post("/api/v1/needs-assessments/", json={**FULL, "overall_opinion": "양호"}, headers=MANAGER).json()["data"]
    assert data["missing_items"] == ["총평"]


def test_history_returns_new_fields_and_isolation(client):
    client.post("/api/v1/needs-assessments/", json=FULL, headers=MANAGER)
    rows = client.get("/api/v1/needs-assessments/resident/1", headers=MANAGER).json()["assessments"]
    assert rows[0]["family_env_note"].startswith("아들 부부")
    assert client.post("/api/v1/needs-assessments/", json={**FULL, "resident_id": 2}, headers=MANAGER).status_code == 404
