"""직원 본인 화면: 내 기록만 보이고, 고충은 접수·처리되며, 보수교육 상태는 생년 홀짝 규칙으로 계산한다."""
import json
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import staff_self, users
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@test.com")
CG = auth(2, "caregiver", "c@test.com")
CG2 = auth(3, "caregiver", "c2@test.com")
SOCIAL = auth(4, "social_worker", "s@test.com")
GUARDIAN = auth(9, "guardian", "g@test.com")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'self.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A"), models.Center(id=2, name="B"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@test.com", full_name="요양사A", role="caregiver", center_id=1, birth_date=date(1980, 3, 1)),
        models.User(id=3, email="c2@test.com", full_name="요양사B", role="caregiver", center_id=1),
        models.User(id=4, email="s@test.com", full_name="사회복지사", role="social_worker", center_id=1),
        models.User(id=9, email="g@test.com", full_name="보호자", role="guardian", center_id=None),
        models.StaffRecord(staff_id=2, record_type="health_checkup", record_date=date(2026, 3, 1), title="일반건강검진", recorded_by=1),
        models.StaffRecord(staff_id=2, record_type="retirement_reserve", record_date=date(2026, 3, 1), title="적립", amount=100000, recorded_by=1),
        models.StaffRecord(staff_id=3, record_type="annual_leave", record_date=date(2026, 2, 1), title="연차", amount=2, recorded_by=1),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(staff_self.router, prefix="/api/v1/staff-self")
    app.include_router(users.router, prefix="/api/v1/users")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def test_caregiver_sees_only_own_records_and_no_retirement_reserve(env):
    _, client = env
    mine = client.get("/api/v1/staff-self/me", headers=CG).json()["data"]
    assert [i["title"] for i in mine["records"]["health_checkup"]["items"]] == ["일반건강검진"]
    assert mine["records"]["annual_leave"]["items"] == []
    assert "retirement_reserve" not in mine["records"] and "퇴직적립금" in mine["note"]
    other = client.get("/api/v1/staff-self/me", headers=CG2).json()["data"]
    assert other["records"]["annual_leave"]["items"][0]["title"] == "연차"


def test_grievance_is_submitted_by_caregiver_and_resolved_by_manager(env):
    _, client = env
    r = client.post("/api/v1/staff-self/grievance", json={"title": "배차 시간 조정 요청", "detail": "이동이 길어 힘듭니다"}, headers=CG)
    assert r.status_code == 200, r.text
    gid = r.json()["data"]["id"]
    assert client.get("/api/v1/staff-self/me", headers=CG).json()["data"]["grievances"][0]["status"] == "open"
    assert client.put(f"/api/v1/staff-self/grievance/{gid}/status", json={"status": "resolved"}, headers=CG).status_code == 403
    assert client.put(f"/api/v1/staff-self/grievance/{gid}/status", json={"status": "resolved"}, headers=MANAGER).status_code == 200
    assert client.get("/api/v1/staff-self/me", headers=CG).json()["data"]["grievances"][0]["status"] == "resolved"
    assert client.post("/api/v1/staff-self/grievance", json={"title": "x"}, headers=GUARDIAN).status_code == 403


def test_education_status_uses_birth_year_parity_and_flags_missing_birth(env):
    db, client = env
    centre = client.get("/api/v1/staff-self/education-status", headers=MANAGER).json()["data"]
    by_id = {r["staff_id"]: r for r in centre["staff"]}
    assert by_id[2]["state"] in ("due", "upcoming", "done")  # 1980년생 짝수 → 짝수 연도 이수
    assert by_id[3]["state"] == "birth_missing"
    assert any(r["staff_id"] == 3 for r in centre["needs_action"])
    # 생년을 넣으면 생년 누락에서 벗어난다 (직원 정보 수정 API)
    client.put("/api/v1/users/3", json={"birth_date": "1981-05-01"}, headers=MANAGER)
    by_id = {r["staff_id"]: r for r in client.get("/api/v1/staff-self/education-status", headers=MANAGER).json()["data"]["staff"]}
    assert by_id[3]["state"] in ("due", "upcoming", "done")


def test_education_exemption_and_completion(env):
    db, client = env
    db.add(models.StaffRecord(staff_id=2, record_type="continuing_education", record_date=date(date.today().year, 1, 10), title="보수교육", recorded_by=1))
    db.commit()
    mine = client.get("/api/v1/staff-self/me", headers=CG).json()["data"]
    from app.education import due_year
    today = date.today()
    expected = "done" if due_year(date(1980, 3, 1), None, today) == today.year else "upcoming"  # 올해 기록은 올해가 대상 연도일 때만 인정
    assert mine["education"]["state"] == expected


def test_non_managers_cannot_see_the_center_education_list(env):
    _, client = env
    assert client.get("/api/v1/staff-self/education-status", headers=CG).status_code == 403
    assert client.get("/api/v1/staff-self/education-status", headers=SOCIAL).status_code == 403


def test_manager_sees_center_grievances_and_resolves_them(env):
    _, client = env
    client.post("/api/v1/staff-self/grievance", json={"title": "배차 조정"}, headers=CG)
    rows = client.get("/api/v1/staff-self/grievances", headers=MANAGER).json()["data"]
    assert rows[0]["title"] == "배차 조정" and rows[0]["staff_name"] == "요양사A"
    assert client.get("/api/v1/staff-self/grievances", headers=CG).status_code == 403


def test_career_ratio_counts_six_month_staff_and_continuous_service(env):
    db, client = env
    db.query(models.User).filter(models.User.id == 2).update({"hire_date": date(2022, 1, 1), "job_type": None, "role": "caregiver"})
    db.query(models.User).filter(models.User.id == 3).update({"hire_date": date(2024, 6, 1)})
    db.commit()
    data = client.get("/api/v1/staff-self/career-ratio", headers=MANAGER).json()["data"]
    names = {r["name"]: r for r in data["staff"]}
    # 요양보호사는 실제 급여제공 월로 센다. 요양사B는 급여 기록이 없어 6개월 미만으로 분모에서 빠진다
    assert names["요양사B"]["included"] is False and "6개월" in names["요양사B"]["reason"]
    assert names["요양사A"]["included"] is False  # 급여 기록 없음 (요양사A도 같은 규칙)
    assert data["threshold_months"] in (12, 24) and data["denominator"] == 0  # 급여 기록이 없으면 분모도 0 (점수 0)
    assert data["score"] == 0
    assert client.get("/api/v1/staff-self/career-ratio", headers=CG).status_code == 403


def test_education_due_reminder_is_sent_once_to_the_caregiver(env):
    db, client = env
    # 올해가 대상 연도가 되도록 생년을 맞춘다
    db.query(models.User).filter(models.User.id == 2).update({"birth_date": date(date.today().year - 46, 3, 1)})  # 오늘 연도와 같은 홀짝
    db.commit()
    client.get("/api/v1/staff-self/education-status", headers=MANAGER)
    client.get("/api/v1/staff-self/me", headers=CG)
    client.get("/api/v1/staff-self/me", headers=CG)
    notes = db.query(models.Notification).filter(models.Notification.user_id == 2, models.Notification.kind == "education_due").all()
    assert len(notes) == 1
