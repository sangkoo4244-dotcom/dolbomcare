from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import billing, inbox
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
    app.include_router(billing.router, prefix="/api/v1/billing")

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
        models.BillingRecord(caregiver_id=2, resident_id=1, center_id=1, approval_status="draft", recorded_date=datetime.now() - timedelta(days=5)),
        models.BillingRecord(caregiver_id=2, resident_id=1, center_id=1, approval_status="draft", recorded_date=datetime.now()),
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
    assert mine == {"missing_record": 1, "draft_claims": 1, "rejected_claims": 1, "change_requests": 1,
                    "handover_unread": 1, "incident_incomplete": 2}
    assert set(counts(client, OTHER_MANAGER).values()) == {0}


def test_submitting_a_claim_notifies_only_managers_of_that_center(env):
    db, client = env
    db.add(models.BillingRecord(id=7, caregiver_id=2, resident_id=1, center_id=1, resident_name="김이용", approval_status="draft",
                                recorded_date=datetime.now()))
    db.commit()
    r = client.post("/api/v1/billing/7/submit", json={"user_id": 2, "user_role": "caregiver"}, headers=CAREGIVER)
    assert r.status_code == 200
    mine = db.query(models.Notification).filter(models.Notification.user_id == 1).all()
    assert [n.kind for n in mine] == ["claim_submitted"]
    assert "요양사A" in mine[0].message and "김이용" in mine[0].message
    assert db.query(models.Notification).filter(models.Notification.user_id == 5).count() == 0  # 다른 센터 센터장
    assert db.query(models.BillingRecord).get(7).approval_status == "pending"


def test_caregiver_board_counts_per_caregiver(env):
    db, client = env
    now = datetime.now()
    db.add_all([
        models.User(id=3, email="b@test.com", full_name="요양사B", role="caregiver", center_id=1),
        models.User(id=6, email="x@test.com", full_name="타센터요양사", role="caregiver", center_id=2),
    ])
    resident = db.query(models.Resident).get(1)
    resident.primary_caregiver_id = 2
    db.add_all([
        # 오늘 방문: A는 2건 중 1건 도착, 취소 건은 제외
        models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=now, status="scheduled", arrived_at=now, left_at=now),
        models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=now, status="scheduled"),
        models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=now, status="cancelled"),
        # 기록 누락: 시간이 지났는데 도착·기록이 없는 오늘 일정 1건 + 이틀 전 일정 1건 (도착·퇴실을 마친 건은 제외)
        models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=now - timedelta(days=2), status="scheduled"),
        models.BillingRecord(caregiver_id=2, resident_id=1, center_id=1, approval_status="draft", recorded_date=now),
        models.BillingRecord(caregiver_id=3, resident_id=1, center_id=1, approval_status="rejected", recorded_date=now),
        models.DailyRecord(resident_id=1, caregiver_id=3, recorded_date=now, notes="x"),
    ])
    db.commit()
    rows = {r["name"]: r for r in client.get("/api/v1/inbox/caregivers", headers=MANAGER).json()["caregivers"]}
    assert set(rows) == {"요양사A", "요양사B"}  # 다른 센터 요양보호사는 안 나옴
    a, b = rows["요양사A"], rows["요양사B"]
    assert (a["residents"], a["today_planned"], a["today_arrived"], a["missing_records"], a["draft_claims"]) == (1, 2, 1, 2, 1)
    assert (b["rejected_claims"], b["month_records"], b["residents"]) == (1, 1, 0)


def test_caregiver_board_is_manager_only(env):
    _, client = env
    assert client.get("/api/v1/inbox/caregivers", headers=CAREGIVER).status_code == 403


def test_new_rows_use_korean_local_time_not_utc(env):
    """알림 목록이 9시간 전으로 보이던 문제: 저장 기본 시각이 UTC(utcnow)가 아니라 서버 시간(한국)이어야 한다."""
    db, _ = env
    from datetime import datetime
    n = models.Notification(user_id=1, kind="claim_submitted", message="x")
    db.add(n)
    db.commit()
    assert abs((n.created_at - datetime.now()).total_seconds()) < 5
