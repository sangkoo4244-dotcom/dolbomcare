"""역할별 메뉴가 기대는 API가 역할에 맞게 열리고 닫히는지 확인한다 (요양보호사·사회복지사·센터장·보호자)."""
import json
from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import audit_prep, care_sheet, trainings
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@test.com")
CAREGIVER = auth(2, "caregiver", "c@test.com")
CAREGIVER2 = auth(3, "caregiver", "c2@test.com")
SOCIAL = auth(4, "social_worker", "s@test.com")
GUARDIAN = auth(9, "guardian", "g@test.com")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'roles.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@test.com", full_name="요양사A", role="caregiver", center_id=1),
        models.User(id=3, email="c2@test.com", full_name="요양사B", role="caregiver", center_id=1),
        models.User(id=4, email="s@test.com", full_name="사회복지사", role="social_worker", center_id=1),
        models.User(id=9, email="g@test.com", full_name="보호자", role="guardian", center_id=None),
        models.Resident(id=1, center_id=1, name="김이용", care_grade=2),
        models.TrainingSession(center_id=1, topic="operating_rules", session_date=date(2026, 10, 1), method="self", instructor="센터장",
                               content="운영규정", attendee_ids=json.dumps([2, 3]), signed_ids=json.dumps([2]), recorded_by=1),
        models.TrainingSession(center_id=1, topic="elder_rights", session_date=date(2026, 10, 5), method="self", instructor="센터장",
                               content="노인인권", attendee_ids=json.dumps([3]), signed_ids=json.dumps([]), recorded_by=1),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(trainings.router, prefix="/api/v1/trainings")
    app.include_router(care_sheet.router, prefix="/api/v1/care-sheet")
    app.include_router(audit_prep.router, prefix="/api/v1/audit-prep")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def test_caregiver_sees_only_own_trainings_with_signature_state(env):
    _, client = env
    mine = client.get("/api/v1/trainings/sessions/mine", headers=CAREGIVER).json()["sessions"]
    assert [s["topic"] for s in mine] == ["operating_rules"] and mine[0]["signed"] is True
    other = client.get("/api/v1/trainings/sessions/mine", headers=CAREGIVER2).json()["sessions"]
    assert sorted(s["topic"] for s in other) == ["elder_rights", "operating_rules"]
    assert client.get("/api/v1/trainings/sessions/mine", headers=GUARDIAN).status_code == 403


def test_manager_training_list_is_still_manager_only(env):
    _, client = env
    assert client.get("/api/v1/trainings/sessions", headers=CAREGIVER).status_code == 403
    assert client.get("/api/v1/trainings/sessions", headers=SOCIAL).status_code == 403
    assert client.get("/api/v1/trainings/sessions", headers=MANAGER).status_code == 200


def test_social_worker_can_read_care_sheet_but_guardian_cannot(env):
    _, client = env
    assert client.get("/api/v1/care-sheet", params={"resident_id": 1, "week_start": "2026-10-12"}, headers=SOCIAL).status_code == 200
    assert client.get("/api/v1/care-sheet", params={"resident_id": 1, "week_start": "2026-10-12"}, headers=GUARDIAN).status_code == 403


def test_social_worker_can_read_audit_packet_but_not_other_roles(env):
    _, client = env
    q = {"start": "2026-10-01", "end": "2026-10-31"}
    assert client.get("/api/v1/audit-prep/resident/1", params=q, headers=SOCIAL).status_code == 200
    assert client.get("/api/v1/audit-prep/resident/1", params=q, headers=CAREGIVER).status_code == 403
