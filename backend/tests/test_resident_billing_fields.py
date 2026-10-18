"""수급자 정보 보강: 급여 개시일, 청구지 주소, 청구서 수신 채널, 추가 보호자.
센터장만 바꾸고, 요양사는 바꾸지 못하며, 다른 센터의 정보는 건드리지 못한다."""
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import residents
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MANAGER = auth(1, "center_manager", "m@test.com")
CAREGIVER = auth(2, "caregiver", "c@test.com")
OTHER_MANAGER = auth(3, "center_manager", "o@test.com")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'res.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A"),
        models.Center(id=2, name="B"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=3, email="o@test.com", full_name="타센터장", role="center_manager", center_id=2),
        models.Resident(id=1, center_id=1, name="이용자", care_grade=2, client_type="일반"),
    ])
    db.commit()
    db.close()
    app = FastAPI()
    app.include_router(residents.router, prefix="/api/v1/residents")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_manager_sets_service_start_billing_address_and_channels(env):
    r = env.put("/api/v1/residents/1", headers=MANAGER, json={
        "service_start_date": "2026-04-01", "billing_address": "서울 강남구 테헤란로 1", "billing_channels": ["sms", "email", "sms"]})
    assert r.status_code == 200, r.text
    got = env.get("/api/v1/residents/1", headers=MANAGER).json()
    assert got["service_start_date"] == "2026-04-01"
    assert got["billing_address"] == "서울 강남구 테헤란로 1"
    assert got["billing_channels"] == ["sms", "email"]  # 중복은 한 번만


def test_caregiver_cannot_change_the_new_fields(env):
    r = env.put("/api/v1/residents/1", headers=CAREGIVER, json={"billing_address": "다른 곳"})
    assert r.status_code == 403


def test_unknown_billing_channel_is_refused(env):
    r = env.put("/api/v1/residents/1", headers=MANAGER, json={"billing_channels": ["fax"]})
    assert r.status_code == 400


def test_additional_guardians_are_added_listed_and_removed(env):
    r = env.post("/api/v1/residents/1/guardians", headers=MANAGER, json={"name": "김자녀", "relation": "자녀", "phone": "010-1234-5678"})
    assert r.status_code == 200, r.text
    gid = r.json()["data"]["id"]
    got = env.get("/api/v1/residents/1", headers=MANAGER).json()
    assert got["additional_guardians"] == [{"id": gid, "name": "김자녀", "relation": "자녀", "phone": "010-1234-5678", "email": None}]
    assert env.delete(f"/api/v1/residents/1/guardians/{gid}", headers=MANAGER).status_code == 200
    assert env.get("/api/v1/residents/1", headers=MANAGER).json()["additional_guardians"] == []


def test_additional_guardian_needs_a_name_and_the_same_center(env):
    assert env.post("/api/v1/residents/1/guardians", headers=MANAGER, json={"name": "  "}).status_code == 400
    assert env.post("/api/v1/residents/1/guardians", headers=OTHER_MANAGER, json={"name": "남"}).status_code == 404
    assert env.post("/api/v1/residents/1/guardians", headers=CAREGIVER, json={"name": "남"}).status_code == 403


def test_saving_the_form_with_empty_optional_fields_works(env):
    # 수정 화면은 빈 칸을 null로 보낸다. 인정 기간을 비운 채 저장해도 실패하면 안 된다.
    r = env.put("/api/v1/residents/1", headers=MANAGER, json={
        "name": "이용자", "recognition_start": None, "recognition_end": None, "service_start_date": None,
        "billing_address": "", "billing_channels": []})
    assert r.status_code == 200, r.text
