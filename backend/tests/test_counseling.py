from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import counseling
from app.api.users import create_access_token
from app.database import Base, get_db

TODAY = date(2026, 10, 13)


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@test.com")
CAREGIVER = auth(2, "caregiver", "c@test.com")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.Center(id=1, name="센터"))
    db.add(models.Center(id=2, name="다른센터"))
    db.add(models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="c@test.com", full_name="요양사A", role="caregiver", center_id=1, hire_date=date(2025, 1, 1)))
    db.add(models.User(id=3, email="c2@test.com", full_name="요양사B", role="caregiver", center_id=1, hire_date=date(2025, 1, 1)))
    db.add(models.User(id=4, email="new@test.com", full_name="신규", role="caregiver", center_id=1, hire_date=date(2026, 10, 2)))
    db.add(models.Resident(id=1, center_id=1, name="김이용"))
    db.add(models.Resident(id=2, center_id=1, name="이이용"))
    db.add(models.Resident(id=3, center_id=2, name="타센터"))
    db.commit()
    app = FastAPI()
    app.include_router(counseling.router, prefix="/api/v1/counseling")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


GOOD = {"kind": "resident", "resident_id": 1, "counselee_name": "김영희(딸)", "counsel_date": "2026-10-05",
        "method": "phone", "content": "허리 통증이 늘었다고 해서 방문 시간을 30분 늘리기로 함"}


def test_create_resident_counseling(env):
    _, client = env
    res = client.post("/api/v1/counseling", json=GOOD, headers=MANAGER)
    assert res.status_code == 200
    assert res.json()["data"]["resident_name"] == "김이용" and res.json()["data"]["method_label"] == "유선"


@pytest.mark.parametrize("content", ["특이사항 없음", "지난달과 동일", "특이사항없음.", "짧음"])
def test_trivial_content_is_rejected(env, content):
    _, client = env
    res = client.post("/api/v1/counseling", json={**GOOD, "content": content}, headers=MANAGER)
    assert res.status_code == 400


def test_text_message_method_is_rejected(env):
    _, client = env
    assert client.post("/api/v1/counseling", json={**GOOD, "method": "sms"}, headers=MANAGER).status_code == 400


def test_resident_counseling_needs_counselee_and_own_center(env):
    _, client = env
    assert client.post("/api/v1/counseling", json={**GOOD, "counselee_name": " "}, headers=MANAGER).status_code == 400
    assert client.post("/api/v1/counseling", json={**GOOD, "resident_id": 3}, headers=MANAGER).status_code == 404


def test_staff_counseling_only_for_own_caregiver(env):
    _, client = env
    body = {"kind": "staff", "staff_id": 2, "counsel_date": "2026-10-05", "method": "visit",
            "content": "배차 시간 조정을 요청하여 다음 달 일정에 반영하기로 함", "action_needed": True}
    assert client.post("/api/v1/counseling", json=body, headers=MANAGER).status_code == 200
    assert client.post("/api/v1/counseling", json={**body, "staff_id": 1}, headers=MANAGER).status_code == 404


def test_caregiver_cannot_use_counseling_api(env):
    _, client = env
    assert client.post("/api/v1/counseling", json=GOOD, headers=CAREGIVER).status_code == 403
    assert client.get("/api/v1/counseling", headers=CAREGIVER).status_code == 403


def test_monthly_status_lists_missing_and_skips_new_staff(env):
    _, client = env
    client.post("/api/v1/counseling", json=GOOD, headers=MANAGER)
    s = client.get("/api/v1/counseling/status?month=2026-10", headers=MANAGER).json()
    assert [r["name"] for r in s["residents"] if r["done"]] == ["김이용"]
    assert s["residents_missing"] == 1
    assert {x["name"] for x in s["staff"]} == {"요양사A", "요양사B"}  # 이번 달 입사한 신규는 제외
    assert s["staff_missing"] == 2


def test_action_record(env):
    _, client = env
    cid = client.post("/api/v1/counseling", json={**GOOD, "action_needed": True}, headers=MANAGER).json()["data"]["id"]
    res = client.put(f"/api/v1/counseling/{cid}/action", json={"action_note": "방문 30분 연장", "action_done_date": "2026-10-10"}, headers=MANAGER)
    assert res.json()["data"]["action_done_date"] == "2026-10-10"


def sched(db, rid, cg, month, day):
    db.add(models.Schedule(resident_id=rid, caregiver_id=cg, center_id=1, scheduled_date=datetime(2026, month, day, 9), status="scheduled"))
    db.commit()


def test_caregiver_change_overdue_pending_and_done(env):
    db, _ = env
    db.add(models.Resident(id=4, center_id=1, name="박이용"))
    db.add(models.Resident(id=5, center_id=1, name="최이용"))
    db.commit()
    # 김이용: 요양사A -> 요양사B (9/10 변경, 기한 9/24 지남, 상담 없음) => overdue
    sched(db, 1, 2, 9, 1); sched(db, 1, 3, 9, 10)
    # 이이용: A -> B (10/10 변경, 기한 10/24) => pending
    sched(db, 2, 2, 10, 1); sched(db, 2, 3, 10, 10)
    # 박이용: A -> B (10/1 변경) 후 10/5에 상담함 => done
    sched(db, 4, 2, 9, 20); sched(db, 4, 3, 10, 1)
    db.add(models.Counseling(center_id=1, kind="resident", resident_id=4, counselor_id=1, counselee_name="박영희(딸)",
                             counsel_date=date(2026, 10, 5), method="phone", content="새 요양사 적응 상태 확인함"))
    db.commit()
    by_name = {c["resident_name"]: c for c in counseling.detect_caregiver_changes(db, 1, TODAY)}
    assert by_name["김이용"]["status"] == "overdue"
    assert by_name["이이용"]["status"] == "pending" and by_name["이이용"]["days_left"] == 11
    assert by_name["박이용"]["status"] == "done"
    assert by_name["김이용"]["from_caregiver"] == "요양사A" and by_name["김이용"]["to_caregiver"] == "요양사B"


def test_returning_to_original_caregiver_within_14_days_needs_no_counseling(env):
    db, _ = env
    sched(db, 1, 2, 9, 20)      # A(기존)
    sched(db, 1, 3, 10, 5)      # B(신규, 14일 미만 근무)
    sched(db, 1, 2, 10, 10)     # A(재교체)
    assert counseling.detect_caregiver_changes(db, 1, TODAY) == []


def test_old_changes_and_cancelled_schedules_are_ignored(env):
    db, _ = env
    sched(db, 1, 2, 3, 1); sched(db, 1, 3, 3, 10)           # 7개월 전 변경은 점검 범위 밖
    db.add(models.Schedule(resident_id=2, caregiver_id=2, center_id=1, scheduled_date=datetime(2026, 10, 1, 9), status="scheduled"))
    db.add(models.Schedule(resident_id=2, caregiver_id=3, center_id=1, scheduled_date=datetime(2026, 10, 8, 9), status="cancelled"))
    db.commit()
    assert counseling.detect_caregiver_changes(db, 1, TODAY) == []


def test_changes_endpoint_is_manager_only(env):
    _, client = env
    assert client.get("/api/v1/counseling/caregiver-changes", headers=MANAGER).status_code == 200
    assert client.get("/api/v1/counseling/caregiver-changes", headers=CAREGIVER).status_code == 403
