"""방문목욕·방문간호 기록지(101·102)용 방문 목록: 급여 종류별로 나누고, 요양보호사는 자기 방문만 본다."""
from datetime import datetime, timedelta

from app import models
from app.api import care_sheet
from tests.test_visit_benefit_api import CG_A, CG_B, MANAGER, bath, env, payload  # noqa: F401  (픽스처 재사용)

WEEK = "2026-10-12"


def _with_sheet(client):
    client.app.include_router(care_sheet.router, prefix="/api/v1/care-sheet")
    return client
DAY = datetime(2026, 10, 14, 9, 0)


def test_bath_sheet_lists_only_bath_visits_with_mode_and_partner(env):
    db, client = env
    _with_sheet(client)
    assert client.post("/api/v1/records/create", json=bath(recorded_date=DAY.isoformat()), headers=CG_A).status_code == 200
    assert client.post("/api/v1/records/create", json=payload(recorded_date=(DAY + timedelta(days=1)).isoformat(), duration_minutes=60), headers=CG_A).status_code == 200
    data = client.get("/api/v1/care-sheet/visits", params={"resident_id": 1, "week_start": WEEK, "benefit_type": "home_bath"}, headers=MANAGER).json()["data"]
    assert len(data["visits"]) == 1
    v = data["visits"][0]
    assert v["bath_mode"] == "vehicle_in" and len(v["caregivers"]) == 2 and v["total_minutes"] == 60


def test_nursing_sheet_is_separate_and_caregiver_sees_only_own_visits(env):
    db, client = env
    _with_sheet(client)
    assert client.post("/api/v1/records/create", json=bath(recorded_date=DAY.isoformat()), headers=CG_A).status_code == 200
    # 요양사 B는 이 목욕 방문에 동행자로만 들어 있으므로 기록지에 보인다. 관계없는 방문은 안 보인다
    b = client.get("/api/v1/care-sheet/visits", params={"resident_id": 1, "week_start": WEEK, "benefit_type": "home_bath"}, headers=CG_B).json()["data"]
    assert len(b["visits"]) == 1
    n = client.get("/api/v1/care-sheet/visits", params={"resident_id": 1, "week_start": WEEK, "benefit_type": "home_nursing"}, headers=MANAGER).json()["data"]
    assert n["visits"] == []
    assert client.get("/api/v1/care-sheet/visits", params={"resident_id": 1, "week_start": WEEK, "benefit_type": "home_care"}, headers=MANAGER).status_code == 400
