"""공단 제공기록지(방문요양) 항목 세분화: 세면·구강·체위변경·외출 동행을 따로 기록하고, 항목별 분을 영역별 제공시간으로 합산한다."""
from datetime import date, datetime, timedelta

from app import models
from tests.test_care_sheet import CG_A, MANAGER, WEEK, add_record, env  # noqa: F401  (픽스처 재사용)

NEW_CODES = "wash_face,oral_care,position_change,outing"


def test_new_item_codes_are_accepted_and_timed(env):
    db, client = env
    body = {"caregiver_id": 2, "resident_id": 1, "service_type": "basic_care", "notes": "양호",
            "care_items": NEW_CODES + ",meal_assist,shopping", "duration_minutes": 60,
            "item_minutes": "wash_face:5,oral_care:5,position_change:10,outing:20,meal_assist:20",
            "recorded_date": datetime(2026, 10, 12, 10, 0).isoformat()}
    r = client.post("/api/v1/records/create", json=body, headers=CG_A)
    assert r.status_code == 200, r.text
    rec = db.query(models.DailyRecord).one()
    assert rec.item_minutes == "wash_face:5,oral_care:5,position_change:10,outing:20,meal_assist:20"


def test_unknown_or_unselected_code_still_refused(env):
    _, client = env
    body = {"caregiver_id": 2, "resident_id": 1, "service_type": "basic_care", "care_items": "wash_face", "duration_minutes": 30,
            "item_minutes": "outing:10", "recorded_date": datetime(2026, 10, 12, 10, 0).isoformat()}
    assert client.post("/api/v1/records/create", json=body, headers=CG_A).status_code == 400


def test_sheet_sums_item_minutes_per_day_and_keeps_the_new_codes(env):
    db, client = env
    add_record(db, 2, 0, care_items="wash_face,position_change", duration_minutes=40, item_minutes="wash_face:15,position_change:25")
    add_record(db, 2, 0, care_items="outing,shopping", duration_minutes=30, item_minutes="outing:20,shopping:10")
    data = client.get("/api/v1/care-sheet", params={"resident_id": 1, "week_start": WEEK.isoformat()}, headers=MANAGER).json()
    monday = data["days"][0]
    assert monday["item_minutes"] == {"wash_face": 15, "position_change": 25, "outing": 20, "shopping": 10}
    assert set(monday["care_items"]) == {"wash_face", "position_change", "outing", "shopping"}
    # 기록이 없는 날은 분이 비어 있다
    assert data["days"][1]["visited"] is False and "item_minutes" not in data["days"][1]  # 방문 없는 날은 분 칸을 채우지 않는다
