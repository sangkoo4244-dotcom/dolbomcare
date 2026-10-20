from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from app.geo import judge


class PlaceBody(BaseModel):
    lat: Optional[float] = None
    lng: Optional[float] = None
    accuracy: Optional[float] = None  # 휴대폰이 알려 준 위치 오차(m)
from sqlalchemy.orm import Session
from app.models import Schedule, User, Resident, Center, DailyRecord, Notification
from app.api.notifications import notify
from app.review import record_fits_schedule
from app.visit_benefit import normalize_visit_benefit
from sqlalchemy import or_
from app.database import get_db
from app.auth import get_current_user, require_manager, assert_self_or_manager, assert_my_center
from datetime import datetime, timedelta

class ScheduleCreate(BaseModel):
    caregiver_id: int
    resident_id: int
    center_id: int
    scheduled_date: str  # ISO 형식 (YYYY-MM-DDTHH:mm:ss)
    service_type: str = "basic_care"
    notes: str = None
    duration_minutes: int = None
    planned_items: str = None
    benefit_type: Optional[str] = None  # home_care(기본)/home_bath/home_nursing
    bath_mode: Optional[str] = None
    co_caregiver_id: Optional[int] = None

class ScheduleUpdate(BaseModel):
    scheduled_date: str = None
    service_type: str = None
    status: str = None
    notes: str = None
    duration_minutes: int = None
    planned_items: str = None
    benefit_type: Optional[str] = None
    bath_mode: Optional[str] = None
    co_caregiver_id: Optional[int] = None

class ScheduleStatusUpdate(BaseModel):
    status: str  # 'scheduled', 'completed', 'cancelled'

router = APIRouter()

