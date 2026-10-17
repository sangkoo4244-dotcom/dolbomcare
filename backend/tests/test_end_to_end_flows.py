"""메뉴를 넘나드는 업무 흐름 검사: 요양보호사 기록 → 사회복지사 확인·보완 → 요양보호사 수정 → 센터장 열람,
사고 보고 → 알림, 연차 신청 → 승인 → 알림, 운영위원회 회의 → 직원 알림, 평가 기한 알림."""
from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models, scheduler
from app.api import committee, incidents, leave, record_review, records, risk_assessments
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@t.kr")
CAREGIVER = auth(2, "caregiver", "c@t.kr")
SOCIAL = auth(3, "social_worker", "s@t.kr")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'e2e.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A센터"),
        models.User(id=1, email="m@t.kr", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@t.kr", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=3, email="s@t.kr", full_name="사회복지사", role="social_worker", center_id=1),
        models.Resident(id=1, center_id=1, name="김이용", age=80, health_status="stable", care_grade=2, client_type="일반"),
        models.DailyRecord(id=1, resident_id=1, caregiver_id=2, recorded_date=datetime.now(), duration_minutes=60,
                           service_type="basic_care", benefit_type="home_care", notes="식사 도움"),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(record_review.router, prefix="/api/v1/record-review")
    app.include_router(records.router, prefix="/api/v1/records")
    app.include_router(incidents.router, prefix="/api/v1/incidents")
    app.include_router(leave.router, prefix="/api/v1/leave")
    app.include_router(committee.router, prefix="/api/v1/committee")
    app.include_router(risk_assessments.router, prefix="/api/v1/risk-assessments")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app), Session


def notes(Session, user_id, kind):
    s = Session()
    try:
        return [n.message for n in s.query(models.Notification).filter(
            models.Notification.user_id == user_id, models.Notification.kind == kind).all()]
    finally:
        s.close()


def test_record_review_loop_from_caregiver_to_manager(env):
    client, Session = env
    # 1) 사회복지사가 확인 대기 건을 본다
    assert client.get("/api/v1/record-review/pending-count", headers=SOCIAL).json()["data"]["pending"] == 1
    # 2) 보완 요청 → 요양보호사에게 알림
    assert client.post("/api/v1/record-review/records/1/return", json={"note": "식사량 보완"}, headers=SOCIAL).status_code == 200
    assert any("식사량 보완" in m for m in notes(Session, 2, "record_returned"))
    # 3) 요양보호사가 기록을 고치면 다시 확인 대기
    r = client.patch("/api/v1/records/daily/1", json={"notes": "식사 도움, 80% 섭취"}, headers=CAREGIVER)
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/record-review/pending-count", headers=SOCIAL).json()["data"]["pending"] == 1
    # 4) 사회복지사가 확인하면 대기에서 빠지고, 센터장은 확인 완료로 본다
    assert client.post("/api/v1/record-review/records/1/confirm", headers=SOCIAL).status_code == 200
    assert client.get("/api/v1/record-review/pending-count", headers=SOCIAL).json()["data"]["pending"] == 0
    done = client.get("/api/v1/record-review/records?status=confirmed", headers=MANAGER).json()["data"]["items"]
    assert [i["status"] for i in done] == ["confirmed"]


def test_incident_reaches_manager_and_social_worker(env):
    client, Session = env
    body = {"resident_id": 1, "occurred_date": date.today().isoformat(), "incident_type": "fall",
            "description": "욕실 앞에서 미끄러져 넘어짐", "action_taken": "바로 일으키고 혈압과 통증을 확인함"}
    assert client.post("/api/v1/incidents", json=body, headers=CAREGIVER).status_code == 200
    assert notes(Session, 1, "incident_reported") and notes(Session, 3, "incident_reported")
    assert client.get("/api/v1/incidents", headers=SOCIAL).json()["reports"]


def test_leave_request_to_approval_and_back(env):
    client, Session = env
    future = (date.today() + timedelta(days=4)).isoformat()
    rid = client.post("/api/v1/leave/requests", json={"leave_date": future, "leave_type": "annual"}, headers=CAREGIVER).json()["data"]["id"]
    assert notes(Session, 1, "leave_requested")
    assert client.post(f"/api/v1/leave/requests/{rid}/approve", json={}, headers=MANAGER).status_code == 200
    assert notes(Session, 2, "leave_decided")
    assert client.get("/api/v1/leave/requests/mine", headers=CAREGIVER).json()["data"][0]["status"] == "approved"


def test_committee_meeting_notifies_staff_and_due_assessments_reach_managers(env):
    client, Session = env
    meeting = {"meeting_date": (date.today() + timedelta(days=7)).isoformat(), "title": "운영위원회", "agenda": "일정 조정"}
    assert client.post("/api/v1/committee", json=meeting, headers=MANAGER).status_code == 200
    assert notes(Session, 2, "staff_meeting") and notes(Session, 3, "staff_meeting")
    # 평가가 한 번도 없으므로 정기 점검이 센터장과 사회복지사에게 알림을 보낸다
    s = Session()
    try:
        summary = scheduler.run_daily_jobs(s)
    finally:
        s.close()
    assert summary["assessment_due_sent"] > 0
    assert notes(Session, 1, "assessment_due") and notes(Session, 3, "assessment_due")
    assert not notes(Session, 2, "assessment_due")  # 요양보호사에게는 가지 않는다
