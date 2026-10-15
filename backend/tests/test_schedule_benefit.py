from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import inbox, records, schedule, users
from app.api.users import create_access_token
from app.database import Base, get_db

NOW = datetime.now().replace(microsecond=0)
NEXT_WEEK = (NOW + timedelta(days=7)).replace(hour=10, minute=0, second=0)


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MGR = auth(1, "center_manager", "m@e.com")
CG_A = auth(2, "caregiver", "a@e.com")
CG_B = auth(3, "caregiver", "b@e.com")
NURSE = auth(4, "caregiver", "n@e.com")


@pytest.fixture
def ctx(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'sb.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="센터", service_types="방문요양,방문목욕,방문간호"),
        models.Center(id=2, name="요양만", service_types="방문요양"),
        models.User(id=1, email="m@e.com", hashed_password="x", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="a@e.com", hashed_password="x", full_name="요양A", role="caregiver", center_id=1),
        models.User(id=3, email="b@e.com", hashed_password="x", full_name="요양B", role="caregiver", center_id=1),
        models.User(id=4, email="n@e.com", hashed_password="x", full_name="간호사N", role="caregiver", center_id=1, job_type="간호사"),
        models.Resident(id=1, center_id=1, name="김일", care_grade=3, client_type="일반"),
    ])
    db.commit()
    db.close()
    app = FastAPI()
    app.include_router(schedule.router, prefix="/api/v1/schedule")
    app.include_router(records.router, prefix="/api/v1/records")
    app.include_router(inbox.router, prefix="/api/v1/inbox")
    app.include_router(users.router, prefix="/api/v1/users")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app), Session


def bath_plan(**kw):
    base = {"caregiver_id": 2, "resident_id": 1, "scheduled_date": NEXT_WEEK.isoformat(), "duration_minutes": 60,
            "benefit_type": "home_bath", "bath_mode": "vehicle_in", "co_caregiver_id": 3}
    base.update(kw)
    return base


def test_caregiver_proposes_a_bath_visit_and_manager_sees_it_with_the_partner(ctx):
    client, Session = ctx
    r = client.post("/api/v1/schedule/propose", json=dict(bath_plan(), user_id=2, user_role="caregiver"), headers=CG_A)
    assert r.status_code == 200, r.text
    item = client.get("/api/v1/schedule/proposals?center_id=1", headers=MGR).json()["items"][0]
    assert (item["benefit_type"], item["bath_mode"], item["co_caregiver_name"]) == ("home_bath", "vehicle_in", "요양B")
    # 방식이나 동행자 없이는 제안할 수 없다
    bad = dict(bath_plan(co_caregiver_id=None), user_id=2, user_role="caregiver")
    assert client.post("/api/v1/schedule/propose", json=bad, headers=CG_A).status_code == 400


def test_manager_creates_plans_directly_and_recurring_with_the_same_rules(ctx):
    client, Session = ctx
    r = client.post("/api/v1/schedule/", json=dict(bath_plan(), center_id=1, scheduled_date=NEXT_WEEK.isoformat()), headers=MGR)
    assert r.status_code == 200, r.text
    assert client.post("/api/v1/schedule/", json=dict(bath_plan(bath_mode=None), center_id=1), headers=MGR).status_code == 400
    # 간호사에게 방문간호를 반복 등록
    start = (NOW + timedelta(days=1)).date().isoformat()
    end = (NOW + timedelta(days=14)).date().isoformat()
    rec = {"caregiver_id": 4, "resident_id": 1, "weekdays": [0, 1, 2, 3, 4, 5, 6], "start_date": start, "end_date": end,
           "start_time": "09:00", "duration_minutes": 30, "benefit_type": "home_nursing"}
    r = client.post("/api/v1/schedule/recurring", json=rec, headers=MGR)
    assert r.status_code == 200 and r.json()["created"] >= 10
    db = Session()
    assert db.query(models.Schedule).filter(models.Schedule.benefit_type == "home_nursing").count() == r.json()["created"]
    # 요양보호사에게 방문간호를 배정할 수는 없다
    assert client.post("/api/v1/schedule/recurring", json=dict(rec, caregiver_id=3), headers=MGR).status_code == 400
    # 방문요양은 예전처럼 아무 값 없이 만들어지고, 계획 시간은 제한하지 않는다
    plain = {"caregiver_id": 3, "resident_id": 1, "weekdays": [0], "start_date": start, "end_date": end, "start_time": "09:00", "duration_minutes": 45}
    assert client.post("/api/v1/schedule/recurring", json=plain, headers=MGR).status_code == 200


