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
    assert mine == {"missing_record": 1, "draft_claims": 1, "rejected_claims": 1, "change_requests": 1, "schedule_changes": 0,
                    "handover_unread": 1, "incident_incomplete": 2, "objections": 0, "anomalies": 0}
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
    assert db.get(models.BillingRecord, 7).approval_status == "pending"


def test_caregiver_board_counts_per_caregiver(env):
    db, client = env
    now = datetime.now()
    db.add_all([
        models.User(id=3, email="b@test.com", full_name="요양사B", role="caregiver", center_id=1),
        models.User(id=6, email="x@test.com", full_name="타센터요양사", role="caregiver", center_id=2),
    ])
    resident = db.get(models.Resident, 1)
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


def test_visits_overview_covers_whole_center(env):
    db, client = env
    now = datetime.now()
    if now.day == 1:
        pytest.skip("매달 1일에는 '이번 달의 지난 일정'을 만들 수 없다")
    earlier_this_month = now.replace(day=1, hour=9, minute=0, second=0, microsecond=0)
    db.add_all([
        models.User(id=3, email="b@test.com", full_name="요양사B", role="caregiver", center_id=1),
        models.User(id=6, email="x@test.com", full_name="타센터요양사", role="caregiver", center_id=2),
        models.Resident(id=2, center_id=2, name="타센터이용자"),
        # 오늘 일정: A는 도착·퇴실까지 마쳤지만 기록은 없음(기록 필요), B는 앞으로 올 일정
        models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=now - timedelta(minutes=1), status="scheduled",
                        arrived_at=now - timedelta(minutes=50), left_at=now - timedelta(minutes=5)),
        models.Schedule(caregiver_id=3, resident_id=1, center_id=1, scheduled_date=now + timedelta(minutes=1), status="scheduled"),
        # 이번 달 앞쪽 일정인데 도착·기록이 없음 → 미기록
        models.Schedule(caregiver_id=3, resident_id=1, center_id=1, scheduled_date=earlier_this_month, status="scheduled"),
        # 승인 대기 계획과 다른 센터 일정은 포함되면 안 된다
        models.Schedule(caregiver_id=3, resident_id=1, center_id=1, scheduled_date=now + timedelta(days=1), status="proposed"),
        models.Schedule(caregiver_id=6, resident_id=2, center_id=2, scheduled_date=earlier_this_month, status="scheduled"),
    ])
    db.commit()
    data = client.get("/api/v1/inbox/visits-overview", headers=MANAGER).json()
    assert {(r["caregiver"], r["state"]) for r in data["today"]} == {("요양사A", "방문완료"), ("요양사B", "예정")}
    assert {(r["caregiver"], r["state"]) for r in data["missing"]} == {("요양사A", "방문완료"), ("요양사B", "미기록")}
    assert data["missing_total"] == 2
    assert data["month"]["total"] == 3 and data["month"]["missing"] == 1


def test_today_summary_counts_states_and_arrival_rate_and_lateness(env):
    db, client = env
    now = datetime.now()
    if (now.hour == 0 and now.minute < 40) or (now.hour == 23 and now.minute >= 29):
        pytest.skip("자정 근처에는 '오늘' 일정을 만들 수 없다")
    min_ = lambda m: now + timedelta(minutes=m)  # noqa: E731
    db.add_all([models.User(id=i, email=f"c{i}@test.com", full_name=f"요양사{i}", role="caregiver", center_id=1) for i in (3, 4, 7, 8)])
    db.add_all([
        # 3: 도착·퇴실·기록까지 끝남(완료)
        models.Schedule(caregiver_id=3, resident_id=1, center_id=1, scheduled_date=min_(-30), status="scheduled", arrived_at=min_(-28), left_at=min_(-5)),
        models.DailyRecord(resident_id=1, caregiver_id=3, recorded_date=min_(-6)),
        # 4: 도착했고 아직 방문 중
        models.Schedule(caregiver_id=4, resident_id=1, center_id=1, scheduled_date=min_(-20), status="scheduled", arrived_at=min_(-18)),
        # 7: 시작 시각이 지났는데 도착도 기록도 없음(미처리)
        models.Schedule(caregiver_id=7, resident_id=1, center_id=1, scheduled_date=min_(-10), status="scheduled"),
        # 8: 도착·퇴실은 했는데 기록이 없음(확인 필요)
        models.Schedule(caregiver_id=8, resident_id=1, center_id=1, scheduled_date=min_(-15), status="scheduled", arrived_at=min_(-14), left_at=min_(-2)),
        # A: 앞으로 올 일정
        models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=min_(30), status="scheduled"),
    ])
    db.commit()
    data = client.get("/api/v1/inbox/visits-overview", headers=MANAGER).json()
    s = data["today_summary"]
    assert (s["total"], s["scheduled"], s["in_progress"], s["done"], s["need_check"], s["late"]) == (5, 1, 1, 1, 1, 1)
    assert (s["started"], s["arrived"], s["arrival_rate"]) == (4, 3, 75)  # 예정 1건은 비율에서 뺀다
    late = next(r for r in data["today"] if r["state"] == "미기록")
    assert late["caregiver"] == "요양사7" and 9 <= late["late_minutes"] <= 11 and late["arrived_at"] is None
    assert all("late_minutes" not in r for r in data["today"] if r["state"] != "미기록")


def test_today_summary_without_started_visits_has_no_rate(env):
    _, client = env
    s = client.get("/api/v1/inbox/visits-overview", headers=MANAGER).json()["today_summary"]
    assert s["total"] == 0 and s["arrival_rate"] is None


def test_visits_overview_is_manager_only(env):
    _, client = env
    assert client.get("/api/v1/inbox/visits-overview", headers=CAREGIVER).status_code == 403
