import os
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import admin, care_plans, handovers, incidents, leave, social_work, users
from app.api.users import create_access_token
from app.database import Base, get_db
from app.demo_seed import DEMO_CAREGIVER_EMAIL, DEMO_CENTER_NAME, DEMO_GUARDIAN_EMAIL, DEMO_MANAGER_EMAIL, DEMO_SOCIAL_EMAIL


def auth(uid, email, role="center_manager"):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


OPERATOR = auth(1, "ops@eeum.kr")
REAL_MANAGER = auth(2, "real@center.kr")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATFORM_ADMIN_EMAILS", "ops@eeum.kr")
    engine = create_engine(f"sqlite:///{tmp_path / 'demo.db'}")

    @event.listens_for(engine, "connect")
    def _enforce_foreign_keys(dbapi_connection, _):  # 운영 PostgreSQL처럼 외래키를 강제한다
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="운영센터"),
        models.User(id=1, email="ops@eeum.kr", full_name="운영자", role="center_manager", center_id=1),
        models.User(id=2, email="real@center.kr", full_name="실센터장", role="center_manager", center_id=1),
        models.Resident(id=1, center_id=1, name="실제이용자", care_grade=3, client_type="일반"),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(admin.router, prefix="/api/v1/admin")
    app.include_router(users.router, prefix="/api/v1/users")
    app.include_router(care_plans.router, prefix="/api/v1/care-plans")
    app.include_router(handovers.router, prefix="/api/v1/handovers")
    app.include_router(incidents.router, prefix="/api/v1/incidents")
    app.include_router(leave.router, prefix="/api/v1/leave")
    app.include_router(social_work.router, prefix="/api/v1/social-work")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def test_only_the_operator_can_see_or_reset_the_demo(env):
    _, client = env
    assert client.get("/api/v1/admin/demo/status", headers=REAL_MANAGER).status_code == 403
    assert client.post("/api/v1/admin/demo/reset", headers=REAL_MANAGER).status_code == 403
    assert client.post("/api/v1/admin/demo/reset").status_code in (401, 403)


def test_reset_creates_the_demo_accounts_and_is_repeatable_without_touching_real_data(env):
    db, client = env
    assert client.get("/api/v1/admin/demo/status", headers=OPERATOR).json()["ready"] is False
    first = client.post("/api/v1/admin/demo/reset", headers=OPERATOR).json()
    assert first["residents"] == 3 and first["bills"] == 15 and first["schedules"] >= 9 and first["reset"] is False  # 오늘 남은 방문은 시각에 따라 줄어든다
    status = client.get("/api/v1/admin/demo/status", headers=OPERATOR).json()
    assert status["ready"] is True and all(a["exists"] for a in status["accounts"])
    demo_center = db.query(models.Center).filter_by(name=DEMO_CENTER_NAME).one()
    remaining = demo_center.trial_ends_at - datetime.utcnow()
    assert demo_center.plan == "trial" and timedelta(days=14, hours=23) < remaining <= timedelta(days=15)
    roles = {u.email: u.role for u in [db.query(models.User).filter_by(email=e).one() for e in [DEMO_SOCIAL_EMAIL, DEMO_MANAGER_EMAIL]]}
    assert roles[DEMO_SOCIAL_EMAIL] == "social_worker"
    # 다시 실행하면 초기화 후 같은 모양으로 다시 만들어진다 (이용자·청구가 두 배로 늘지 않는다)
    second = client.post("/api/v1/admin/demo/reset", headers=OPERATOR).json()
    assert second["reset"] is True
    db.expire_all()
    demo = db.query(models.Center).filter_by(name=DEMO_CENTER_NAME).all()
    assert len(demo) == 1
    assert db.query(models.Resident).filter_by(center_id=demo[0].id).count() == 3
    assert db.query(models.BillingRecord).filter_by(center_id=demo[0].id).count() == 15
    # 실제 센터 자료는 그대로
    assert db.query(models.Resident).filter_by(name="실제이용자").count() == 1 and db.query(models.User).filter_by(email="real@center.kr").count() == 1


