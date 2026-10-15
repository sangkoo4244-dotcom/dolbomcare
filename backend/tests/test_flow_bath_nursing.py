"""방문목욕·방문간호 기록의 금액을 공단 수가표와 손으로 계산한 값에 대조한다(방문요양은 test_flow_end_to_end.py)."""
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import billing, records
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, email):
    token = create_access_token({"sub": email, "uid": uid, "role": "caregiver"}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


CG = auth(2, "c@a.kr")
NURSE = auth(3, "n@a.kr")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'bn.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A센터", service_types="방문요양,방문목욕,방문간호"),
        models.User(id=1, email="m@a.kr", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@a.kr", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=3, email="n@a.kr", full_name="간호사", role="caregiver", center_id=1, job_type="간호사"),
        models.User(id=4, email="d@a.kr", full_name="동행", role="caregiver", center_id=1),
        models.Resident(id=1, center_id=1, name="일반1등급", age=80, health_status="stable", care_grade=1, client_type="일반"),
        models.Resident(id=2, center_id=1, name="일반3등급", age=80, health_status="stable", care_grade=3, client_type="일반"),
        models.Resident(id=3, center_id=1, name="기초생활", age=80, health_status="stable", care_grade=2, client_type="기초생활보장"),
        models.Resident(id=4, center_id=1, name="차상위", age=80, health_status="stable", care_grade=3, client_type="차상위계층"),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(records.router, prefix="/api/v1/records")
    app.include_router(billing.router, prefix="/api/v1/billing")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def post(client, headers, resident_id, minutes, when, **extra):
    body = {"caregiver_id": headers is NURSE and 3 or 2, "resident_id": resident_id, "service_type": "basic_care",
            "duration_minutes": minutes, "recorded_date": when, **extra}
    r = client.post("/api/v1/records/create", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()["data"]["billing_id"]


def money(db, billing_id):
    b = db.query(models.BillingRecord).filter(models.BillingRecord.id == billing_id).one()
    return b.total_cost, b.amount, b.extra_amount or 0


def test_home_bath_amounts(env):
    db, client = env
    # 가정 내 목욕 60분 일반 1등급: 80,230 / 본인부담 15%=12,034.5→12,030 / 공단 68,200 / 중증 가산 3,000(별도)
    a = post(client, CG, 1, 60, "2026-10-14T10:00:00", benefit_type="home_bath", bath_mode="vehicle_home", co_caregiver_id=4)
    assert money(db, a) == (80230, 68200, 3000)
    # 차량 내 목욕 45분(40~60분은 80%) 일반 3등급: 88,990×0.8=71,192 / 본인부담 10,678.8→10,670 / 공단 60,522 / 3등급은 중증 가산 없음
    b = post(client, CG, 2, 45, "2026-10-14T13:00:00", benefit_type="home_bath", bath_mode="vehicle_in", co_caregiver_id=4)
    assert money(db, b) == (71192, 60522, 0)
    # 차량 미이용 1인 몸 씻기 예외 60분 기초생활 2등급: 50,100×0.8=40,080 / 본인부담 0 / 중증 가산 3,000
    c = post(client, CG, 3, 60, "2026-10-15T10:00:00", benefit_type="home_bath", bath_mode="no_vehicle",
             bath_solo_exception=True, special_note="수치심으로 몸 씻기만 1인 제공")
    assert money(db, c) == (40080, 40080, 3000)


def test_home_bath_rejects_what_cannot_be_billed(env):
    _, client = env
    base = dict(benefit_type="home_bath", bath_mode="vehicle_home", co_caregiver_id=4)
    for minutes, extra, key in ((30, {}, "40분"), (60, {"co_caregiver_id": None}, "2인")):
        body = {"caregiver_id": 2, "resident_id": 1, "service_type": "basic_care", "duration_minutes": minutes,
                "recorded_date": "2026-10-14T10:00:00", **{**base, **extra}}
        r = client.post("/api/v1/records/create", headers=CG, json=body)
        assert r.status_code == 400 and key in r.text


def test_home_nursing_amounts(env):
    db, client = env
    # 20분(15~30분) 일반 1등급: 42,880 / 6,432→6,430 / 공단 36,450 / 방문간호는 중증 가산 없음
    a = post(client, NURSE, 1, 20, "2026-10-14T10:00:00", benefit_type="home_nursing")
    assert money(db, a) == (42880, 36450, 0)
    # 45분(30~60분) 일반 3등급: 53,770 / 8,065.5→8,060 / 공단 45,710
    b = post(client, NURSE, 2, 45, "2026-10-14T11:00:00", benefit_type="home_nursing")
    assert money(db, b) == (53770, 45710, 0)
    # 70분(60분 이상) 차상위 3등급: 64,690 / 6%=3,881.4→3,880 / 공단 60,810
    c = post(client, NURSE, 4, 70, "2026-10-14T14:00:00", benefit_type="home_nursing")
    assert money(db, c) == (64690, 60810, 0)
    # 일요일 30분 일반 1등급: 53,770에 30% 가산 16,131→16,130(10원 단위 반올림) = 69,900 / 10,485→10,480 / 공단 59,420
    d = post(client, NURSE, 1, 30, "2026-10-11T11:00:00", benefit_type="home_nursing")
    assert money(db, d) == (69900, 59420, 0)


def test_home_nursing_only_by_nursing_staff(env):
    _, client = env
    r = client.post("/api/v1/records/create", headers=CG, json={
        "caregiver_id": 2, "resident_id": 1, "service_type": "basic_care", "duration_minutes": 30,
        "recorded_date": "2026-10-14T10:00:00", "benefit_type": "home_nursing"})
    assert r.status_code == 400 and "간호" in r.text


def test_bath_and_nursing_flow_into_monthly_total(env):
    db, client = env
    a = post(client, CG, 1, 60, "2026-10-14T10:00:00", benefit_type="home_bath", bath_mode="vehicle_home", co_caregiver_id=4)
    b = post(client, NURSE, 2, 45, "2026-10-14T11:00:00", benefit_type="home_nursing")
    manager = {"Authorization": "Bearer " + create_access_token({"sub": "m@a.kr", "uid": 1, "role": "center_manager"}, timedelta(hours=1))}
    for bid, hdr, uid in ((a, CG, 2), (b, NURSE, 3)):
        assert client.post(f"/api/v1/billing/{bid}/submit", headers=hdr, json={"user_id": uid, "user_role": "caregiver"}).status_code == 200
        assert client.post(f"/api/v1/billing/{bid}/approve", headers=manager, json={"user_id": 1, "user_role": "center_manager"}).status_code == 200
    monthly = client.get("/api/v1/billing/monthly/2026-10", headers=manager).json()
    # 청구 행은 3건: 주 담당 목욕 + 동행 요양보호사 목욕(급여 0원, 중증 가산만) + 간호. 방문요양 2인 동시 제공과 같은 방식으로 요양보호사별 청구 행을 센다
    assert monthly["total_records"] == 3 and monthly["approved_amount"] == 68200 + 45710
