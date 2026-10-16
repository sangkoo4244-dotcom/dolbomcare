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


@pytest.fixture(autouse=True)
def _daytime_visits(monkeypatch):
    """방문 시각은 서버 현재 시각이라, 실행 시간대에 따라 야간 가산이 붙어 금액이 달라졌다. 이 파일의 테스트는 모두 낮 10시로 고정한다."""
    import datetime as _dt

    class _Daytime(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return _dt.datetime(2026, 10, 12, 10, 0)

    monkeypatch.setattr(records, "datetime", _Daytime)


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
    rec, bill = db.query(models.DailyRecord).filter_by(bath_companion=False).one(), db.query(models.BillingRecord).filter_by(caregiver_id=2).one()
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
    bill = db.query(models.BillingRecord).filter_by(caregiver_id=2).one()
    assert (bill.total_cost, bill.amount) == (50100, 42590)
    # 목욕 기록의 동행자를 본인으로 바꾸려 하면 거절
    assert client.patch(f"/api/v1/records/daily/{rid}", json={"co_caregiver_id": 2}, headers=CG_A).status_code == 400


def bath(**kw):
    base = dict(benefit_type="home_bath", bath_mode="vehicle_in", co_caregiver_id=3, duration_minutes=60)
    base.update(kw)
    return payload(**base)


def test_bath_under_60_minutes_is_billed_at_80_percent_and_under_40_is_refused(env):
    db, client = env
    assert client.post("/api/v1/records/create", json=bath(duration_minutes=30), headers=CG_A).status_code == 400
    assert client.post("/api/v1/records/create", json=bath(duration_minutes=45), headers=CG_A).status_code == 200
    bill = db.query(models.BillingRecord).filter_by(caregiver_id=2).one()
    assert (bill.total_cost, bill.amount) == (71192, 60522)  # 88,990원의 80%, 본인부담 15%(10원 절사)


def test_bath_is_limited_to_once_a_week_unless_a_reason_is_given(env):
    db, client = env
    assert client.post("/api/v1/records/create", json=bath(), headers=CG_A).status_code == 200
    again = client.post("/api/v1/records/create", json=bath(), headers=CG_A)
    assert again.status_code == 400 and "주" in again.json()["detail"]
    ok = client.post("/api/v1/records/create", json=bath(special_note="변실금으로 피부 관리 필요"), headers=CG_A)
    assert ok.status_code == 200
    assert db.query(models.DailyRecord).filter_by(benefit_type="home_bath", bath_companion=False).count() == 2  # 동행 기록은 횟수에 세지 않는다
    assert db.query(models.DailyRecord).order_by(models.DailyRecord.id.desc()).first().special_note == "변실금으로 피부 관리 필요"


def test_one_person_bath_exception_bills_80_or_70_percent_of_the_no_vehicle_fee(env):
    db, client = env
    solo = dict(benefit_type="home_bath", bath_mode="no_vehicle", bath_solo_exception=True, duration_minutes=60)
    assert client.post("/api/v1/records/create", json=payload(**solo), headers=CG_A).status_code == 400  # 사유 없음
    assert client.post("/api/v1/records/create", json=payload(**dict(solo, bath_mode="vehicle_in"), special_note="수치심"), headers=CG_A).status_code == 400  # 차량을 쓴 목욕
    assert client.post("/api/v1/records/create", json=payload(**solo, special_note="수치심으로 몸 씻기만 1인"), headers=CG_A).status_code == 200
    rec, bill = db.query(models.DailyRecord).one(), db.query(models.BillingRecord).one()
    assert rec.bath_solo_exception is True and rec.co_caregiver_id is None and bill.total_cost == 40080


def test_two_caregivers_on_home_care_make_two_linked_records_and_bills(env):
    db, client = env
    body = payload(duration_minutes=60, co_caregiver_id=3)
    assert client.post("/api/v1/records/create", json=body, headers=CG_A).status_code == 400  # 동의·상태 없음
    r = client.post("/api/v1/records/create", json=dict(body, special_note="보호자 동의, 와상 상태로 2인 필요"), headers=CG_A)
    assert r.status_code == 200, r.text
    recs = db.query(models.DailyRecord).order_by(models.DailyRecord.id).all()
    bills = db.query(models.BillingRecord).order_by(models.BillingRecord.id).all()
    assert [x.caregiver_id for x in recs] == [2, 3] and [x.caregiver_id for x in bills] == [2, 3]
    assert recs[0].pair_record_id == recs[1].id and recs[1].pair_record_id == recs[0].id
    assert recs[0].co_caregiver_id == 3 and recs[1].co_caregiver_id == 2 and recs[1].special_note.startswith("보호자 동의")
    assert [(b.total_cost, b.amount) for b in bills] == [(25320, 21530), (25320, 21530)]  # 요양보호사별로 각각 같은 금액
    assert db.query(models.Notification).filter(models.Notification.user_id == 3, models.Notification.kind == "record_pair").count() == 1


def test_editing_or_deleting_one_side_of_a_pair_keeps_both_in_sync(env, monkeypatch):
    db, client = env
    # 방문 시각은 서버 현재 시각이므로, 야간 가산이 끼지 않도록 낮 시간으로 고정한다 (실행 시각에 따라 금액이 달라지지 않게)
    import datetime as _dt
    from app.api import records as records_api

    class _Daytime(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return _dt.datetime(2026, 10, 12, 10, 0)

    monkeypatch.setattr(records_api, "datetime", _Daytime)
    r = client.post("/api/v1/records/create", json=payload(duration_minutes=60, co_caregiver_id=3, special_note="동의"), headers=CG_A)
    rid = r.json()["data"]["record_id"]
    assert client.patch(f"/api/v1/records/daily/{rid}", json={"duration_minutes": 120, "notes": "수정"}, headers=CG_A).status_code == 200
    db.expire_all()
    recs = db.query(models.DailyRecord).order_by(models.DailyRecord.id).all()
    bills = db.query(models.BillingRecord).order_by(models.BillingRecord.id).all()
    assert [(x.duration_minutes, x.notes) for x in recs] == [(120, "수정"), (120, "수정")]
    assert [b.total_cost for b in bills] == [43430, 43430]
    # 2인 동시 제공은 기록을 새로 입력할 때만 지정한다
    solo = client.post("/api/v1/records/create", json=payload(duration_minutes=60, resident_id=1), headers=CG_B).json()["data"]["record_id"]
    assert client.patch(f"/api/v1/records/daily/{solo}", json={"co_caregiver_id": 2}, headers=CG_B).status_code == 400
    # 한쪽을 지우면 상대쪽 기록·청구도 함께 지운다
    assert client.delete(f"/api/v1/records/daily/{rid}", headers=CG_A).status_code == 200
    db.expire_all()
    assert [x.id for x in db.query(models.DailyRecord).all()] == [solo]
    assert db.query(models.BillingRecord).count() == 1


def test_a_pair_cannot_be_changed_or_deleted_after_the_partner_bill_is_approved(env):
    db, client = env
    rid = client.post("/api/v1/records/create", json=payload(duration_minutes=60, co_caregiver_id=3, special_note="동의"), headers=CG_A).json()["data"]["record_id"]
    partner_bill = db.query(models.BillingRecord).filter_by(caregiver_id=3).one()
    partner_bill.approval_status = "approved"
    db.commit()
    assert client.patch(f"/api/v1/records/daily/{rid}", json={"notes": "x"}, headers=CG_A).status_code == 400
    assert client.delete(f"/api/v1/records/daily/{rid}", headers=CG_A).status_code == 400
    assert db.query(models.DailyRecord).count() == 2
