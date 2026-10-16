"""사회복지사 역할: 상담·사례관리·급여제공계획·욕구사정은 맡지만, 청구·급여·직원 관리·삭제는 맡지 않는다. 센터 밖은 막는다."""
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import billing, care_plans, counseling, needs_assessments, risk_assessments, service_reviews, users
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@test.com")
SOCIAL = auth(3, "social_worker", "s@test.com")
OTHER_SOCIAL = auth(7, "social_worker", "o@test.com")
CAREGIVER = auth(2, "caregiver", "c@test.com")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'sw.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A"), models.Center(id=2, name="B"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=3, email="s@test.com", full_name="사회복지사", role="social_worker", center_id=1, care_bonus_registered=True),
        models.User(id=7, email="o@test.com", full_name="타센터 복지사", role="social_worker", center_id=2),
        models.Resident(id=1, center_id=1, name="김이용", care_grade=2),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(counseling.router, prefix="/api/v1/counseling")
    app.include_router(service_reviews.router, prefix="/api/v1/service-reviews")
    app.include_router(care_plans.router, prefix="/api/v1/care-plans")
    app.include_router(needs_assessments.router, prefix="/api/v1/needs-assessments")
    app.include_router(risk_assessments.router, prefix="/api/v1/risk-assessments")
    app.include_router(billing.router, prefix="/api/v1/billing")
    app.include_router(users.router, prefix="/api/v1/users")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def plan_body(**kw):
    base = {"resident_id": 1, "plan_type": "regular", "written_date": "2026-10-05", "service_start_date": "2026-10-10",
            "goals": "낙상 없이 일상생활 유지", "needs": "보행 보조", "details": "신체활동 지원", "frequency": "주 5회",
            "duration_minutes": 180, "opinion": "보행 시 부축 필요"}
    base.update(kw)
    return base


def test_social_worker_can_write_care_plans_and_counseling(env):
    _, client = env
    assert client.post("/api/v1/care-plans", json=plan_body(), headers=SOCIAL).status_code == 200
    assert client.get("/api/v1/care-plans", params={"resident_id": 1}, headers=SOCIAL).status_code == 200


def test_social_worker_cannot_touch_billing_or_salary(env):
    _, client = env
    assert client.get("/api/v1/billing/monthly/2026-10", headers=SOCIAL).status_code == 403
    assert client.get("/api/v1/billing/monthly/2026-10", headers=MANAGER).status_code == 200


def test_only_manager_can_delete_plans_and_records(env):
    _, client = env
    pid = client.post("/api/v1/care-plans", json=plan_body(), headers=MANAGER).json()["data"]["id"]
    assert client.delete(f"/api/v1/care-plans/{pid}", headers=SOCIAL).status_code == 403
    assert client.delete(f"/api/v1/care-plans/{pid}", headers=MANAGER).status_code == 200


def test_caregiver_still_cannot_write_plans(env):
    _, client = env
    assert client.post("/api/v1/care-plans", json=plan_body(), headers=CAREGIVER).status_code == 403


def test_social_worker_can_write_assessments_and_other_center_is_refused(env):
    _, client = env
    needs = {"resident_id": 1, "assessed_on": date.today().isoformat()}
    r = client.post("/api/v1/needs-assessments/", json=needs, headers=SOCIAL)
    assert r.status_code != 403, r.text  # 역할은 통과 (본문 검사는 별도)
    assert client.post("/api/v1/needs-assessments/", json=needs, headers=OTHER_SOCIAL).status_code == 404  # 다른 센터 이용자
    assert client.post("/api/v1/care-plans", json=plan_body(), headers=OTHER_SOCIAL).status_code in (404, 400, 403)


def test_social_worker_cannot_create_billing_or_admin_users(env):
    _, client = env
    assert client.post("/api/v1/users/register", json={"email": "x@test.com", "password": "password123", "full_name": "x", "role": "social_worker"}, headers=SOCIAL).status_code == 403


def test_manager_registers_social_worker_with_bonus_flag(env):
    db, client = env
    body = {"email": "new.social@test.com", "password": "password123", "full_name": "새 복지사", "role": "social_worker", "care_bonus_registered": True}
    r = client.post("/api/v1/users/register", json=body, headers=MANAGER)
    assert r.status_code == 200, r.text
    u = db.query(models.User).filter(models.User.email == "new.social@test.com").one()
    assert u.role == "social_worker" and u.center_id == 1 and u.care_bonus_registered is True
    # 요양사로 만들 때는 가산 인력 표시가 저장되지 않는다
    client.post("/api/v1/users/register", json={**body, "email": "c3@test.com", "role": "caregiver"}, headers=MANAGER)
    assert db.query(models.User).filter(models.User.email == "c3@test.com").one().care_bonus_registered is False
    # 사회복지사는 사회복지사 계정을 만들 수 없다
    assert client.post("/api/v1/users/register", json={**body, "email": "x2@test.com"}, headers=SOCIAL).status_code == 403
