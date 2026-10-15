"""중증 가산 한도는 수급자 1인 1일 기준이고(고시 제19조의2·제26조의2), 방문목욕 동행 요양보호사도 1인당 3,000원을 받는다."""
from datetime import datetime, timedelta

from app import models
from app.api.records import _bath_visits_that_week
from tests.test_visit_benefit_api import CG_A, CG_B, MANAGER, bath, env, payload  # noqa: F401  (env 픽스처 재사용)

DAY = (datetime.now() - timedelta(days=2)).replace(hour=9, minute=0, second=0, microsecond=0)


def severe_resident(db, grade=1):
    db.query(models.Resident).filter_by(id=1).update({"care_grade": grade})
    db.commit()


def test_home_care_two_caregivers_share_one_beneficiary_cap(env):
    db, client = env
    severe_resident(db)
    # 같은 수급자 같은 날 120분씩 두 요양보호사(2인 동시 제공): 각자 4,000원이지만 수급자 한도 6,000원
    r = client.post("/api/v1/records/create", json=payload(benefit_type="home_care", duration_minutes=120, co_caregiver_id=3,
                                                          special_note="동의함, 거동 불가", recorded_date=DAY.isoformat()), headers=CG_A)
    assert r.status_code == 200, r.text
    rows = db.query(models.BillingRecord).filter(models.BillingRecord.benefit_type == "home_care").all()
    assert sorted((b.caregiver_id, b.extra_amount) for b in rows) == [(2, 4000), (3, 2000)]
    assert sum(b.extra_amount for b in rows) == 6000


def test_bath_with_companion_gives_each_caregiver_3000_within_the_beneficiary_cap(env):
    db, client = env
    severe_resident(db)
    r = client.post("/api/v1/records/create", json=bath(recorded_date=DAY.isoformat()), headers=CG_A)
    assert r.status_code == 200, r.text
    primary = db.query(models.BillingRecord).filter_by(caregiver_id=2).one()
    companion = db.query(models.BillingRecord).filter_by(caregiver_id=3).one()
    # 주 담당: 차량 내 목욕 60분 일반 1등급 → 급여 88,990원, 본인부담 15%(13,340원) → 공단 75,650원, 중증 가산 3,000원
    assert (primary.total_cost, primary.amount, primary.extra_amount) == (88990, 75650, 3000)
    # 동행: 급여비용 0원(주 담당 청구에 이미 포함), 중증 가산 3,000원만
    assert (companion.total_cost, companion.amount, companion.extra_amount, companion.benefit_type) == (0, 0, 3000, "home_bath")
    assert companion.daily_record_id is not None
    # 동행의 기록은 같은 목욕 방문에 묶여 있다
    comp_record = db.query(models.DailyRecord).filter_by(id=companion.daily_record_id).one()
    assert comp_record.bath_companion is True and comp_record.pair_record_id == primary.daily_record_id


def test_companion_record_does_not_count_as_a_second_bath_in_the_week(env):
    db, client = env
    severe_resident(db)
    client.post("/api/v1/records/create", json=bath(recorded_date=DAY.isoformat()), headers=CG_A)
    assert _bath_visits_that_week(db, 1, DAY) == 1  # 2인 방문 1회 = 주 1회


def test_editing_bath_duration_below_60_removes_the_companion_bonus(env):
    db, client = env
    severe_resident(db)
    rid = client.post("/api/v1/records/create", json=bath(recorded_date=DAY.isoformat()), headers=CG_A).json()["data"]["record_id"]
    assert db.query(models.BillingRecord).filter_by(caregiver_id=3).one().extra_amount == 3000
    # 45분이면 목욕 가산(60분 이상)이 없고, 급여비용은 80%로 줄어든다
    r = client.patch(f"/api/v1/records/daily/{rid}", json={"duration_minutes": 45}, headers=CG_A)
    assert r.status_code == 200, r.text
    primary = db.query(models.BillingRecord).filter_by(caregiver_id=2).one()
    companion = db.query(models.BillingRecord).filter_by(caregiver_id=3).one()
    assert primary.extra_amount == 0 and companion.extra_amount == 0
    assert primary.total_cost == 88990 * 80 // 100 and companion.total_cost == 0  # 45분이면 80%


def test_deleting_the_bath_visit_deletes_the_companion_too(env):
    db, client = env
    severe_resident(db)
    rid = client.post("/api/v1/records/create", json=bath(recorded_date=DAY.isoformat()), headers=CG_A).json()["data"]["record_id"]
    r = client.delete(f"/api/v1/records/daily/{rid}", headers=CG_A)
    assert r.status_code == 200, r.text
    assert db.query(models.BillingRecord).count() == 0 and db.query(models.DailyRecord).count() == 0


def test_grade_3_has_no_bath_bonus_for_either_caregiver(env):
    db, client = env
    severe_resident(db, grade=3)
    client.post("/api/v1/records/create", json=bath(recorded_date=DAY.isoformat()), headers=CG_A)
    assert [b.extra_amount for b in db.query(models.BillingRecord).order_by(models.BillingRecord.id).all()] == [0, 0]