@router.get("/")
async def get_schedules(
    center_id: int = None,
    caregiver_id: int = None,
    resident_id: int = None,
    status: str = None,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """스케줄 목록 조회 (필터링 가능). 항상 로그인한 사람의 센터 일정만 보인다."""
    if actor.role not in ("caregiver", "center_manager") or not actor.center_id:
        raise HTTPException(status_code=403, detail="일정을 볼 수 있는 권한이 없습니다")
    query = db.query(Schedule).filter(Schedule.center_id == actor.center_id)
    if caregiver_id:
        query = query.filter(Schedule.caregiver_id == caregiver_id)
    if resident_id:
        query = query.filter(Schedule.resident_id == resident_id)
    if status:
        query = query.filter(Schedule.status == status)

    schedules = query.order_by(Schedule.scheduled_date).all()
    residents = {x.id: x.name for x in db.query(Resident).all()}
    caregivers = {x.id: x.full_name for x in db.query(User).all()}

    return {
        "total": len(schedules),
        "schedules": [
            {
                "id": s.id,
                "caregiver_id": s.caregiver_id,
                "caregiver_name": caregivers.get(s.caregiver_id),
                "resident_id": s.resident_id,
                "resident_name": residents.get(s.resident_id),
                "center_id": s.center_id,
                "scheduled_date": s.scheduled_date.isoformat(),
                "duration_minutes": s.duration_minutes,
                "planned_items": _codes(s.planned_items),
                "arrived_at": s.arrived_at.isoformat() if s.arrived_at else None,
                "left_at": s.left_at.isoformat() if s.left_at else None,
                "review_note": s.review_note,
                "service_type": s.service_type,
                "benefit_type": s.benefit_type or "home_care",
                "bath_mode": s.bath_mode,
                "co_caregiver_id": s.co_caregiver_id,
                "co_caregiver_name": caregivers.get(s.co_caregiver_id),
                "status": s.status,
                "notes": s.notes,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat()
            }
            for s in schedules
        ]
    }

@router.post("/")
async def create_schedule(
    schedule_data: ScheduleCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_manager)
):
    """스케줄 생성 (센터장만 가능, 내 센터의 요양사·이용자만)"""
    try:
        # 요양사, 이용자, 센터 검증
        caregiver = db.query(User).filter(User.id == schedule_data.caregiver_id, User.center_id == actor.center_id).first()
        if not caregiver:
            raise HTTPException(status_code=404, detail="요양사를 찾을 수 없습니다")

        resident = db.query(Resident).filter(Resident.id == schedule_data.resident_id, Resident.center_id == actor.center_id).first()
        if not resident:
            raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")

        center = db.query(Center).filter(Center.id == schedule_data.center_id).first()
        if not center:
            raise HTTPException(status_code=404, detail="센터를 찾을 수 없습니다")

        visit = normalize_visit_benefit(db, center_id=schedule_data.center_id, caregiver_id=schedule_data.caregiver_id,
                                        benefit_type=schedule_data.benefit_type, bath_mode=schedule_data.bath_mode,
                                        co_caregiver_id=schedule_data.co_caregiver_id, duration_minutes=schedule_data.duration_minutes)

        # 스케줄 생성
        scheduled_datetime = datetime.fromisoformat(schedule_data.scheduled_date)

        new_schedule = Schedule(
            caregiver_id=schedule_data.caregiver_id,
            resident_id=schedule_data.resident_id,
            center_id=schedule_data.center_id,
            scheduled_date=scheduled_datetime,
            service_type=schedule_data.service_type,
            notes=schedule_data.notes,
            duration_minutes=schedule_data.duration_minutes,
            planned_items=schedule_data.planned_items or None,
            benefit_type=visit["benefit_type"], bath_mode=visit["bath_mode"], co_caregiver_id=visit["co_caregiver_id"],
            status="scheduled"
        )

        db.add(new_schedule)
        db.commit()
        db.refresh(new_schedule)

        return {
            "status": "success",
            "message": "스케줄이 생성되었습니다",
            "data": {
                "id": new_schedule.id,
                "caregiver_id": new_schedule.caregiver_id,
                "resident_id": new_schedule.resident_id,
                "scheduled_date": new_schedule.scheduled_date.isoformat(),
                "service_type": new_schedule.service_type,
                "status": new_schedule.status,
                "notes": new_schedule.notes
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"스케줄 생성 중 오류: {str(e)}")

class RecurringCreate(BaseModel):
    caregiver_id: int
    resident_id: int
    weekdays: list  # 0=월 ... 6=일
    start_date: str  # YYYY-MM-DD
    end_date: str
    start_time: str  # HH:MM
    duration_minutes: int = None
    service_type: str = "basic_care"
    planned_items: str = None
    benefit_type: Optional[str] = None
    bath_mode: Optional[str] = None
    co_caregiver_id: Optional[int] = None

MAX_RECURRING_DAYS = 92

@router.post("/recurring")
def create_recurring_schedule(req: RecurringCreate, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    """요일별 반복 방문을 기간 안의 날짜마다 한 번에 만든다 (같은 요양사·이용자·날짜에 이미 있으면 건너뜀)"""
    caregiver = db.query(User).filter(User.id == req.caregiver_id, User.center_id == actor.center_id, User.role == "caregiver").first()
    resident = db.query(Resident).filter(Resident.id == req.resident_id, Resident.center_id == actor.center_id).first()
    if not caregiver or not resident:
        raise HTTPException(status_code=404, detail="요양사 또는 이용자를 찾을 수 없습니다")
    try:
        start = datetime.fromisoformat(req.start_date).date()
        end = datetime.fromisoformat(req.end_date).date()
        hour, minute = (int(x) for x in req.start_time.split(":"))
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 또는 시간 형식이 올바르지 않습니다")
    visit = normalize_visit_benefit(db, center_id=actor.center_id, caregiver_id=caregiver.id, benefit_type=req.benefit_type,
                                    bath_mode=req.bath_mode, co_caregiver_id=req.co_caregiver_id, duration_minutes=req.duration_minutes)
    weekdays = {int(d) for d in req.weekdays if str(d).isdigit() and 0 <= int(d) <= 6}
    if not weekdays:
        raise HTTPException(status_code=400, detail="방문 요일을 하나 이상 선택해 주세요")
    if end < start or (end - start).days >= MAX_RECURRING_DAYS:
        raise HTTPException(status_code=400, detail=f"기간은 시작일 이후 {MAX_RECURRING_DAYS}일 이내로 정해 주세요")
    existing = {s.scheduled_date.date() for s in db.query(Schedule).filter(
        Schedule.caregiver_id == caregiver.id, Schedule.resident_id == resident.id,
        Schedule.scheduled_date >= datetime.combine(start, datetime.min.time()),
        Schedule.scheduled_date < datetime.combine(end + timedelta(days=1), datetime.min.time()),
        Schedule.status != "cancelled").all()}
    created, skipped = 0, 0
    day = start
    while day <= end:
        if day.weekday() in weekdays:
            if day in existing:
                skipped += 1
            else:
                db.add(Schedule(caregiver_id=caregiver.id, resident_id=resident.id, center_id=actor.center_id,
                                scheduled_date=datetime(day.year, day.month, day.day, hour, minute),
                                duration_minutes=req.duration_minutes, service_type=req.service_type or "basic_care",
                                planned_items=req.planned_items or None, status="scheduled",
                                benefit_type=visit["benefit_type"], bath_mode=visit["bath_mode"], co_caregiver_id=visit["co_caregiver_id"]))
                created += 1
        day += timedelta(days=1)
    if created:
        notify(db, caregiver.id, "schedule_assigned", f"{resident.name} 어르신 방문 일정 {created}건이 등록되었습니다. 나의 일정에서 확인해 주세요.")
    db.commit()
    return {"status": "success", "created": created, "skipped": skipped}

def _codes(value):
    return [c for c in (value or "").split(",") if c]

def _record_view(r, residents):
    """화면의 '기록 보기'에 보여 줄 실제 기록 내용 (계획과 따로 저장된 값을 그대로 쓴다).
    이용자 이름과 이용자 번호를 함께 돌려줘서, 화면에서 같은 사람의 기록인지 바로 확인할 수 있게 한다."""
    if r is None:
        return None
    resident = residents.get(r.resident_id)
    return {
        "id": r.id,
        "resident_id": r.resident_id,
        "resident_name": resident.name if resident else None,
        "recorded_date": r.recorded_date.strftime("%Y-%m-%d %H:%M") if r.recorded_date else None,
        "duration_minutes": r.duration_minutes,
        "care_items": _codes(r.care_items),
        "condition": r.condition,
        "notes": r.notes,
        "service_type": r.service_type,
    }

def _my_schedule(db, schedule_id, actor):
    """내 센터의 일정만 돌려준다(다른 센터 일정은 없는 것으로 본다)."""
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    return schedule if schedule and actor.center_id is not None and schedule.center_id == actor.center_id else None


def _assert_visit_day(schedule):
    """도착·퇴실은 방문 날짜 당일에만 기록할 수 있다. 다른 날 일정에 도착을 찍어 기록을 미리 만드는 것을 막는다."""
    if schedule.scheduled_date.date() != datetime.now().date():
        raise HTTPException(status_code=400, detail="방문 당일에만 도착·퇴실을 기록할 수 있습니다")

def _assert_owner(schedule, user_id, user_role):
    if user_role not in ("caregiver", "center_manager"):
        raise HTTPException(status_code=403, detail="요양보호사만 기록할 수 있습니다")
    if user_role == "caregiver" and schedule.caregiver_id != user_id:
        raise HTTPException(status_code=403, detail="본인의 일정만 기록할 수 있습니다")

def _visit_state(schedule, matched, now):
    if schedule.status == "proposed":
        return "승인 대기"
    if schedule.status == "rejected":
        return "반려"
    if matched and schedule.left_at:
        return "완료"
    if schedule.arrived_at:
        return "방문완료" if schedule.left_at else "방문중"
    if matched:
        return "도착 미기록"  # 기록은 저장됐는데 도착 버튼을 누르지 않음: '기록 없음'(미기록)과 구분한다
    return "미기록" if schedule.scheduled_date < now else "예정"

@router.get("/caregiver-view")
def caregiver_schedule_view(
    caregiver_id: int,
    year_month: str,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """요양사 방문 계획: 계획된 방문과 실제 기록·도착/퇴실 시각을 날짜·이용자 기준으로 맞춘 결과"""
    if actor.role not in ("caregiver", "center_manager"):
        raise HTTPException(status_code=403, detail="일정을 볼 수 있는 권한이 없습니다")
    if actor.role == "caregiver" and actor.id != caregiver_id:
        raise HTTPException(status_code=403, detail="본인의 일정만 조회할 수 있습니다")
    if actor.role == "center_manager":
        assert_self_or_manager(actor, caregiver_id, db)
    start = datetime.strptime(f"{year_month}-01", "%Y-%m-%d")
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    now = datetime.now()

    # 방문목욕처럼 2인이 함께 가는 방문은 함께 가는 요양보호사의 일정에도 보인다(companion). 기록은 주 담당자가 쓴다.
    schedules = db.query(Schedule).filter(
        or_(Schedule.caregiver_id == caregiver_id, Schedule.co_caregiver_id == caregiver_id),
        Schedule.scheduled_date >= start,
        Schedule.scheduled_date < end,
        Schedule.status != "cancelled",
    ).all()
    records = db.query(DailyRecord).filter(
        DailyRecord.caregiver_id == caregiver_id,
        DailyRecord.recorded_date >= start,
        DailyRecord.recorded_date < end,
    ).all()
    primary_ids = {s.caregiver_id for s in schedules if s.caregiver_id != caregiver_id}
    primary_records = db.query(DailyRecord).filter(
        DailyRecord.caregiver_id.in_(primary_ids),
        DailyRecord.recorded_date >= start,
        DailyRecord.recorded_date < end,
    ).all() if primary_ids else []
    residents = {x.id: x for x in db.query(Resident).all()}
    staff_ids = {s.co_caregiver_id for s in schedules if s.co_caregiver_id} | primary_ids
    staff_names = {x.id: x.full_name for x in db.query(User).filter(User.id.in_(staff_ids)).all()} if staff_ids else {}

    used = set()
    items = []
    for s in schedules:
        planned = _codes(s.planned_items)
        day = s.scheduled_date.date()
        match = None
        companion = s.caregiver_id != caregiver_id
        pool = [r for r in primary_records if r.caregiver_id == s.caregiver_id] if companion else records
        if s.status == "scheduled":
            # 기록이 이 방문에 직접 연결돼 있으면(화면에서 고른 방문) 그것을 우선 쓰고, 없으면 방문 시간대로 찾는다
            match = next((r for r in pool if r.id not in used and r.schedule_id == s.id), None) or next(
                (r for r in pool if r.id not in used and r.resident_id == s.resident_id and record_fits_schedule(s, r.recorded_date)),
                None,
            )
        if match:
            used.add(match.id)
        state = _visit_state(s, match, now)
        resident = residents.get(s.resident_id)
        items.append({
            "date": day.isoformat(),
            "time": s.scheduled_date.strftime("%H:%M"),
            "resident_id": s.resident_id,
            "resident_name": resident.name if resident else None,
            "resident_gender": resident.gender if resident else None,
            "address": resident.address if resident else None,
            "care_notes": resident.care_notes if resident else None,
            "duration_minutes": s.duration_minutes or (match.duration_minutes if match else None),
            "service_type": s.service_type,
            "benefit_type": s.benefit_type or "home_care",
            "bath_mode": s.bath_mode,
            "co_caregiver_id": s.co_caregiver_id,
            "co_caregiver_name": staff_names.get(s.co_caregiver_id),
            "companion": companion,
            "primary_caregiver_name": staff_names.get(s.caregiver_id) if companion else None,
            "planned_items": planned,
            "done_items": [c for c in _codes(match.care_items) if c in planned] if match else [],
            "state": state,
            "daily_record_id": match.id if match else None,
            "record": _record_view(match, residents),
            "schedule_id": s.id,
            "arrived_at": s.arrived_at.isoformat() if s.arrived_at else None,
            "left_at": s.left_at.isoformat() if s.left_at else None,
            "review_note": s.review_note,
            "change_date": s.change_date.strftime("%Y-%m-%d %H:%M") if s.change_date else None,
            "change_reason": s.change_reason,
            "change_service_type": s.change_service_type,
            "change_planned_items": _codes(s.change_planned_items) if s.change_planned_items is not None else None,
            "planned": True,
        })

    for r in records:
        if r.id in used:
            continue
        resident = residents.get(r.resident_id)
        items.append({
            "date": r.recorded_date.date().isoformat(),
            "time": r.recorded_date.strftime("%H:%M"),
            "resident_id": r.resident_id,
            "resident_name": resident.name if resident else None,
            "resident_gender": resident.gender if resident else None,
            "address": resident.address if resident else None,
            "care_notes": resident.care_notes if resident else None,
            "duration_minutes": r.duration_minutes,
            "service_type": r.service_type,
            "planned_items": [],
            "done_items": _codes(r.care_items),
            "state": "완료",
            "daily_record_id": r.id,
            "record": _record_view(r, residents),
            "schedule_id": None,
            "arrived_at": None,
            "left_at": None,
            "planned": False,
        })

    items.sort(key=lambda x: (x["date"], x["time"]))
    summary = {}
    for it in items:
        summary[it["state"]] = summary.get(it["state"], 0) + 1

    # 오늘 방문 계획이 있으면 하루 한 번만 리마인더 알림을 보낸다 (이 화면을 열 때마다 중복 발송하지 않는다)
    today_key = now.date().isoformat()
    today_planned = [it for it in items if it["date"] == today_key and it["planned"]]
    if today_planned:
        day_start = datetime.combine(now.date(), datetime.min.time())
        already_sent = db.query(Notification).filter(
            Notification.user_id == caregiver_id,
            Notification.kind == "schedule_today",
            Notification.created_at >= day_start,
        ).first()
        if not already_sent:
            notify(db, caregiver_id, "schedule_today", f"오늘 {len(today_planned)}건의 방문 일정이 있습니다")
            db.commit()

    return {"year_month": year_month, "items": items, "summary": summary}

def _place_check(db: Session, schedule, body):
    """이용자 주소 좌표와 휴대폰 위치를 비교한다. 좌표는 버리고 판정과 거리만 돌려준다."""
    resident = db.query(Resident).filter(Resident.id == schedule.resident_id).first()
    body = body or PlaceBody()
    return judge(resident.latitude if resident else None, resident.longitude if resident else None,
                 body.lat, body.lng, body.accuracy)


@router.post("/{schedule_id}/arrive")
def mark_arrived(schedule_id: int, body: Optional[PlaceBody] = None, db: Session = Depends(get_db),
                 actor: User = Depends(get_current_user)):
    """도착 시각 기록 (이미 도착한 경우 처음 시각 유지). 위치를 보내면 이용자 주소와 비교해 판정을 남긴다."""
    schedule = _my_schedule(db, schedule_id, actor)
    if not schedule:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다")
    _assert_owner(schedule, actor.id, actor.role)
    if schedule.status != "scheduled":
        raise HTTPException(status_code=400, detail="센터장이 승인한 일정만 도착을 기록할 수 있습니다")
    _assert_visit_day(schedule)
    if schedule.arrived_at is None:
        schedule.arrived_at = datetime.now()
        schedule.arrive_check, schedule.arrive_distance_m = _place_check(db, schedule, body)
        db.commit()
    return {"status": "success", "arrived_at": schedule.arrived_at.isoformat()}

@router.post("/{schedule_id}/depart")
def mark_left(schedule_id: int, body: Optional[PlaceBody] = None, db: Session = Depends(get_db),
              actor: User = Depends(get_current_user)):
    """퇴실 시각 기록 (도착 기록 이후에만 가능). 처음 퇴실 기록 시 방문 기록 작성 알림을 보낸다."""
    schedule = _my_schedule(db, schedule_id, actor)
    if not schedule:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다")
    _assert_owner(schedule, actor.id, actor.role)
    if schedule.status != "scheduled":
        raise HTTPException(status_code=400, detail="센터장이 승인한 일정만 퇴실을 기록할 수 있습니다")
    _assert_visit_day(schedule)
    if schedule.arrived_at is None:
        raise HTTPException(status_code=400, detail="도착 기록 후 퇴실을 기록할 수 있습니다")
    if schedule.left_at is None:
        schedule.left_at = datetime.now()
        schedule.depart_check, schedule.depart_distance_m = _place_check(db, schedule, body)
        resident = db.query(Resident).filter(Resident.id == schedule.resident_id).first()
        resident_label = f"{resident.name} " if resident else ""
        notify(db, schedule.caregiver_id, "record_needed", f"{resident_label}방문 기록을 작성해 주세요")
        db.commit()
    return {"status": "success", "left_at": schedule.left_at.isoformat()}
class ProposalRequest(BaseModel):
    user_id: int
    user_role: str
    caregiver_id: int
    resident_id: int
    scheduled_date: str
    duration_minutes: int = None
    planned_items: str = None
    service_type: str = "basic_care"
    notes: str = None
    benefit_type: Optional[str] = None
    bath_mode: Optional[str] = None
    co_caregiver_id: Optional[int] = None

class ReviewRequest(BaseModel):
    user_id: int
    user_role: str
    reason: str = ""

class ResubmitRequest(BaseModel):
    user_id: int
    user_role: str
    scheduled_date: str = None
    duration_minutes: int = None
    planned_items: str = None
    service_type: str = None
    bath_mode: Optional[str] = None
    co_caregiver_id: Optional[int] = None

@router.post("/propose")
def propose_schedule(req: ProposalRequest, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """요양사가 방문 계획을 제안 (센터장 승인 대기)"""
    if actor.role != "caregiver" or actor.id != req.caregiver_id:
        raise HTTPException(status_code=403, detail="요양사 본인의 방문 계획만 제안할 수 있습니다")
    resident = db.query(Resident).filter(Resident.id == req.resident_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    visit = normalize_visit_benefit(db, center_id=resident.center_id, caregiver_id=req.caregiver_id, benefit_type=req.benefit_type,
                                    bath_mode=req.bath_mode, co_caregiver_id=req.co_caregiver_id, duration_minutes=req.duration_minutes)
    schedule = Schedule(
        caregiver_id=req.caregiver_id,
        resident_id=req.resident_id,
        center_id=resident.center_id,
        scheduled_date=datetime.fromisoformat(req.scheduled_date),
        duration_minutes=req.duration_minutes,
        planned_items=req.planned_items or None,
        service_type=req.service_type or "basic_care",
        benefit_type=visit["benefit_type"], bath_mode=visit["bath_mode"], co_caregiver_id=visit["co_caregiver_id"],
        notes=req.notes,
        status="proposed",
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return {"status": "success", "schedule_id": schedule.id, "message": "방문 계획을 제안했습니다. 센터장 승인을 기다려 주세요"}

@router.get("/proposals")
def list_proposals(center_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """센터장 승인 대기·반려 계획 목록"""
    if actor.role != "center_manager":
        raise HTTPException(status_code=403, detail="센터장만 조회할 수 있습니다")
    assert_my_center(actor, center_id)
    rows = db.query(Schedule).filter(
        Schedule.center_id == center_id,
        Schedule.status.in_(["proposed", "rejected"]),
    ).order_by(Schedule.scheduled_date).all()
    residents = {x.id: x.name for x in db.query(Resident).all()}
    caregivers = {x.id: x.full_name for x in db.query(User).all()}
    return {
        "items": [
            {
                "schedule_id": s.id,
                "status": s.status,
                "caregiver_id": s.caregiver_id,
                "caregiver_name": caregivers.get(s.caregiver_id),
                "resident_id": s.resident_id,
                "resident_name": residents.get(s.resident_id),
                "scheduled_date": s.scheduled_date.strftime("%Y-%m-%d %H:%M"),
                "duration_minutes": s.duration_minutes,
                "planned_items": _codes(s.planned_items),
                "review_note": s.review_note,
                "service_type": s.service_type,
                "benefit_type": s.benefit_type or "home_care",
                "bath_mode": s.bath_mode,
                "co_caregiver_id": s.co_caregiver_id,
                "co_caregiver_name": caregivers.get(s.co_caregiver_id),
            }
            for s in rows
        ]
    }

@router.post("/{schedule_id}/approve")
def approve_schedule(schedule_id: int, req: ReviewRequest, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """센터장이 방문 계획 승인 → 요양사 나의일정에 확정"""
    if actor.role != "center_manager":
        raise HTTPException(status_code=403, detail="센터장만 승인할 수 있습니다")
    schedule = _my_schedule(db, schedule_id, actor)
    if not schedule:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다")
    if schedule.status != "proposed":
        raise HTTPException(status_code=400, detail="승인 대기 중인 계획만 승인할 수 있습니다")
    schedule.status = "scheduled"
    schedule.review_note = None
    notify(db, schedule.caregiver_id, "plan_approved", f"방문 계획이 승인되었습니다 ({schedule.scheduled_date:%m/%d %H:%M})")
    db.commit()
    return {"status": "success", "schedule_id": schedule.id, "schedule_status": schedule.status}

@router.post("/{schedule_id}/reject")
def reject_schedule(schedule_id: int, req: ReviewRequest, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """센터장이 방문 계획 반려 (사유 필수)"""
    if actor.role != "center_manager":
        raise HTTPException(status_code=403, detail="센터장만 반려할 수 있습니다")
    reason = (req.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="반려 사유를 입력해 주세요")
    schedule = _my_schedule(db, schedule_id, actor)
    if not schedule:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다")
    if schedule.status != "proposed":
        raise HTTPException(status_code=400, detail="승인 대기 중인 계획만 반려할 수 있습니다")
    schedule.status = "rejected"
    schedule.review_note = reason
    notify(db, schedule.caregiver_id, "plan_rejected", f"방문 계획이 반려되었습니다: {reason}")
    db.commit()
    return {"status": "success", "schedule_id": schedule.id, "schedule_status": schedule.status}

@router.post("/{schedule_id}/resubmit")
def resubmit_schedule(schedule_id: int, req: ResubmitRequest, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """요양사가 반려된 계획을 수정해 다시 제안"""
    if actor.role != "caregiver":
        raise HTTPException(status_code=403, detail="요양사만 다시 제안할 수 있습니다")
    schedule = _my_schedule(db, schedule_id, actor)
    if not schedule:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다")
    _assert_owner(schedule, actor.id, actor.role)
    if schedule.status != "rejected":
        raise HTTPException(status_code=400, detail="반려된 계획만 다시 제안할 수 있습니다")
    if req.scheduled_date:
        schedule.scheduled_date = datetime.fromisoformat(req.scheduled_date)
    if req.duration_minutes is not None:
        schedule.duration_minutes = req.duration_minutes
    if req.planned_items is not None:
        schedule.planned_items = req.planned_items or None
    if req.service_type:
        schedule.service_type = req.service_type
    visit = normalize_visit_benefit(db, center_id=schedule.center_id, caregiver_id=schedule.caregiver_id, benefit_type=schedule.benefit_type,
                                    bath_mode=req.bath_mode or schedule.bath_mode, co_caregiver_id=req.co_caregiver_id or schedule.co_caregiver_id,
                                    duration_minutes=schedule.duration_minutes)
    schedule.bath_mode, schedule.co_caregiver_id = visit["bath_mode"], visit["co_caregiver_id"]
    schedule.status = "proposed"
    schedule.review_note = None
    db.commit()
    return {"status": "success", "schedule_id": schedule.id, "schedule_status": schedule.status}

class ChangeRequest(BaseModel):
    scheduled_date: str
    duration_minutes: int = None
    service_type: str = None
    planned_items: str = None  # 쉼표로 이은 제공 항목 코드 (빈 문자열이면 항목 없음, None이면 변경 없음)
    reason: str = ""


def _clear_change(schedule):
    schedule.change_date = None
    schedule.change_duration = None
    schedule.change_reason = None
    schedule.change_service_type = None
    schedule.change_planned_items = None


@router.post("/{schedule_id}/change-request")
def request_schedule_change(schedule_id: int, req: ChangeRequest, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """요양보호사가 승인된 예정 일정의 날짜·시간 변경을 요청 (센터장 승인 전까지 원래 일정 유지)"""
    if actor.role != "caregiver":
        raise HTTPException(status_code=403, detail="요양보호사만 변경을 요청할 수 있습니다")
    schedule = _my_schedule(db, schedule_id, actor)
    if not schedule:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다")
    _assert_owner(schedule, actor.id, actor.role)
    if schedule.status != "scheduled" or schedule.arrived_at is not None:
        raise HTTPException(status_code=400, detail="아직 방문하지 않은 승인된 일정만 변경을 요청할 수 있습니다")
    reason = (req.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="변경 사유를 입력해 주세요")
    new_date = datetime.fromisoformat(req.scheduled_date)
    new_service = req.service_type if req.service_type and req.service_type != schedule.service_type else None
    new_items = None
    if req.planned_items is not None and sorted(_codes(req.planned_items)) != sorted(_codes(schedule.planned_items)):
        new_items = req.planned_items
    if new_date == schedule.scheduled_date and req.duration_minutes in (None, schedule.duration_minutes) and new_service is None and new_items is None:
        raise HTTPException(status_code=400, detail="기존 일정과 같습니다")
    schedule.change_date = new_date
    schedule.change_duration = req.duration_minutes
    schedule.change_service_type = new_service
    schedule.change_planned_items = new_items
    schedule.change_reason = reason
    resident = db.query(Resident).filter(Resident.id == schedule.resident_id).first()
    for mgr in db.query(User).filter(User.center_id == schedule.center_id, User.role == "center_manager", User.is_active == True).all():  # noqa: E712
        notify(db, mgr.id, "schedule_change_requested",
               f"{actor.full_name} 요양보호사가 {resident.name if resident else ''} 방문 일정 변경을 요청했습니다 ({schedule.scheduled_date:%m/%d %H:%M} → {new_date:%m/%d %H:%M})")
    db.commit()
    return {"status": "success", "schedule_id": schedule.id, "message": "변경을 요청했습니다. 센터장이 승인하기 전까지는 기존 일정으로 방문해 주세요"}


@router.post("/{schedule_id}/change-cancel")
def cancel_schedule_change(schedule_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """요양보호사가 보낸 변경 요청을 철회"""
    schedule = _my_schedule(db, schedule_id, actor)
    if not schedule:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다")
    _assert_owner(schedule, actor.id, actor.role)
    if schedule.change_date is None:
        raise HTTPException(status_code=400, detail="대기 중인 변경 요청이 없습니다")
    _clear_change(schedule)
    db.commit()
    return {"status": "success", "schedule_id": schedule.id}


@router.get("/change-requests")
def list_change_requests(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    """센터장 승인 대기 중인 일정 변경 요청"""
    rows = db.query(Schedule).filter(Schedule.center_id == actor.center_id, Schedule.change_date.isnot(None)).order_by(Schedule.scheduled_date).all()
    residents = {x.id: x.name for x in db.query(Resident).filter(Resident.center_id == actor.center_id).all()}
    caregivers = {x.id: x.full_name for x in db.query(User).filter(User.center_id == actor.center_id).all()}
    return {"items": [{
        "schedule_id": s.id,
        "caregiver_name": caregivers.get(s.caregiver_id),
        "resident_name": residents.get(s.resident_id),
        "from_date": s.scheduled_date.strftime("%Y-%m-%d %H:%M"),
        "to_date": s.change_date.strftime("%Y-%m-%d %H:%M"),
        "from_duration": s.duration_minutes,
        "to_duration": s.change_duration,
        "from_service_type": s.service_type,
        "to_service_type": s.change_service_type,
        "from_items": _codes(s.planned_items),
        "to_items": _codes(s.change_planned_items) if s.change_planned_items is not None else None,
        "reason": s.change_reason,
    } for s in rows]}


@router.post("/{schedule_id}/change-approve")
def approve_schedule_change(schedule_id: int, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id, Schedule.center_id == actor.center_id).first()
    if not schedule or schedule.change_date is None:
        raise HTTPException(status_code=404, detail="대기 중인 변경 요청을 찾을 수 없습니다")
    schedule.scheduled_date = schedule.change_date
    if schedule.change_duration is not None:
        schedule.duration_minutes = schedule.change_duration
    if schedule.change_service_type:
        schedule.service_type = schedule.change_service_type
    if schedule.change_planned_items is not None:
        schedule.planned_items = schedule.change_planned_items or None
    _clear_change(schedule)
    notify(db, schedule.caregiver_id, "schedule_change_approved", f"일정 변경이 승인되었습니다 ({schedule.scheduled_date:%m/%d %H:%M})")
    db.commit()
    return {"status": "success", "schedule_id": schedule.id}


@router.post("/{schedule_id}/change-reject")
def reject_schedule_change(schedule_id: int, req: ReviewRequest, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    reason = (req.reason or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="반려 사유를 입력해 주세요")
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id, Schedule.center_id == actor.center_id).first()
    if not schedule or schedule.change_date is None:
        raise HTTPException(status_code=404, detail="대기 중인 변경 요청을 찾을 수 없습니다")
    _clear_change(schedule)
    notify(db, schedule.caregiver_id, "schedule_change_rejected", f"일정 변경이 반려되었습니다. 기존 일정({schedule.scheduled_date:%m/%d %H:%M})으로 방문해 주세요: {reason}")
    db.commit()
    return {"status": "success", "schedule_id": schedule.id}


@router.get("/{schedule_id}")
async def get_schedule(schedule_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """스케줄 상세 조회"""
    schedule = _my_schedule(db, schedule_id, actor)
    if not schedule:
        raise HTTPException(status_code=404, detail="스케줄을 찾을 수 없습니다")

    return {
        "status": "success",
        "data": {
            "id": schedule.id,
            "caregiver_id": schedule.caregiver_id,
            "resident_id": schedule.resident_id,
            "center_id": schedule.center_id,
            "scheduled_date": schedule.scheduled_date.isoformat(),
            "service_type": schedule.service_type,
            "status": schedule.status,
            "notes": schedule.notes,
            "created_at": schedule.created_at.isoformat(),
            "updated_at": schedule.updated_at.isoformat()
        }
    }

@router.put("/{schedule_id}")
async def update_schedule(
    schedule_id: int,
    update_data: ScheduleUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_manager)
):
    """스케줄 수정 (센터장만 가능)"""
    schedule = _my_schedule(db, schedule_id, actor)
    if not schedule:
        raise HTTPException(status_code=404, detail="스케줄을 찾을 수 없습니다")

    try:
        new_duration = update_data.duration_minutes if update_data.duration_minutes is not None else schedule.duration_minutes
        visit = normalize_visit_benefit(db, center_id=schedule.center_id, caregiver_id=schedule.caregiver_id,
                                        benefit_type=update_data.benefit_type or schedule.benefit_type,
                                        bath_mode=update_data.bath_mode or schedule.bath_mode,
                                        co_caregiver_id=update_data.co_caregiver_id or schedule.co_caregiver_id, duration_minutes=new_duration)
        schedule.benefit_type, schedule.bath_mode, schedule.co_caregiver_id = visit["benefit_type"], visit["bath_mode"], visit["co_caregiver_id"]
        if update_data.scheduled_date:
            schedule.scheduled_date = datetime.fromisoformat(update_data.scheduled_date)
        if update_data.service_type:
            schedule.service_type = update_data.service_type
        if update_data.status:
            schedule.status = update_data.status
        if update_data.notes is not None:
            schedule.notes = update_data.notes
        if update_data.duration_minutes is not None:
            schedule.duration_minutes = update_data.duration_minutes
        if update_data.planned_items is not None:
            schedule.planned_items = update_data.planned_items or None

        db.commit()
        db.refresh(schedule)

        return {
            "status": "success",
            "message": "스케줄이 수정되었습니다",
            "data": {
                "id": schedule.id,
                "scheduled_date": schedule.scheduled_date.isoformat(),
                "service_type": schedule.service_type,
                "benefit_type": schedule.benefit_type or "home_care",
                "status": schedule.status,
                "notes": schedule.notes
            }
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"스케줄 수정 중 오류: {str(e)}")

@router.patch("/{schedule_id}/status")
async def update_schedule_status(
    schedule_id: int,
    status_data: ScheduleStatusUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_manager)
):
    """스케줄 상태 변경"""
    schedule = _my_schedule(db, schedule_id, actor)
    if not schedule:
        raise HTTPException(status_code=404, detail="스케줄을 찾을 수 없습니다")

    if status_data.status not in ["scheduled", "completed", "cancelled"]:
        raise HTTPException(status_code=400, detail="유효한 상태가 아닙니다")

    try:
        schedule.status = status_data.status
        db.commit()
        db.refresh(schedule)

        return {
            "status": "success",
            "message": f"스케줄 상태가 '{status_data.status}'로 변경되었습니다",
            "data": {
                "id": schedule.id,
                "status": schedule.status,
                "updated_at": schedule.updated_at.isoformat()
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"상태 변경 중 오류: {str(e)}")

@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: int, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    """스케줄 삭제 (센터장만 가능)"""
    schedule = _my_schedule(db, schedule_id, actor)
    if not schedule:
        raise HTTPException(status_code=404, detail="스케줄을 찾을 수 없습니다")

    try:
        db.delete(schedule)
        db.commit()

        return {
            "status": "success",
            "message": "스케줄이 삭제되었습니다",
            "data": {"id": schedule_id}
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"스케줄 삭제 중 오류: {str(e)}")
