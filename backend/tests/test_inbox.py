from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import inbox
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@test.com")
OTHER_MANAGER = auth(5, "center_manager", "o@test.com")
CAREGIVER = auth(2, "caregiver", "a@test.com")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="센터"), models.Center(id=2, name="다른센터"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="a@test.com", full_name="요양사A", role="caregiver", center_id=1),
        models.User(id=5, email="o@test.com", full_name="타센터장", role="center_manager", center_id=2),
        models.Resident(id=1, center_id=1, name="김이용"),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(inbox.router, prefix="/api/v1/inbox")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def counts(client, headers=MANAGER):
    r = client.get("/api/v1/inbox", headers=headers)
    assert r.status_code == 200
    return {i["key"]: i["count"] for i in r.json()["items"]}


def test_empty_center_has_zero_everywhere(env):
    _, client = env
    assert set(counts(client).values()) == {0}


def test_only_manager_can_open_inbox(env):
    _, client = env
    assert client.get("/api/v1/inbox", headers=CAREGIVER).status_code == 403


def test_counts_each_pending_kind_for_own_center_only(env):
    db, client = env
    past = datetime.now() - timedelta(days=2)
    db.add_all([
        models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=past, status="scheduled"),
        models.BillingRecord(caregiver_id=2, resident_id=1, center_id=1, approval_status="rejected", recorded_date=past),
        models.BillingRecord(caregiver_id=2, resident_id=1, center_id=1, approval_status="approved", recorded_date=past),
        models.ResidentChangeRequest(resident_id=1, center_id=1, requested_by=2, field="care_grade", status="pending"),
        models.ResidentChangeRequest(resident_id=1, center_id=1, requested_by=2, field="address", status="approved"),
        models.HandoverNote(center_id=1, resident_id=1, author_id=1, to_caregiver_id=2, content="x" * 12),
        models.HandoverNote(center_id=1, resident_id=1, author_id=1, to_caregiver_id=2, content="y" * 12,
                            acknowledged_at=datetime.now()),
        models.HandoverNote(center_id=1, resident_id=1, author_id=1, to_caregiver_id=None, content="z" * 12),
        models.IncidentReport(center_id=1, resident_id=1, reporter_id=2, occurred_date=date.today(), incident_type="fall",
                              description="d", action_taken="a", guardian_notified_date=None, prevention="대책"),
        models.IncidentReport(center_id=1, resident_id=1, reporter_id=2, occurred_date=date.today(), incident_type="fall",
                              description="d", action_taken="a", guardian_notified_date=date.today(), prevention=""),
        models.IncidentReport(center_id=1, resident_id=1, reporter_id=2, occurred_date=date.today(), incident_type="fall",
                              description="d", action_taken="a", guardian_notified_date=date.today(), prevention="대책"),
    ])
    db.commit()
    mine = counts(client)
    assert mine == {"missing_record": 1, "rejected_claims": 1, "change_requests": 1,
                    "handover_unread": 1, "incident_incomplete": 2}
    assert set(counts(client, OTHER_MANAGER).values()) == {0}
