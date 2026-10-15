from datetime import datetime, timedelta

from app import benefits
from app import models
from tests.test_visit_benefit_api import CG_A, CG_B, bath, env, payload  # noqa: F401  (env 픽스처 재사용)

DAY = (datetime.now() - timedelta(days=2)).replace(hour=9, minute=0, second=0, microsecond=0)


def at(hour, **kw):
    return payload(recorded_date=DAY.replace(hour=hour).isoformat(), **kw)


def test_severe_bonus_table_follows_the_notice():
    assert [benefits.severe_bonus("home_care", 1, m) for m in (30, 60, 90, 120, 150, 180, 240)] == [0, 2000, 2000, 4000, 4000, 6000, 6000]
    assert benefits.severe_bonus("home_care", 2, 120) == 4000 and benefits.severe_bonus(None, 1, 60) == 2000
    assert benefits.severe_bonus("home_care", 3, 240) == 0 and benefits.severe_bonus("home_care", None, 240) == 0  # 1·2등급만
    assert (benefits.severe_bonus("home_bath", 1, 60), benefits.severe_bonus("home_bath", 1, 59), benefits.severe_bonus("home_bath", 4, 60)) == (3000, 0, 0)
    assert benefits.severe_bonus("home_nursing", 1, 60) == 0


def test_severe_bonus_is_separate_from_the_fee_and_has_a_daily_cap(env):
    db, client = env
    db.query(models.Resident).filter_by(id=1).update({"care_grade": 1})
    db.commit()
    for hour, minutes in ((8, 120), (12, 120)):
        assert client.post("/api/v1/records/create", json=at(hour, benefit_type="home_care", duration_minutes=minutes), headers=CG_A).status_code == 200
    bills = db.query(models.BillingRecord).order_by(models.BillingRecord.id).all()
    assert [b.extra_amount for b in bills] == [4000, 2000]  # 같은 날 6,000원 한도: 4,000 + 나머지 2,000
    assert bills[0].total_cost == 43430 and bills[0].amount == 36920  # 급여비용·본인부담은 가산과 별개
    # 다음 날은 한도가 새로 시작
    assert client.post("/api/v1/records/create", json=payload(recorded_date=(DAY - timedelta(days=1)).isoformat(), benefit_type="home_care", duration_minutes=180), headers=CG_A).status_code == 200
    assert db.query(models.BillingRecord).order_by(models.BillingRecord.id.desc()).first().extra_amount == 6000


def test_no_bonus_for_grade_3_and_editing_recomputes_it(env):
    db, client = env
    rid = client.post("/api/v1/records/create", json=payload(benefit_type="home_care", duration_minutes=120, recorded_date=DAY.isoformat()), headers=CG_A).json()["data"]["record_id"]
    assert db.query(models.BillingRecord).one().extra_amount == 0
    db.query(models.Resident).filter_by(id=1).update({"care_grade": 2})
    db.commit()
    client.patch(f"/api/v1/records/daily/{rid}", json={"care_grade": 2, "duration_minutes": 180}, headers=CG_A)
    assert db.query(models.BillingRecord).one().extra_amount == 6000
    client.patch(f"/api/v1/records/daily/{rid}", json={"duration_minutes": 60}, headers=CG_A)
    assert db.query(models.BillingRecord).one().extra_amount == 2000  # 자기 자신은 한도에서 빼고 다시 계산


def test_bath_bonus_and_pair_caregivers_each_get_their_own_bonus(env):
    db, client = env
    db.query(models.Resident).filter_by(id=1).update({"care_grade": 1})
    db.commit()
    client.post("/api/v1/records/create", json=bath(recorded_date=DAY.isoformat()), headers=CG_A)
    assert [b.extra_amount for b in db.query(models.BillingRecord).all()] == [3000]
    # 방문요양 2인 동시 제공: 요양보호사별로 각각 가산
    r = client.post("/api/v1/records/create", json=payload(benefit_type="home_care", duration_minutes=180, co_caregiver_id=3, special_note="동의함, 거동 불가",
                                                          recorded_date=(DAY - timedelta(days=1)).isoformat()), headers=CG_A)
    assert r.status_code == 200, r.text
    rows = db.query(models.BillingRecord).filter(models.BillingRecord.benefit_type == "home_care").all()
    assert sorted((b.caregiver_id, b.extra_amount) for b in rows) == [(2, 6000), (3, 6000)]
