"""사회복지사 업무수행일지와 월 방문 확인 기록: 필수 항목, 월 1회, 같은 센터, 청구·급여와 분리."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import social_work
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@test.com")
SOCIAL = auth(3, "social_worker", "s@test.com")
CAREGIVER = auth(2, "caregiver", "c@test.com")
OTHER_SOCIAL = auth(7, "social_worker", "o@test.com")
VISIT = "2026-10-14T10:00:00"


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'sw2.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A"), models.Center(id=2, name="B"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=3, email="s@test.com", full_name="사회복지사", role="social_worker", center_id=1),
        models.User(id=7, email="o@test.com", full_name="타센터 복지사", role="social_worker", center_id=2),
        models.Resident(id=1, center_id=1, name="김이용", care_grade=2),
        models.Resident(id=2, center_id=1, name="박이용", care_grade=3),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(social_work.router, prefix="/api/v1/social-work")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def log_body(**kw):
    base = {"resident_id": 1, "visited_at": VISIT, "counseling_target": "김영희(딸)",
            "counseling_result": "식사량 감소로 보호자와 식단 조정", "content": "정기 상담", "monitoring_checked": True}
    base.update(kw)
    return base


def test_social_worker_writes_a_log_and_manager_reads_it(env):
    _, client = env
    r = client.post("/api/v1/social-work/logs", json=log_body(), headers=SOCIAL)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["author_name"] == "사회복지사"
    rows = client.get("/api/v1/social-work/logs", params={"resident_id": 1}, headers=MANAGER).json()["data"]
    assert rows[0]["counseling_target"] == "김영희(딸)" and rows[0]["monitoring_checked"] is True


def test_required_fields_for_counseling_log(env):
    _, client = env
    assert client.post("/api/v1/social-work/logs", json=log_body(counseling_target=" "), headers=SOCIAL).status_code == 400
    assert client.post("/api/v1/social-work/logs", json=log_body(counseling_result=""), headers=SOCIAL).status_code == 400


def test_one_monitoring_visit_per_resident_per_month(env):
    _, client = env
    body = {"resident_id": 1, "year_month": "2026-10", "visit_date": "2026-10-14T10:00:00", "service_checked": True}
    assert client.post("/api/v1/social-work/monitoring", json=body, headers=SOCIAL).status_code == 200
    assert client.post("/api/v1/social-work/monitoring", json=body, headers=SOCIAL).status_code == 409
    assert client.post("/api/v1/social-work/monitoring", json={**body, "visit_date": "2026-09-30T10:00:00"}, headers=SOCIAL).status_code == 400


def test_three_month_gap_flags_only_residents_missing_for_three_months(env):
    """고시: 세 달 연속 방문 확인이 빠지면 가산 점수를 받을 수 없다. 8월에 한 번이라도 확인했거나 9월 입소한 이용자는 제외."""
    db, client = env
    db.add(models.Resident(id=3, center_id=1, name="최입소", care_grade=2, admission_date=datetime(2026, 9, 15)))
    db.add(models.MonthlyMonitoring(center_id=1, resident_id=1, year_month="2026-08", visit_date=datetime(2026, 8, 10).date(),
                                    author_id=3, service_checked=True))
    db.commit()
    data = client.get("/api/v1/social-work/monitoring/status", params={"year_month": "2026-10"}, headers=MANAGER).json()["data"]
    assert [x["resident_id"] for x in data["three_month_gap"]] == [2]
    data = client.get("/api/v1/social-work/monitoring/status", params={"year_month": "2026-11"}, headers=MANAGER).json()["data"]
    assert [x["resident_id"] for x in data["three_month_gap"]] == [1, 2]  # 8월 확인은 9~11월 창 밖이라 김이용도 빠진다. 최입소는 입소월(9월)이 창에 있어 제외


def test_monthly_status_lists_who_is_still_missing(env):
    _, client = env
    client.post("/api/v1/social-work/monitoring", json={"resident_id": 1, "year_month": "2026-10", "visit_date": "2026-10-14T10:00:00"}, headers=SOCIAL)
    data = client.get("/api/v1/social-work/monitoring/status", params={"year_month": "2026-10"}, headers=MANAGER).json()["data"]
    assert [x["resident_id"] for x in data["done"]] == [1]
    assert [x["resident_id"] for x in data["missing"]] == [2]


def test_roles_and_centers_are_respected(env):
    _, client = env
    assert client.post("/api/v1/social-work/logs", json=log_body(), headers=CAREGIVER).status_code == 403
    assert client.post("/api/v1/social-work/logs", json=log_body(), headers=OTHER_SOCIAL).status_code == 404  # 다른 센터 이용자
    assert client.get("/api/v1/social-work/logs", params={"resident_id": 1}, headers=OTHER_SOCIAL).status_code == 404


def test_visit_plan_is_created_listed_and_marked_done(env):
    _, client = env
    r = client.post("/api/v1/social-work/visit-plans", json={"resident_id": 1, "planned_date": "2026-10-20", "note": "월 방문 확인"}, headers=SOCIAL)
    assert r.status_code == 200, r.text
    pid = r.json()["data"]["id"]
    rows = client.get("/api/v1/social-work/visit-plans", params={"from_date": "2026-10-01", "to_date": "2026-10-31"}, headers=SOCIAL).json()["data"]
    assert rows[0]["resident_name"] == "김이용" and rows[0]["done"] is False
    assert client.post(f"/api/v1/social-work/visit-plans/{pid}/done", headers=SOCIAL).status_code == 200
    assert client.get("/api/v1/social-work/visit-plans", params={"from_date": "2026-10-01", "to_date": "2026-10-31"}, headers=SOCIAL).json()["data"][0]["done"] is True
    assert client.post("/api/v1/social-work/visit-plans", json={"resident_id": 1, "planned_date": "2026-10-20"}, headers=CAREGIVER).status_code == 403
    assert client.post(f"/api/v1/social-work/visit-plans/{pid}/done", headers=OTHER_SOCIAL).status_code == 404


def test_completing_a_plan_records_the_monthly_visit_once(env):
    _, client = env
    first = client.post("/api/v1/social-work/visit-plans", json={"resident_id": 1, "planned_date": "2026-10-20"}, headers=SOCIAL).json()["data"]["id"]
    second = client.post("/api/v1/social-work/visit-plans", json={"resident_id": 1, "planned_date": "2026-10-27"}, headers=SOCIAL).json()["data"]["id"]
    done = client.post(f"/api/v1/social-work/visit-plans/{first}/done", json={"service_checked": True}, headers=SOCIAL).json()["data"]
    assert done["monitoring_created"] is True
    status = client.get("/api/v1/social-work/monitoring/status", params={"year_month": "2026-10"}, headers=MANAGER).json()["data"]
    assert [x["resident_id"] for x in status["done"]] == [1]
    again = client.post(f"/api/v1/social-work/visit-plans/{second}/done", headers=SOCIAL).json()["data"]
    assert again["monitoring_created"] is False  # 같은 달 기록은 한 번만


def test_log_form_returns_print_fields_and_hides_other_centers(env):
    _, client = env
    log_id = client.post("/api/v1/social-work/logs", json=log_body(), headers=SOCIAL).json()["data"]["id"]
    r = client.get(f"/api/v1/social-work/logs/{log_id}/form", headers=MANAGER)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["resident_name"] == "김이용"
    assert data["care_grade"] == 2
    assert data["author_name"] == "사회복지사"
    assert data["counseling_target"] == "김영희(딸)"
    assert data["visited_at"] == "2026-10-14 10:00"
    assert data["needs_assessment"] is None  # 욕구조사가 없으면 출력 칸은 빈칸으로 둔다
    assert client.get(f"/api/v1/social-work/logs/{log_id}/form", headers=OTHER_SOCIAL).status_code == 404
    assert client.get(f"/api/v1/social-work/logs/{log_id}/form", headers=CAREGIVER).status_code == 403
