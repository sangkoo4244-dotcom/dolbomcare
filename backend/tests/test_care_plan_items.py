from tests.test_care_plans import MANAGER, body, env  # noqa: F401  (fixture 재사용)
from app import models


ITEM = {"service_type": "방문요양", "area": "신체활동", "goal": "보행 안정", "need": "보행 보조",
        "detail": "옷 갈아입기 도움", "frequency": "주 5회", "duration_minutes": 60, "writer": "요양보호사 이OO"}


def test_items_and_contract_fields_saved_and_returned(env):
    db, client = env
    payload = body(contract_date="2026-10-01", contract_start_date="2026-10-01", contract_end_date="2027-09-30",
                   service_end_date="2027-09-30", goal_summary="집에서 안전하게 생활", consenter_relation="딸",
                   consenter_phone="010-1234-5678", supervisor_name="사회복지사 김OO",
                   items=[ITEM, {**ITEM, "area": "가사활동", "duration_minutes": 120}])
    res = client.post("/api/v1/care-plans", json=payload, headers=MANAGER)
    assert res.status_code == 200
    plan = res.json()["data"]
    assert plan["contract_date"] == "2026-10-01"
    assert plan["service_end_date"] == "2027-09-30"
    assert plan["consenter_relation"] == "딸"
    assert plan["supervisor_name"] == "사회복지사 김OO"
    assert [i["area"] for i in plan["items"]] == ["신체활동", "가사활동"]
    assert plan["items"][1]["duration_minutes"] == 120

    form = client.get(f"/api/v1/care-plans/{plan['id']}/form", headers=MANAGER).json()["data"]
    assert form["plan"]["contract_start_date"] == "2026-10-01"
    assert form["plan"]["goal_summary"] == "집에서 안전하게 생활"
    assert len(form["items"]) == 2


def test_plan_without_items_still_saves(env):
    db, client = env
    res = client.post("/api/v1/care-plans", json=body(), headers=MANAGER)
    assert res.status_code == 200
    assert res.json()["data"]["items"] == []


def test_delete_removes_items_too(env):
    db, client = env
    plan_id = client.post("/api/v1/care-plans", json=body(items=[ITEM]), headers=MANAGER).json()["data"]["id"]
    assert client.delete(f"/api/v1/care-plans/{plan_id}", headers=MANAGER).status_code == 200
    assert db.query(models.CarePlanItem).filter(models.CarePlanItem.plan_id == plan_id).count() == 0