def test_partner_caregiver_sees_the_bath_visit_but_it_is_not_counted_twice(ctx):
    client, Session = ctx
    db = Session()
    today = NOW.replace(hour=12, minute=0, second=0)
    db.add(models.Schedule(id=10, caregiver_id=2, resident_id=1, center_id=1, scheduled_date=today - timedelta(hours=1), duration_minutes=60,
                           status="scheduled", benefit_type="home_bath", bath_mode="vehicle_home", co_caregiver_id=3))
    db.commit()
    ym = today.strftime("%Y-%m")
    mine = client.get(f"/api/v1/schedule/caregiver-view?caregiver_id=2&year_month={ym}", headers=CG_A).json()["items"]
    partner = client.get(f"/api/v1/schedule/caregiver-view?caregiver_id=3&year_month={ym}", headers=CG_B).json()["items"]
    assert len(mine) == 1 and mine[0]["companion"] is False and mine[0]["co_caregiver_name"] == "요양B"
    assert len(partner) == 1 and partner[0]["companion"] is True and partner[0]["primary_caregiver_name"] == "요양A"
    assert partner[0]["benefit_type"] == "home_bath" and partner[0]["bath_mode"] == "vehicle_home"
    # 센터 전체 현황에는 방문이 한 번만 나온다(동행 건은 뺀다)
    overview = client.get("/api/v1/inbox/visits-overview", headers=MGR).json()
    assert sum(1 for r in overview["today"] + overview["missing"] if r["resident"] == "김일") <= 1
    assert overview["month"]["total"] == 1


def test_prefill_passes_the_planned_benefit_to_the_record_form(ctx):
    client, Session = ctx
    db = Session()
    soon = datetime.now().replace(microsecond=0)
    db.add(models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=soon, duration_minutes=60, status="scheduled",
                           benefit_type="home_bath", bath_mode="no_vehicle", co_caregiver_id=3))
    db.commit()
    planned = client.get("/api/v1/records/prefill?resident_id=1", headers=CG_A).json()["planned"]
    assert (planned["benefit_type"], planned["bath_mode"], planned["co_caregiver_id"]) == ("home_bath", "no_vehicle", 3)


def test_manager_update_rechecks_rules_and_legacy_schedules_still_work(ctx):
    client, Session = ctx
    db = Session()
    db.add(models.Schedule(id=20, caregiver_id=2, resident_id=1, center_id=1, scheduled_date=NEXT_WEEK, duration_minutes=45, status="scheduled"))
    db.commit()
    # 급여 종류가 없던 예전 일정(시간 45분)도 그대로 수정된다
    assert client.put("/api/v1/schedule/20", json={"notes": "메모"}, headers=MGR).status_code == 200
    # 방문목욕으로 바꾸려면 방식과 동행자가 필요하다
    assert client.put("/api/v1/schedule/20", json={"benefit_type": "home_bath"}, headers=MGR).status_code == 400
    ok = client.put("/api/v1/schedule/20", json={"benefit_type": "home_bath", "bath_mode": "vehicle_in", "co_caregiver_id": 3}, headers=MGR)
    assert ok.status_code == 200 and ok.json()["data"]["benefit_type"] == "home_bath"


def test_job_type_set_by_manager_decides_who_can_do_nursing(ctx):
    client, Session = ctx
    start = (NOW + timedelta(days=1)).date().isoformat()
    end = (NOW + timedelta(days=3)).date().isoformat()
    rec = {"caregiver_id": 3, "resident_id": 1, "weekdays": [0, 1, 2, 3, 4, 5, 6], "start_date": start, "end_date": end,
           "start_time": "09:00", "duration_minutes": 30, "benefit_type": "home_nursing"}
    assert client.post("/api/v1/schedule/recurring", json=rec, headers=MGR).status_code == 400  # 아직 요양보호사
    assert client.put("/api/v1/users/3", json={"job_type": "의사"}, headers=MGR).status_code == 400
    r = client.put("/api/v1/users/3", json={"job_type": "간호조무사"}, headers=MGR)
    assert r.status_code == 200 and r.json()["job_type"] == "간호조무사"
    assert client.post("/api/v1/schedule/recurring", json=rec, headers=MGR).status_code == 200
    r = client.put("/api/v1/users/3", json={"job_type": ""}, headers=MGR)
    assert r.json()["job_type"] == "요양보호사"
    users_list = client.get("/api/v1/users/?center_id=1", headers=MGR).json()["users"]
    assert {u["full_name"]: u["job_type"] for u in users_list}["간호사N"] == "간호사"
