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

# 날짜를 고정한다: 오늘 기준으로 잡으면 일요일에 걸려 가산 표시와 금액이 달라진다
DAY = datetime(2026, 10, 13, 0, 0, 0)  # 화요일, 공휴일 아님
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


def add_benefit_visit(db, rid, hour, minutes, *, caregiver=2, benefit="home_bath", bath_mode=None, co=None, note=None):
    """방문목욕·방문간호 기록 한 건(일정·청구 포함)을 만든다."""
    sch = models.Schedule(caregiver_id=caregiver, resident_id=rid, center_id=1, scheduled_date=DAY + timedelta(hours=hour), duration_minutes=minutes,
                          status="scheduled", arrived_at=DAY + timedelta(hours=hour), left_at=DAY + timedelta(hours=hour, minutes=minutes),
                          benefit_type=benefit, bath_mode=bath_mode, co_caregiver_id=co)
    db.add(sch)
    db.flush()
    rec = models.DailyRecord(resident_id=rid, caregiver_id=caregiver, recorded_date=DAY + timedelta(hours=hour), duration_minutes=minutes, schedule_id=sch.id,
                             care_items="bath", benefit_type=benefit, bath_mode=bath_mode, co_caregiver_id=co, nursing_order_note=note)
    db.add(rec)
    db.flush()
    db.add(models.BillingRecord(daily_record_id=rec.id, caregiver_id=caregiver, resident_id=rid, center_id=1, amount=75650, total_cost=88990,
                                approval_status="approved", recorded_date=rec.recorded_date, year_month=MONTH, benefit_type=benefit))
    db.commit()


def test_bath_and_nursing_rows_use_nhis_service_names_and_their_own_checks(ctx):
    client, Session = ctx
    db = Session()
    db.add(models.User(id=7, email="n@e.com", hashed_password="x", full_name="간호사", role="caregiver", center_id=1, job_type="간호사"))
    db.commit()
    add_benefit_visit(db, 1, 7, 60, benefit="home_bath", bath_mode="vehicle_in", co=3)            # 정상 2인 목욕
    add_benefit_visit(db, 2, 20, 60, benefit="home_bath", bath_mode="no_vehicle", co=None)         # 동행자 기록 없음
    add_benefit_visit(db, 3, 21, 30, caregiver=7, benefit="home_nursing", note="지시서 2026-10-01")
    add_benefit_visit(db, 4, 22, 30, caregiver=7, benefit="home_nursing", note=None)               # 지시서 메모 없음
    # 함께 간 요양보호사(3)가 같은 시각에 다른 이용자를 방문했다면 겹침으로 본다
    visit(db, 2, 7, 60, caregiver=3)
    db.close()
    data = get(client).json()
    rows = by_name(data)
    kim = [v for v in rows["김일"]["visits"] if v["benefit_type"] == "home_bath"][0]
    assert kim["service"] == "방문목욕" and "차량 이용(차량 내 목욕)" in kim["detail"] and "함께 간 요양보호사 이요양" in kim["detail"]
    assert "overlap_caregiver" in kim["flags"]  # 동행자가 같은 시각 다른 방문
    two = rows["이이"]["visits"]
    solo = [v for v in two if v["benefit_type"] == "home_bath" and "bath_no_partner" in v["flags"]]
    assert len(solo) == 1 and "차량 미이용" in solo[0]["detail"]
    nursing_ok = [v for v in rows["박삼"]["visits"] if v["benefit_type"] == "home_nursing"][0]
    assert nursing_ok["service"] == "방문간호" and nursing_ok["detail"] == "지시서: 지시서 2026-10-01" and "nursing_no_order" not in nursing_ok["flags"]
    assert "nursing_no_order" in [v for v in rows["최사"]["visits"] if v["benefit_type"] == "home_nursing"][0]["flags"]
    # 방문요양 전용 확인(5등급·장시간)은 목욕·간호 방문에 붙지 않는다
    assert not {"grade5", "long_visit"} & set(nursing_ok["flags"])
    assert set(data["flag_counts"]) <= set(data["flag_labels"])


def test_pair_visits_are_not_flagged_as_overlap_and_bath_time_and_weekly_rules_are_checked(ctx):
    client, Session = ctx
    db = Session()
    # 방문요양 2인 동시 제공: 같은 이용자, 같은 시각, 요양보호사 둘 — 서로 이어진 기록이면 겹침으로 보지 않는다
    for cg, other in ((2, 3), (3, 2)):
        sch = models.Schedule(caregiver_id=cg, resident_id=2, center_id=1, scheduled_date=DAY + timedelta(hours=18), duration_minutes=60,
                              status="scheduled", arrived_at=DAY + timedelta(hours=18), left_at=DAY + timedelta(hours=19))
        db.add(sch)
        db.flush()
        rec = models.DailyRecord(resident_id=2, caregiver_id=cg, recorded_date=DAY + timedelta(hours=18), duration_minutes=60, schedule_id=sch.id,
                                 care_items="bath", benefit_type="home_care", co_caregiver_id=other, special_note="보호자 동의, 와상 상태")
        db.add(rec)
        db.flush()
        db.add(models.BillingRecord(daily_record_id=rec.id, caregiver_id=cg, resident_id=2, center_id=1, amount=21530, total_cost=25320,
                                    approval_status="approved", recorded_date=rec.recorded_date, year_month=MONTH, benefit_type="home_care"))
    db.flush()
    first, second = db.query(models.DailyRecord).filter(models.DailyRecord.special_note.like("보호자 동의%")).order_by(models.DailyRecord.id).all()
    first.pair_record_id, second.pair_record_id = second.id, first.id
    db.commit()
    # 방문목욕: 같은 주에 두 번(둘째는 사유 없음), 45분(80%), 30분(청구 불가 - 예전 기록)
    add_benefit_visit(db, 3, 7, 45, benefit="home_bath", bath_mode="vehicle_in", co=3)
    add_benefit_visit(db, 3, 9, 30, benefit="home_bath", bath_mode="vehicle_in", co=3)
    db.close()
    rows = by_name(get(client).json())
    pair_rows = [v for v in rows["이이"]["visits"] if v["detail"].startswith("2인 동시 제공")]
    assert len(pair_rows) == 2 and all("overlap_resident" not in v["flags"] for v in pair_rows)
    assert "보호자 동의" in pair_rows[0]["detail"]
    baths = sorted([v for v in rows["박삼"]["visits"] if v["benefit_type"] == "home_bath"], key=lambda v: v["start"])
    assert "bath_reduced" in baths[0]["flags"] and "bath_weekly_over" not in baths[0]["flags"]
    assert "bath_too_short" in baths[1]["flags"] and "bath_weekly_over" in baths[1]["flags"]
