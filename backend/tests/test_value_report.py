from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import models
from app.api import claim_helper, value_report
from app.database import get_db
from tests.test_visit_benefit_api import CG_A, MANAGER, env, payload  # noqa: F401  (env 픽스처 재사용)

DAY = (datetime.now() - timedelta(days=2)).replace(hour=22, minute=0, second=0, microsecond=0)


def make_client(client):
    app = FastAPI()
    app.include_router(value_report.router, prefix="/api/v1/value-report")
    app.dependency_overrides[get_db] = client.app.dependency_overrides[get_db]
    return TestClient(app)


def test_value_report_counts_only_what_was_actually_done(env):
    db, client = env
    db.query(models.Resident).filter_by(id=1).update({"care_grade": 1})
    db.commit()
    # 1·2등급 이용자의 밤 22시 방문요양 180분 → 야간 가산 + 중증 가산, 도착 기록 없음
    r = client.post("/api/v1/records/create", json=payload(benefit_type="home_care", duration_minutes=180, recorded_date=DAY.isoformat()), headers=CG_A)
    assert r.status_code == 200, r.text
    data = make_client(client).get(f"/api/v1/value-report?year_month={DAY:%Y-%m}", headers=MANAGER).json()
    assert (data["visits"], data["auto_bills"]) == (1, 1)
    assert data["review"]["flagged_visits"] == 1 and data["review"]["clean_visits"] == 0  # 도착·퇴실 없음 등 확인할 건
    assert any(f["key"] == "no_arrival" for f in data["review"]["top_flags"])
    assert all(f["key"] != "surcharge" for f in data["review"]["top_flags"])             # 가산 안내는 '확인할 문제'가 아니다
    extras = data["calculated_extras"]
    assert extras["severe_bonus"] == 6000 and extras["time_surcharge"] > 0 and extras["day_night_extra"] == 0
    assert extras["total"] == extras["severe_bonus"] + extras["time_surcharge"]
    assert data["guardian_updates"] == 1                                                 # 보호자에게 방문 소식이 자동으로 나갔다
    assert data["arrival"] == {"with_arrival": 0, "total": 1, "rate": 0}
    assert data["approval"]["draft"] == 1 and data["claim_amount"] > 0


def test_empty_month_and_permissions(env):
    db, client = env
    c = make_client(client)
    empty = c.get("/api/v1/value-report?year_month=2020-01", headers=MANAGER).json()
    assert empty["visits"] == 0 and empty["arrival"]["rate"] is None and empty["calculated_extras"]["total"] == 0
    assert c.get("/api/v1/value-report?year_month=2020-01", headers=CG_A).status_code == 403   # 센터장만
    assert c.get("/api/v1/value-report?year_month=2020-13", headers=MANAGER).status_code == 400