def test_orphan_demo_guardian_left_by_a_center_delete_does_not_block_a_new_seed(env):
    db, client = env
    client.post("/api/v1/admin/demo/reset", headers=OPERATOR)
    demo_center = db.query(models.Center).filter_by(name=DEMO_CENTER_NAME).one()
    # 운영자 콘솔에서 센터만 지워 보호자 계정(센터 없음)이 남은 상태를 흉내 낸다
    demo_center.manager_id = None
    db.flush()
    db.query(models.Schedule).filter_by(center_id=demo_center.id).delete()
    db.query(models.BillingRecord).filter_by(center_id=demo_center.id).delete()
    db.query(models.DailyRecord).delete()
    db.query(models.ResidentMessage).delete()
    db.query(models.Notification).delete()
    db.query(models.IncidentReport).filter_by(center_id=demo_center.id).delete()
    db.query(models.HandoverNote).filter_by(center_id=demo_center.id).delete()
    db.query(models.LeaveRequest).filter_by(center_id=demo_center.id).delete()
    db.query(models.CarePlan).filter_by(center_id=demo_center.id).delete()
    db.query(models.MonthlyMonitoring).filter_by(center_id=demo_center.id).delete()
    db.query(models.NeedsAssessment).filter(models.NeedsAssessment.resident_id.in_(
        [r.id for r in db.query(models.Resident).filter_by(center_id=demo_center.id).all()])).delete(synchronize_session=False)
    db.query(models.Resident).filter_by(center_id=demo_center.id).delete()
    db.query(models.User).filter(models.User.center_id == demo_center.id).delete()
    db.delete(demo_center)
    db.commit()
    assert db.query(models.User).filter(models.User.email.like("demo_guardian%")).count() == 1
    assert client.post("/api/v1/admin/demo/reset", headers=OPERATOR).status_code == 200
    assert db.query(models.User).filter_by(email=DEMO_MANAGER_EMAIL).count() == 1


def test_reset_still_works_after_demo_accounts_were_used(env):
    """체험 계정으로 근태·점검·보호자 열람을 남긴 뒤에도 초기화가 500으로 죽지 않아야 한다 (운영 DB는 외래키를 강제한다)."""
    db, client = env
    assert client.post("/api/v1/admin/demo/reset", headers=OPERATOR).status_code == 200
    manager = db.query(models.User).filter_by(email=DEMO_MANAGER_EMAIL).one()
    caregiver = db.query(models.User).filter_by(email=DEMO_CAREGIVER_EMAIL).one()
    guardian = db.query(models.User).filter_by(email=DEMO_GUARDIAN_EMAIL).one()
    resident = db.query(models.Resident).filter_by(center_id=manager.center_id).first()
    db.add_all([
        models.WorkLog(center_id=manager.center_id, staff_id=caregiver.id, work_date=datetime(2026, 10, 15).date(), clock_in=datetime(2026, 10, 15, 9)),
        models.GuardianViewLog(guardian_id=guardian.id, resident_id=resident.id, center_id=manager.center_id, kind="visits"),
        models.InspectionLog(center_id=manager.center_id, kind="vehicle", check_date=datetime(2026, 10, 15).date(), inspector_id=caregiver.id, results="{}"),
    ])
    db.commit()
    response = client.post("/api/v1/admin/demo/reset", headers=OPERATOR)
    assert response.status_code == 200, response.text
    assert response.json()["reset"] is True


def test_demo_login_resets_a_stale_demo_only_once_a_day_and_keeps_the_trial_end(env):
    db, client = env
    client.post("/api/v1/admin/demo/reset", headers=OPERATOR)
    trial_end = datetime.utcnow() + timedelta(days=3)
    center = db.query(models.Center).filter_by(name=DEMO_CENTER_NAME).one()
    center.created_at = datetime.now() - timedelta(days=1)  # 어제 만든 데모
    center.trial_ends_at = trial_end
    db.commit()
    assert client.post("/api/v1/users/login", json={"email": DEMO_CAREGIVER_EMAIL, "password": "demo1234!"}).status_code == 200
    db.expire_all()
    refreshed = db.query(models.Center).filter_by(name=DEMO_CENTER_NAME).one()
    assert refreshed.created_at.date() == datetime.now().date()  # 어제 자료가 오늘 새로 만들어졌다
    assert refreshed.trial_ends_at == trial_end  # 체험 종료일은 이어진다
    assert client.post("/api/v1/users/login", json={"email": DEMO_MANAGER_EMAIL, "password": "demo1234!"}).status_code == 200
    db.expire_all()
    assert db.query(models.Center).filter_by(name=DEMO_CENTER_NAME).one().id == refreshed.id  # 같은 날 두 번째 로그인은 다시 만들지 않는다


