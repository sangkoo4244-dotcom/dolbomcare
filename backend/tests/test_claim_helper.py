from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import claim_helper
from app.api.users import create_access_token
from app.database import Base, get_db

DAY = (datetime.now() - timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
MONTH = DAY.strftime("%Y-%m")


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MGR = auth(1, "center_manager", "m@e.com")
CG = auth(2, "caregiver", "c@e.com")
OTHER_MGR = auth(9, "center_manager", "o@e.com")


def visit(db, rid, hour, minutes, *, arrived=True, caregiver=2, status="approved", items="meal_assist,bath"):
    """방문 계획 + 일지 + 청구를 한 번에 만든다. arrived=False면 도착·퇴실 기록이 없다."""
    sch = models.Schedule(caregiver_id=caregiver, resident_id=rid, center_id=1, scheduled_date=DAY + timedelta(hours=hour),
                          duration_minutes=minutes, status="scheduled",
                          arrived_at=DAY + timedelta(hours=hour) if arrived else None,
                          left_at=DAY + timedelta(hours=hour, minutes=minutes) if arrived else None)
    db.add(sch)
    db.flush()
    rec = models.DailyRecord(resident_id=rid, caregiver_id=caregiver, recorded_date=DAY + timedelta(hours=hour), duration_minutes=minutes,
                             schedule_id=sch.id, care_items=items)
    db.add(rec)
    db.flush()
    db.add(models.BillingRecord(daily_record_id=rec.id, caregiver_id=caregiver, resident_id=rid, center_id=1, amount=21520, total_cost=25320,
                                approval_status=status, recorded_date=rec.recorded_date, year_month=MONTH))
    db.commit()


@pytest.fixture
def ctx(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ch.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A"), models.Center(id=2, name="B"),
        models.User(id=1, email="m@e.com", hashed_password="x", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@e.com", hashed_password="x", full_name="김요양", role="caregiver", center_id=1),
        models.User(id=3, email="c3@e.com", hashed_password="x", full_name="이요양", role="caregiver", center_id=1),
        models.User(id=9, email="o@e.com", hashed_password="x", full_name="타센터장", role="center_manager", center_id=2),
        models.Resident(id=1, center_id=1, name="김일", age=80, health_status="stable", care_grade=3, client_type="일반", recognition_number="L1"),
        models.Resident(id=2, center_id=1, name="이이", age=80, health_status="stable", care_grade=3, client_type="일반"),
        models.Resident(id=3, center_id=1, name="박삼", age=80, health_status="stable", care_grade=5, client_type="일반"),
        models.Resident(id=4, center_id=1, name="최사", age=80, health_status="stable", care_grade=2, client_type="일반",
                        recognition_end=(DAY - timedelta(days=10)).date()),
    ])
    db.commit()
    visit(db, 1, 9, 60)                                   # 정상
    visit(db, 2, 9, 60, caregiver=2)                      # 같은 요양보호사가 09시에 두 이용자 -> 겹침
    visit(db, 3, 13, 60, arrived=False, status="pending")  # 도착 기록 없음 + 5등급 + 승인 전
    visit(db, 4, 15, 60)                                  # 인정기간 만료
    db.close()
    app = FastAPI()
    app.include_router(claim_helper.router, prefix="/api/v1/claim-helper")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app), Session


def get(client, headers=MGR, month=MONTH):
    return client.get(f"/api/v1/claim-helper?year_month={month}", headers=headers)


def by_name(data):
    return {r["name"]: r for r in data["residents"]}


def test_rows_follow_nhis_screen_and_totals_count_only_approved(ctx):
    client, _ = ctx
    r = get(client)
    assert r.status_code == 200
    data = r.json()
    kim = by_name(data)["김일"]
    v = kim["visits"][0]
    assert (v["date"], v["start"], v["end"], v["minutes"], v["service"]) == (DAY.strftime("%Y-%m-%d"), "09:00", "10:00", 60, "방문요양")
    assert v["caregiver"] == "김요양" and v["items"] == ["식사 보조", "목욕·세면"]
    assert kim["recognition_number"] == "L1" and kim["totals"]["total_cost"] == 25320 and kim["totals"]["claim_amount"] == 21520
    # 승인 전 건은 목록엔 보이지만 합계에서는 빠진다
    park = by_name(data)["박삼"]
    assert park["totals"]["visits"] == 1 and park["totals"]["approved_visits"] == 0 and park["totals"]["total_cost"] == 0
    assert data["visit_count"] == 4


def test_flags_point_out_what_to_check_before_typing_into_nhis(ctx):
    client, _ = ctx
    data = get(client).json()
    rows = by_name(data)
    assert rows["김일"]["visits"][0]["flags"] == ["overlap_caregiver"]  # 김요양이 09시에 이이도 방문
    assert "overlap_caregiver" in rows["이이"]["visits"][0]["flags"]
    assert set(rows["박삼"]["visits"][0]["flags"]) == {"no_arrival", "grade5"}
    assert rows["최사"]["visits"][0]["flags"] == ["recognition_expired"]
    assert data["flag_counts"]["overlap_caregiver"] == 2 and data["flag_counts"]["no_arrival"] == 1
    assert set(data["flag_counts"]) <= set(data["flag_labels"])


def test_same_resident_overlap_and_long_visit_and_time_gap(ctx):
    client, Session = ctx
    db = Session()
    visit(db, 1, 9, 30, caregiver=3)    # 김일에게 같은 시간 다른 요양보호사 -> 2인 제공/중복
    visit(db, 2, 18, 240)               # 3등급 240분 -> 210분 이상 연속
    sch = db.query(models.Schedule).filter(models.Schedule.resident_id == 2, models.Schedule.duration_minutes == 240).one()
    sch.left_at = sch.arrived_at + timedelta(minutes=120)  # 실제로는 120분만 머묾 -> 시간 차이
    db.commit()
    db.close()
    rows = by_name(get(client).json())
    kim_flags = [set(v["flags"]) for v in rows["김일"]["visits"]]
    assert all("overlap_resident" in f for f in kim_flags)
    lee = next(v for v in rows["이이"]["visits"] if v["minutes"] == 240)
    assert {"long_visit", "time_gap"} <= set(lee["flags"]) and lee["stay_minutes"] == 120


def test_guards_empty_month_bad_month_other_center_and_role(ctx):
    client, _ = ctx
    assert get(client, month="2020-01").json()["residents"] == []
    assert get(client, month="2020-13").status_code == 400
    assert get(client, month="abc").status_code == 400
    assert get(client, headers=OTHER_MGR).json()["residents"] == []  # 다른 센터 자료는 보이지 않는다
    assert get(client, headers=CG).status_code == 403
