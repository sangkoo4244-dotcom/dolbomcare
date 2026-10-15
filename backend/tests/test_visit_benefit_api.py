from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import records
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


CG_A = auth(2, "caregiver", "a@test.com")
CG_B = auth(3, "caregiver", "b@test.com")
NURSE = auth(4, "caregiver", "n@test.com")
MANAGER = auth(1, "center_manager", "m@test.com")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="센터", service_types="방문요양,방문목욕,방문간호"),
        models.Center(id=2, name="요양만", service_types="방문요양"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="a@test.com", full_name="요양A", role="caregiver", center_id=1),
        models.User(id=3, email="b@test.com", full_name="요양B", role="caregiver", center_id=1),
        models.User(id=4, email="n@test.com", full_name="간호사N", role="caregiver", center_id=1, job_type="간호사"),
        models.User(id=6, email="c@test.com", full_name="타센터요양", role="caregiver", center_id=2),
        models.User(id=9, email="g@test.com", full_name="보호자", role="guardian", center_id=1),
        models.Resident(id=1, center_id=1, name="김이용", care_grade=3, client_type="일반", guardian_id=9),
        models.Resident(id=2, center_id=2, name="타센터이용자", care_grade=3, client_type="일반"),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(records.router, prefix="/api/v1/records")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def payload(**kw):
    base = {"caregiver_id": 2, "resident_id": 1, "service_type": "basic_care", "notes": "방문"}
    base.update(kw)
    return base


def test_existing_home_care_record_is_unchanged_and_defaults_to_home_care(env):
    db, client = env
    r = client.post("/api/v1/records/create", json=payload(duration_minutes=60), headers=CG_A)
    assert r.status_code == 200 and r.json()["data"]["benefit_type"] == "home_care"
    rec, bill = db.query(models.DailyRecord).one(), db.query(models.BillingRecord).one()
    assert (rec.benefit_type, bill.benefit_type, bill.total_cost, bill.amount) == ("home_care", "home_care", 25320, 21530)
    assert client.post("/api/v1/records/create", json=payload(duration_minutes=45), headers=CG_A).status_code == 400  # 방문요양은 정해진 시간만
    assert client.post("/api/v1/records/create", json=payload(duration_minutes=300), headers=CG_A).status_code == 422


def test_bath_visit_bills_the_nhis_bath_fee_with_the_second_caregiver(env):
    db, client = env
    body = payload(benefit_type="home_bath", bath_mode="vehicle_in", co_caregiver_id=3, duration_minutes=60)
    r = client.post("/api/v1/records/create", json=body, headers=CG_A)
    assert r.status_code == 200, r.text
    rec, bill = db.query(models.DailyRecord).one(), db.query(models.BillingRecord).one()
    assert (rec.benefit_type, rec.bath_mode, rec.co_caregiver_id) == ("home_bath", "vehicle_in", 3)
    assert (bill.benefit_type, bill.total_cost, bill.amount) == ("home_bath", 88990, 75650)  # 총액 88,990원, 일반 본인부담 15%
    # 보호자에게는 방문목욕이라고 알린다
    note = db.query(models.Notification).filter(models.Notification.user_id == 9).one()
    assert "방문목욕" in note.message


def test_bath_visit_is_rejected_without_a_valid_mode_or_second_caregiver(env):
    _, client = env
    base = dict(benefit_type="home_bath", duration_minutes=60)
    assert client.post("/api/v1/records/create", json=payload(**base, co_caregiver_id=3), headers=CG_A).status_code == 400  # 방식 없음
    assert client.post("/api/v1/records/create", json=payload(**base, bath_mode="vehicle_in"), headers=CG_A).status_code == 400  # 2인 아님
    assert client.post("/api/v1/records/create", json=payload(**base, bath_mode="vehicle_in", co_caregiver_id=6), headers=CG_A).status_code == 400  # 타센터
    assert client.post("/api/v1/records/create", json=payload(**base, bath_mode="car", co_caregiver_id=3), headers=CG_A).status_code == 422


def test_nursing_visit_bills_by_time_band_for_nursing_staff_only(env):
    db, client = env
    r = client.post("/api/v1/records/create", json=payload(caregiver_id=4, benefit_type="home_nursing", duration_minutes=45,
                                                             nursing_order_note="지시서 2026-10-01"), headers=NURSE)
    assert r.status_code == 200, r.text
    rec, bill = db.query(models.DailyRecord).one(), db.query(models.BillingRecord).one()
    assert (rec.benefit_type, rec.nursing_order_note) == ("home_nursing", "지시서 2026-10-01")
    assert (bill.total_cost, bill.amount) == (53770, 45710)  # 30분 이상 60분 미만
    # 요양보호사는 방문간호를 기록할 수 없고, 15분 미만도 안 된다
    assert client.post("/api/v1/records/create", json=payload(benefit_type="home_nursing", duration_minutes=30), headers=CG_A).status_code == 400
    assert client.post("/api/v1/records/create", json=payload(caregiver_id=4, benefit_type="home_nursing", duration_minutes=10), headers=NURSE).status_code == 400


def test_center_must_offer_the_benefit(env):
    db, client = env
    db.add(models.Resident(id=3, center_id=2, name="요양만이용자", care_grade=3, client_type="일반"))
    db.commit()
    other = auth(6, "caregiver", "c@test.com")
    body = payload(caregiver_id=6, resident_id=3, benefit_type="home_nursing", duration_minutes=30)
    r = client.post("/api/v1/records/create", json=body, headers=other)
    assert r.status_code == 400 and "센터 정보" in r.json()["detail"]


def test_updating_a_bath_record_recalculates_by_mode_and_keeps_rules(env):
    db, client = env
    body = payload(benefit_type="home_bath", bath_mode="vehicle_in", co_caregiver_id=3, duration_minutes=60)
    rid = client.post("/api/v1/records/create", json=body, headers=CG_A).json()["data"]["record_id"]
    r = client.patch(f"/api/v1/records/daily/{rid}", json={"bath_mode": "no_vehicle"}, headers=CG_A)
    assert r.status_code == 200, r.text
    bill = db.query(models.BillingRecord).one()
    assert (bill.total_cost, bill.amount) == (50100, 42590)
    # 목욕 기록의 동행자를 본인으로 바꾸려 하면 거절
    assert client.patch(f"/api/v1/records/daily/{rid}", json={"co_caregiver_id": 2}, headers=CG_A).status_code == 400
