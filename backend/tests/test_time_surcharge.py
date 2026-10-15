from datetime import datetime, timedelta

from app import benefits
from app import models
from app.billing_rules import split_benefit
from tests.test_visit_benefit_api import CG_A, env, payload  # noqa: F401  (env 픽스처 재사용)

MON = datetime(2026, 10, 12)   # 월요일
SUN = datetime(2026, 10, 18)   # 일요일


def test_night_surcharge_follows_the_nhis_formula_and_rounds_to_10_won():
    fee = benefits.home_care_fee(240)
    # 낮 방문: 가산 없음
    assert benefits.visit_surcharge(fee, MON.replace(hour=9), 240) == 0
    # 전부 야간(22~02시): 기본 × 0.3
    full = benefits.visit_surcharge(fee, MON.replace(hour=22), 240)
    assert full == int((fee * 3 / 10 + 5) // 10) * 10
    # 일부만 야간(20~24시 중 22~24시 = 120분 / 240분): 기본 × 0.3 × 120/240
    half = benefits.visit_surcharge(fee, MON.replace(hour=20), 240)
    assert half == int((fee * 3 / 10 * 120 / 240 + 5) // 10) * 10
    # 새벽 06시 이후는 가산 없음 (04~08시 중 04~06시 = 120분)
    assert benefits.visit_surcharge(fee, MON.replace(hour=4), 240) == half


def test_spec_example_first_leg_22_00_to_22_30_of_270_minutes():
    """공단 세부지침 예시: 18:00 시작 360분 중 최초 270분은 가산 적용 30분(22:00~22:30) → 기본 × 0.3 × 30 ÷ 270."""
    fee = 100000
    assert benefits.surcharge_minutes(MON.replace(hour=18), 270) == 30
    assert benefits.visit_surcharge(fee, MON.replace(hour=18), 270) == int((fee * 3 * 30 / (10 * 270) + 5) // 10) * 10


def test_sunday_is_surcharged_and_overlap_with_night_is_not_counted_twice():
    fee = benefits.home_care_fee(120)
    assert benefits.surcharge_minutes(SUN.replace(hour=10), 120) == 120
    assert benefits.visit_surcharge(fee, SUN.replace(hour=10), 120) == int((fee * 3 / 10 + 5) // 10) * 10
    # 일요일 밤 22시 방문(야간+일요일)도 30%만
    assert benefits.visit_surcharge(fee, SUN.replace(hour=22), 120) == benefits.visit_surcharge(fee, SUN.replace(hour=10), 120)
    # 토요일 23시~일요일 01시: 일요일 구간(00~01시)과 야간이 이어져 120분 모두 가산
    assert benefits.surcharge_minutes((SUN - timedelta(days=1)).replace(hour=23), 120) == 120
    # 일요일 21시 방문 120분: 21~24시 중 일요일이라 전부 가산
    assert benefits.surcharge_minutes(SUN.replace(hour=21), 120) == 120
    # 월요일 새벽 05시~07시: 05~06시만 야간
    assert benefits.surcharge_minutes(MON.replace(hour=5), 120) == 60


def test_surcharge_goes_into_the_fee_and_the_copay_but_not_into_bath():
    base = benefits.home_care_fee(120)
    day = split_benefit("home_care", 120, "일반", start=MON.replace(hour=10))
    night = split_benefit("home_care", 120, "일반", start=MON.replace(hour=22))
    assert day[0] == base and night[0] == base + benefits.visit_surcharge(base, MON.replace(hour=22), 120)
    assert night[1] > day[1] and night[0] - night[1] == night[2]  # 가산도 본인부담 대상
    # start를 안 주면 예전과 같은 금액
    assert split_benefit("home_care", 120, "일반") == day
    # 방문목욕은 시간 가산이 없다
    assert split_benefit("home_bath", 60, "일반", "vehicle_in", start=SUN.replace(hour=23)) == split_benefit("home_bath", 60, "일반", "vehicle_in")


def test_record_at_night_is_billed_with_the_surcharge_and_edits_keep_it(env):
    db, client = env
    when = (datetime.now() - timedelta(days=2)).replace(hour=22, minute=0, second=0, microsecond=0)
    r = client.post("/api/v1/records/create", json=payload(benefit_type="home_care", duration_minutes=120, recorded_date=when.isoformat()), headers=CG_A)
    assert r.status_code == 200, r.text
    base = benefits.home_care_fee(120)
    bill = db.query(models.BillingRecord).one()
    assert bill.total_cost == base + benefits.visit_surcharge(base, when, 120) and bill.total_cost > base
    rid = r.json()["data"]["record_id"]
    assert client.patch(f"/api/v1/records/daily/{rid}", json={"duration_minutes": 60}, headers=CG_A).status_code == 200
    db.expire_all()
    base60 = benefits.home_care_fee(60)
    assert db.query(models.BillingRecord).one().total_cost == base60 + benefits.visit_surcharge(base60, when, 60)


def test_claim_helper_flags_night_and_sunday_visits(env):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import claim_helper, records
    from app.database import get_db
    from tests.test_visit_benefit_api import MANAGER

    db, client = env
    when = (datetime.now() - timedelta(days=2)).replace(hour=22, minute=0, second=0, microsecond=0)
    assert client.post("/api/v1/records/create", json=payload(benefit_type="home_care", duration_minutes=60, recorded_date=when.isoformat()), headers=CG_A).status_code == 200
    bill = db.query(models.BillingRecord).one()
    bill.approval_status = "approved"
    db.commit()
    app = FastAPI()
    app.include_router(claim_helper.router, prefix="/api/v1/claim-helper")
    app.dependency_overrides[get_db] = client.app.dependency_overrides[get_db]
    data = TestClient(app).get(f"/api/v1/claim-helper?year_month={when:%Y-%m}", headers=MANAGER).json()
    flags = [f for r in data["residents"] for v in r["visits"] for f in v["flags"]]
    assert "surcharge" in flags and "surcharge" in data["flag_labels"]


def test_surcharge_preview_endpoint_matches_the_billing_rule(env):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import benefits as benefits_api

    _, client = env
    app = FastAPI()
    app.include_router(benefits_api.router, prefix="/api/v1/benefits")
    c = TestClient(app)
    night = c.get("/api/v1/benefits/visit-surcharge", params={"benefit_type": "home_care", "minutes": 120, "start": "2026-10-13T22:00:00"}, headers=CG_A).json()
    assert night["covered_minutes"] == 120 and night["amount"] == benefits.visit_surcharge(benefits.home_care_fee(120), datetime(2026, 10, 13, 22), 120)
    day = c.get("/api/v1/benefits/visit-surcharge", params={"benefit_type": "home_care", "minutes": 120, "start": "2026-10-13T10:00"}, headers=CG_A).json()
    assert day == {"amount": 0, "covered_minutes": 0}
    assert c.get("/api/v1/benefits/visit-surcharge", params={"benefit_type": "home_bath", "minutes": 60, "start": "2026-10-13T23:00"}, headers=CG_A).json()["amount"] == 0
    assert c.get("/api/v1/benefits/visit-surcharge", params={"benefit_type": "home_care", "minutes": 60, "start": "abc"}, headers=CG_A).status_code == 400
