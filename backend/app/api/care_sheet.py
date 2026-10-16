"""장기요양급여 제공기록지(방문요양) - 공단 서식(시행규칙 별지 제12호, 2025.12 개정) 한 주 분량을 모아 준다.

센터가 평가·점검 때 종이 기록지를 내야 할 때 방문 기록을 서식 모양으로 출력하는 용도다.
공단 시스템에 전송하는 기능이 아니다.
"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Center, DailyRecord, Resident, Schedule, User

router = APIRouter()


def _merge_day(records: list, schedules: dict, names: dict) -> dict:
    """하루에 방문이 여러 번이면 제공 항목은 합치고 시간은 더한다."""
    items = []
    for r in records:
        for code in (r.care_items or "").split(","):
            if code and code not in items:
                items.append(code)

    def last(field):
        for r in reversed(records):
            if getattr(r, field):
                return getattr(r, field)
        return None

    def total(field):
        values = [getattr(r, field) for r in records if getattr(r, field) is not None]
        return sum(values) if values else None

    starts, ends = [], []
    for r in records:
        sch = schedules.get(r.schedule_id)
        starts.append(sch.arrived_at if sch and sch.arrived_at else r.recorded_date)
        if sch and sch.left_at:
            ends.append(sch.left_at)

    notes = " / ".join(r.notes.strip() for r in records if r.notes and r.notes.strip())
    item_minutes = {}
    for r in records:  # "meal_assist:30,bath:30" 형식을 항목별로 더한다 (공단 서식의 영역별 제공시간용)
        for part in (r.item_minutes or "").split(","):
            code, _, minutes = part.partition(":")
            if code and minutes.isdigit():
                item_minutes[code] = item_minutes.get(code, 0) + int(minutes)
    return {
        "item_minutes": item_minutes,
        "care_items": items,
        "total_minutes": total("duration_minutes"),
        "start_time": min(starts).strftime("%H:%M") if starts else None,
        "end_time": max(ends).strftime("%H:%M") if ends else None,
        "physical_change": last("physical_change"),
        "meal_change": last("meal_change"),
        "cognitive_change": last("cognitive_change"),
        "stool_accidents": total("stool_accidents"),
        "urine_accidents": total("urine_accidents"),
        "notes": notes,
        "has_signature": any(r.signature for r in records),
        "caregivers": sorted({names.get(r.caregiver_id, "") for r in records} - {""}),
    }


@router.get("")
def care_sheet(
    resident_id: int = Query(...),
    week_start: date = Query(..., description="주의 시작 날짜(YYYY-MM-DD). 이 날부터 7일을 보여 준다"),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """센터장은 센터 이용자 전체, 요양보호사는 본인이 작성한 기록만 서식에 넣는다."""
    if actor.role not in ("center_manager", "caregiver", "social_worker"):
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    resident = db.query(Resident).filter(Resident.id == resident_id, Resident.center_id == actor.center_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    center = db.query(Center).filter(Center.id == actor.center_id).first()

    start = datetime.combine(week_start, datetime.min.time())
    end = start + timedelta(days=7)
    q = db.query(DailyRecord).filter(
        DailyRecord.resident_id == resident_id,
        DailyRecord.recorded_date >= start,
        DailyRecord.recorded_date < end,
    )
    if actor.role == "caregiver":
        q = q.filter(DailyRecord.caregiver_id == actor.id)
    records = q.order_by(DailyRecord.recorded_date).all()

    schedule_ids = {r.schedule_id for r in records if r.schedule_id}
    schedules = {s.id: s for s in db.query(Schedule).filter(Schedule.id.in_(schedule_ids)).all()} if schedule_ids else {}
    names = {u.id: u.full_name for u in db.query(User).filter(User.id.in_({r.caregiver_id for r in records})).all()} if records else {}

    by_day = {}
    for r in records:
        by_day.setdefault(r.recorded_date.date(), []).append(r)
    days = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        day = {"date": d.isoformat(), "visited": d in by_day}
        if d in by_day:
            day.update(_merge_day(by_day[d], schedules, names))
        days.append(day)

    return {
        "resident": {
            "name": resident.name,
            "birth_date": resident.birth_date.isoformat() if resident.birth_date else None,
            "care_grade": resident.care_grade,
            "recognition_number": resident.recognition_number,
        },
        "center": {"name": center.name if center else None, "institution_code": center.institution_code if center else None},
        "days": days,
    }


@router.get("/visits")
def visit_sheet(
    resident_id: int = Query(...),
    week_start: date = Query(...),
    benefit_type: str = Query(..., description="home_bath 또는 home_nursing"),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """방문목욕·방문간호 기록지(공단 서식 101·102)용 방문 목록. 방문 한 번이 서식 한 칸이다. 저장하지 않은 칸(상태 확인, 혈압 등)은 비워 둔다."""
    if benefit_type not in ("home_bath", "home_nursing"):
        raise HTTPException(status_code=400, detail="목욕 또는 간호 기록지만 볼 수 있습니다")
    if actor.role not in ("center_manager", "caregiver", "social_worker"):
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    resident = db.query(Resident).filter(Resident.id == resident_id, Resident.center_id == actor.center_id).first() if actor.center_id else None
    if not resident:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    start = datetime.combine(week_start, datetime.min.time())
    rows = db.query(DailyRecord).filter(
        DailyRecord.resident_id == resident_id, DailyRecord.benefit_type == benefit_type,
        DailyRecord.bath_companion.isnot(True),  # 동행 기록은 주 담당 방문 한 칸에 함께 적는다 (중복 방지)
        DailyRecord.recorded_date >= start, DailyRecord.recorded_date < start + timedelta(days=7),
    ).order_by(DailyRecord.recorded_date).all()
    if actor.role == "caregiver":
        rows = [r for r in rows if r.caregiver_id == actor.id or r.co_caregiver_id == actor.id]
    schedules = {s.id: s for s in db.query(Schedule).filter(Schedule.id.in_({r.schedule_id for r in rows if r.schedule_id})).all()} if rows else {}
    names = {u.id: u.full_name for u in db.query(User).filter(User.id.in_({x for r in rows for x in (r.caregiver_id, r.co_caregiver_id) if x})).all()} if rows else {}
    visits = []
    for r in rows:
        sch = schedules.get(r.schedule_id)
        began = sch.arrived_at if sch and sch.arrived_at else r.recorded_date
        ended = sch.left_at if sch and sch.left_at else None
        visits.append({
            "date": r.recorded_date.date().isoformat(),
            "start_time": began.strftime("%H:%M"),
            "end_time": ended.strftime("%H:%M") if ended else None,
            "total_minutes": r.duration_minutes,
            "caregivers": [n for n in (names.get(r.caregiver_id), names.get(r.co_caregiver_id)) if n],
            "bath_mode": r.bath_mode,
            "solo_exception": bool(r.bath_solo_exception),
            "special_note": r.special_note,
            "nursing_order_note": r.nursing_order_note,
            "notes": r.notes,
            "has_signature": bool(r.signature),
        })
    return {"status": "success", "data": {
        "resident": {"name": resident.name, "birth_date": resident.birth_date.isoformat() if resident.birth_date else None,
                     "care_grade": resident.care_grade, "recognition_number": resident.recognition_number},
        "visits": visits,
    }}