def test_demo_work_flows_reach_the_other_roles(env):
    """요양보호사가 올린 기록이 사회복지사·센터장 화면에 나오고, 사회복지사의 계획서가 담당 요양보호사에게 보여야 체험이 의미 있다."""
    db, client = env
    assert client.post("/api/v1/admin/demo/reset", headers=OPERATOR).status_code == 200
    demo = db.query(models.Center).filter_by(name=DEMO_CENTER_NAME).one()
    caregiver = db.query(models.User).filter_by(email=DEMO_CAREGIVER_EMAIL).one()
    social = db.query(models.User).filter_by(email=DEMO_SOCIAL_EMAIL).one()
    manager = db.query(models.User).filter_by(email=DEMO_MANAGER_EMAIL).one()
    kim = db.query(models.Resident).filter_by(center_id=demo.id, name="김복동").one()
    park = db.query(models.Resident).filter_by(center_id=demo.id, name="박만수").one()
    headers = {
        "caregiver": auth(caregiver.id, DEMO_CAREGIVER_EMAIL, "caregiver"),
        "social": auth(social.id, DEMO_SOCIAL_EMAIL, "social_worker"),
        "manager": auth(manager.id, DEMO_MANAGER_EMAIL, "center_manager"),
    }

    mine = client.get("/api/v1/care-plans/mine", headers=headers["caregiver"]).json()["plans"]
    assert sorted({p["resident_name"] for p in mine}) == ["김복동", "이순자"]  # 요양보호사는 담당 이용자의 계획서만 본다
    plans = client.get(f"/api/v1/care-plans?resident_id={kim.id}", headers=headers["social"]).json()["plans"]
    assert plans and all(p["author_name"] == "데모 사회복지사" for p in plans)

    for role in ("social", "manager", "caregiver"):  # 사고 보고: 요양보호사 본인 것이므로 요양보호사·사회복지사·센터장 모두 본다
        reports = client.get("/api/v1/incidents", headers=headers[role]).json()["reports"]
        assert [r["incident_type"] for r in reports] == ["fall"], role

    notes = client.get("/api/v1/handovers", headers=headers["manager"]).json()["notes"]
    assert [n["resident_id"] for n in notes] == [park.id]

    pending = client.get("/api/v1/leave/requests?status=pending", headers=headers["manager"]).json()["data"]
    assert len(pending) == 1 and pending[0]["staff_id"] == caregiver.id


def test_demo_monitoring_shows_one_resident_in_the_three_month_gap(env):
    """데모 체험 첫 화면은 경고 하나만 보여야 한다: 김복동·이순자는 최근 세 달 확인했고 박만수만 누락."""
    db, client = env
    assert client.post("/api/v1/admin/demo/reset", headers=OPERATOR).status_code == 200
    manager = db.query(models.User).filter_by(email=DEMO_MANAGER_EMAIL).one()
    social = db.query(models.User).filter_by(email=DEMO_SOCIAL_EMAIL).one()
    today = datetime.now().date()
    year_month = today.strftime("%Y-%m")
    data = client.get("/api/v1/social-work/monitoring/status", params={"year_month": year_month},
                      headers=auth(social.id, DEMO_SOCIAL_EMAIL, "social_worker")).json()["data"]
    assert [x["name"] for x in data["three_month_gap"]] == ["박만수"]
    assert {x["name"] for x in data["done"]} == {"김복동", "이순자"}
    assert manager.center_id == social.center_id


def test_demo_residents_have_addresses_and_points_for_the_visit_map(env):
    db, client = env
    assert client.post("/api/v1/admin/demo/reset", headers=OPERATOR).status_code == 200
    demo = db.query(models.Center).filter_by(name=DEMO_CENTER_NAME).one()
    residents = db.query(models.Resident).filter_by(center_id=demo.id).all()
    assert len(residents) == 3
    # 데모 이용자는 주소와 좌표를 미리 가진다 (방문 지도에 점이 찍히도록, 주소 변환 API를 부르지 않도록)
    assert all(r.address and r.latitude is not None and r.longitude is not None for r in residents)
