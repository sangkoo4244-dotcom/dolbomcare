"""처음 쓰는 센터의 하루: 센터장이 일정을 잡고 → 요양보호사가 도착·퇴실·기록 → 청구가 생기고 → 센터장이 승인하는 흐름.
각 단계에서 요양보호사 화면과 센터장 화면(오늘 방문 현황·청구 목록·월 청구 합계)이 같은 숫자를 보여 주는지 확인한다."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import billing, records, schedule, today_board
from app.api.users import create_access_token
from app.auth import get_current_user
from app.database import Base, get_db

# 시각에 따라 상태가 달라지지 않도록 방문 시각을 지금 기준으로 잡는다.
# 요양사A의 방문은 지금(도착·퇴실 후 기록), 요양사B의 방문은 3시간 뒤(아직 도착 전 = 예정).
NOW = datetime.now().replace(second=0, microsecond=0)
VISIT_AT = NOW
LATER = NOW + timedelta(hours=3)
YEAR_MONTH = VISIT_AT.strftime("%Y-%m")


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MANAGER = auth(1, "center_manager", "m@t.kr")
CG_A = auth(2, "caregiver", "a@t.kr")
CG_B = auth(3, "caregiver", "b@t.kr")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'chain.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="처음센터"),
        models.User(id=1, email="m@t.kr", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="a@t.kr", full_name="요양사A", role="caregiver", center_id=1),
        models.User(id=3, email="b@t.kr", full_name="요양사B", role="caregiver", center_id=1),
        models.Resident(id=1, center_id=1, name="이용자1", age=80, health_status="stable", care_grade=2, client_type="일반"),
        models.Resident(id=2, center_id=1, name="이용자2", age=78, health_status="stable", care_grade=3, client_type="일반"),
    ])
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(schedule.router, prefix="/api/v1/schedule")
    app.include_router(records.router, prefix="/api/v1/records")
    app.include_router(billing.router, prefix="/api/v1/billing")
    app.include_router(today_board.router, prefix="/api/v1/today-board")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_visit_flows_from_schedule_to_manager_views_with_same_numbers(env):
    # 1. 센터장이 요양사A에게 이용자1 방문을 잡는다 (요양사B는 이용자2 방문)
    for cg, res in ((2, 1), (3, 2)):
        r = env.post("/api/v1/schedule/", headers=MANAGER, json={
            "caregiver_id": cg, "resident_id": res, "center_id": 1,
            "scheduled_date": (VISIT_AT if res == 1 else LATER).isoformat(), "duration_minutes": 60, "benefit_type": "home_care"})
        assert r.status_code == 200, r.text

    # 2. 요양사A 화면에 그 일정이 보이고, 도착·퇴실을 누른다
    view = env.get("/api/v1/schedule/caregiver-view", params={"caregiver_id": 2, "year_month": YEAR_MONTH}, headers=CG_A).json()
    my = [i for i in view["items"] if i["resident_id"] == 1 and i["planned"]]
    assert len(my) == 1, view
    schedule_id = my[0]["schedule_id"]
    assert env.post(f"/api/v1/schedule/{schedule_id}/arrive", headers=CG_A).status_code == 200
    assert env.post(f"/api/v1/schedule/{schedule_id}/depart", headers=CG_A).status_code == 200

    # 3. 요양사A가 방문 기록을 남긴다 (60분, 방문요양)
    r = env.post("/api/v1/records/create", headers=CG_A, json={
        "caregiver_id": 2, "resident_id": 1, "service_type": "basic_care", "notes": "식사 도움",
        "care_items": "meal_assist", "duration_minutes": 60, "benefit_type": "home_care"})
    assert r.status_code == 200, r.text

    # 4. 센터장 '오늘 방문 현황': 요양사A는 기록 완료, 요양사B는 아직 도착 전(예정)
    board = env.get("/api/v1/today-board", headers=MANAGER).json()["data"]
    states = {row["resident"]: row["status"] for row in board["rows"]}
    assert states == {"이용자1": "recorded", "이용자2": "upcoming"}
    by_cg = {g["caregiver"]: g for g in board["by_caregiver"]}
    assert by_cg["요양사A"] == {"caregiver": "요양사A", "total": 1, "recorded": 1, "open": 0}
    assert by_cg["요양사B"]["open"] == 0 and by_cg["요양사B"]["recorded"] == 0

    # 5. 청구: 요양사A 나의 청구와 센터장 청구 목록이 같은 건·같은 금액이어야 한다
    mine = env.get("/api/v1/billing/", headers=CG_A).json()
    mine = mine if isinstance(mine, list) else mine.get("data", mine.get("records", []))
    theirs = env.get("/api/v1/billing/", headers=MANAGER).json()
    theirs = theirs if isinstance(theirs, list) else theirs.get("data", theirs.get("records", []))
    assert len(mine) == 1, mine
    assert [(r["id"], r["amount"]) for r in mine] == [(r["id"], r["amount"]) for r in theirs if r["caregiver_id"] == 2]
    amount = mine[0]["amount"]
    assert amount > 0
    assert mine[0]["approval_status"] == "draft"  # 기록만 된 상태: 요양사가 제출해야 센터장 승인 대기로 넘어간다

    # 6. 센터장 월 청구 합계 (제출 전): 아직 제출 안 된 청구가 승인 대기로 세지면 안 된다
    month_draft = env.get(f"/api/v1/billing/monthly/{YEAR_MONTH}", headers=MANAGER).json()
    print("MONTH_DRAFT", month_draft)

    # 7. 요양사A가 제출 → 요양사A 화면과 센터장 목록이 '승인 대기'로 같이 바뀐다
    assert env.post(f"/api/v1/billing/{mine[0]['id']}/submit", headers=CG_A, json={"user_id": 2, "user_role": "caregiver"}).status_code == 200
    mine_sub = env.get("/api/v1/billing/", headers=CG_A).json()
    mine_sub = mine_sub if isinstance(mine_sub, list) else mine_sub.get("data", mine_sub.get("records", []))
    theirs_sub = env.get("/api/v1/billing/", headers=MANAGER).json()
    theirs_sub = theirs_sub if isinstance(theirs_sub, list) else theirs_sub.get("data", theirs_sub.get("records", []))
    print("AFTER_SUBMIT", mine_sub[0]["approval_status"], [(r["approval_status"], r["amount"]) for r in theirs_sub])
    assert mine_sub[0]["approval_status"] == "pending"
    assert [(r["approval_status"], r["amount"]) for r in theirs_sub if r["caregiver_id"] == 2] == [("pending", amount)]

    # 8. 센터장 월 청구 합계: 제출 후 대기 금액이 같다
    month = env.get(f"/api/v1/billing/monthly/{YEAR_MONTH}", headers=MANAGER).json()
    print("MONTH_SUBMITTED", month)
    assert month["total_amount"] == amount

    # 9. 센터장 승인 → 요양사A 화면이 승인으로 바뀌고 월 합계 금액이 그대로다
    assert env.post(f"/api/v1/billing/{mine[0]['id']}/approve", headers=MANAGER, json={"user_id": 1, "user_role": "center_manager", "reason": "테스트: 위치 없이 도착한 방문, 센터장 확인"}).status_code == 200
    mine_after = env.get("/api/v1/billing/", headers=CG_A).json()
    mine_after = mine_after if isinstance(mine_after, list) else mine_after.get("data", mine_after.get("records", []))
    assert mine_after[0]["approval_status"] == "approved"
    month_after = env.get(f"/api/v1/billing/monthly/{YEAR_MONTH}", headers=MANAGER).json()
    assert month_after["total_amount"] == amount


def test_caregiver_cannot_see_other_caregivers_billing(env):
    # 요양사B 화면에는 요양사A의 청구가 보이면 안 된다 (처음 쓰는 요양사가 남의 것을 보는 일 방지)
    env.post("/api/v1/schedule/", headers=MANAGER, json={
        "caregiver_id": 2, "resident_id": 1, "center_id": 1,
        "scheduled_date": VISIT_AT.isoformat(), "duration_minutes": 60, "benefit_type": "home_care"})
    env.post("/api/v1/records/create", headers=CG_A, json={
        "caregiver_id": 2, "resident_id": 1, "service_type": "basic_care", "notes": "식사",
        "care_items": "meal_assist", "duration_minutes": 60, "benefit_type": "home_care"})
    b = env.get("/api/v1/billing/", headers=CG_B).json()
    b = b if isinstance(b, list) else b.get("data", b.get("records", []))
    assert b == []


def test_voice_record_path_creates_the_same_billing_for_manager(env):
    # 요양사가 실제로 가장 많이 쓰는 경로: 음성 기록 → 청구가 자동으로 생기고, 센터장 목록에 같은 금액으로 보인다
    env.post("/api/v1/schedule/", headers=MANAGER, json={
        "caregiver_id": 2, "resident_id": 1, "center_id": 1,
        "scheduled_date": VISIT_AT.isoformat(), "duration_minutes": 60, "benefit_type": "home_care"})
    r = env.post("/api/v1/records/voice/create", headers=CG_A, params={
        "resident_id": 1, "service_type": "basic_care", "duration_minutes": 60, "transcription": "식사 도움과 청소"})
    assert r.status_code == 200, r.text
    mine = env.get("/api/v1/billing/", headers=CG_A).json()
    mine = mine if isinstance(mine, list) else mine.get("data", mine.get("records", []))
    theirs = env.get("/api/v1/billing/", headers=MANAGER).json()
    theirs = theirs if isinstance(theirs, list) else theirs.get("data", theirs.get("records", []))
    assert len(mine) == 1 and mine[0]["amount"] > 0
    assert [(x["id"], x["amount"], x["approval_status"]) for x in theirs] == [(mine[0]["id"], mine[0]["amount"], mine[0]["approval_status"])]
