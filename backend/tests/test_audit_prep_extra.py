from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import audit_prep
from app.api.users import create_access_token
from app.database import Base, get_db


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
    db.add(models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1))
    db.add(models.Resident(id=1, center_id=1, name="김이용"))
    db.add(models.Resident(id=2, center_id=1, name="이이용"))
    # 김이용: 10월 기록들 + 9월 기록(범위 밖)
    db.add(models.CarePlan(center_id=1, resident_id=1, written_date=date(2026, 10, 5), author_id=1, goals="g", needs="n", details="d", frequency="주 5회", opinion="o"))
    db.add(models.CarePlan(center_id=1, resident_id=1, written_date=date(2026, 9, 1), author_id=1, goals="g", needs="n", details="d", frequency="주 5회", opinion="o"))
    db.add(models.ServiceEvaluation(center_id=1, resident_id=1, evaluated_date=date(2026, 10, 6), author_id=1, summary="결과평가 총평 내용", status_changed=True))
    db.add(models.Counseling(center_id=1, kind="resident", resident_id=1, counselor_id=1, counselee_name="김영희(딸)", counsel_date=date(2026, 10, 7), method="phone", content="상담 내용 충분히 구체적으로"))
    db.add(models.Counseling(center_id=1, kind="staff", staff_id=2, counselor_id=1, counsel_date=date(2026, 10, 8), method="visit", content="직원 상담 내용 충분히 구체적으로"))
    db.add(models.ResidentNotice(center_id=1, resident_id=1, notice_type="staff_respect", notice_date=date(2026, 10, 9), method="sms", recipient="김영희(딸)"))
    db.add(models.CaseConference(center_id=1, resident_id=1, conference_date=date(2026, 10, 10), author_id=1, reason="r", content="c", plan="p", attendees="[]"))
    db.add(models.TrainingSession(center_id=1, topic="operating_rules", session_date=date(2026, 10, 11), method="self", instructor="센터장", content="교육내용", attendee_ids="[1, 2]", signed_ids="[1]", recorded_by=1))
    db.commit()
    app = FastAPI()
    app.include_router(audit_prep.router, prefix="/api/v1/audit-prep")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_resident_packet_includes_new_records_within_range(env):
    data = env.get("/api/v1/audit-prep/resident/1?start=2026-10-01&end=2026-10-31", headers=MANAGER).json()
    assert [p["written_date"] for p in data["care_plans"]] == ["2026-10-05"]       # 9월 계획서는 범위 밖
    assert data["care_plans"][0]["issues"]                                          # 서명·통보 누락이 함께 보인다
    assert len(data["service_evaluations"]) == 1 and data["service_evaluations"][0]["follow_up"]["state"] in ("done", "pending", "overdue")
    assert [c["counsel_date"] for c in data["counselings"]] == ["2026-10-07"]       # 직원 상담은 이용자 자료에 섞이지 않는다
    assert data["notices"][0]["notice_type_label"].startswith("직원 존중")
    assert len(data["conferences"]) == 1


def test_other_resident_has_no_records(env):
    data = env.get("/api/v1/audit-prep/resident/2?start=2026-10-01&end=2026-10-31", headers=MANAGER).json()
    assert data["care_plans"] == [] and data["counselings"] == [] and data["notices"] == []


def test_center_packet(env):
    data = env.get("/api/v1/audit-prep/center?start=2026-10-01&end=2026-10-31", headers=MANAGER).json()
    assert [t["topic_label"] for t in data["trainings"]] == ["운영규정 교육"]
    assert [a["name"] for a in data["trainings"][0]["attendees"]] == ["센터장", "요양사"]
    assert [c["staff_name"] for c in data["staff_counselings"]] == ["요양사"]
    assert len(data["conferences"]) == 1


def test_center_packet_validation_and_role(env):
    assert env.get("/api/v1/audit-prep/center?start=bad&end=2026-10-31", headers=MANAGER).status_code == 400
    assert env.get("/api/v1/audit-prep/center?start=2026-10-01&end=2026-10-31", headers=CAREGIVER).status_code == 403
