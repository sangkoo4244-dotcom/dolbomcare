from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.models import Schedule, User, Resident, Center, DailyRecord
from app.database import get_db
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

class ScheduleUpdate(BaseModel):
    scheduled_date: str = None
    service_type: str = None
    status: str = None
    notes: str = None
    duration_minutes: int = None
    planned_items: str = None

class ScheduleStatusUpdate(BaseModel):
    status: str  # 'scheduled', 'completed', 'cancelled'

router = APIRouter()

@router.get("/")
async def get_schedules(
    center_id: int = None,
    caregiver_id: int = None,
    resident_id: int = None,
    status: str = None,
    db: Session = Depends(get_db)
):
    """스케줄 목록 조회 (필터링 가능)"""
    query = db.query(Schedule)

    if center_id:
        query = query.filter(Schedule.center_id == center_id)
    if caregiver_id:
        query = query.filter(Schedule.caregiver_id == caregiver_id)
    if resident_id:
        query = query.filter(Schedule.resident_id == resident_id)
    if status:
        query = query.filter(Schedule.status == status)

    schedules = query.order_by(Schedule.scheduled_date).all()

    return {
        "total": len(schedules),
        "schedules": [
            {
                "id": s.id,
                "caregiver_id": s.caregiver_id,
                "resident_id": s.resident_id,
                "center_id": s.center_id,
                "scheduled_date": s.scheduled_date.isoformat(),
                "service_type": s.service_type,
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
    db: Session = Depends(get_db)
):
    """스케줄 생성 (센터장만 가능)"""
    try:
        # 요양사, 이용자, 센터 검증
        caregiver = db.query(User).filter(User.id == schedule_data.caregiver_id).first()
        if not caregiver:
            raise HTTPException(status_code=404, detail="요양사를 찾을 수 없습니다")

        resident = db.query(Resident).filter(Resident.id == schedule_data.resident_id).first()
        if not resident:
            raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")

        center = db.query(Center).filter(Center.id == schedule_data.center_id).first()
        if not center:
            raise HTTPException(status_code=404, detail="센터를 찾을 수 없습니다")

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

def _codes(value):
    return [c for c in (value or "").split(",") if c]

def _visit_state(schedule, matched, now):
    if matched:
        return "완료"
    if schedule.arrived_at:
        return "미기록" if schedule.left_at else "방문중"
    return "미기록" if schedule.scheduled_date < now else "예정"

@router.get("/caregiver-view")
def caregiver_schedule_view(
    caregiver_id: int,
    year_month: str,
    db: Session = Depends(get_db)
):
    """요양사 방문 계획: 계획된 방문과 실제 기록·도착/퇴실 시각을 날짜·이용자 기준으로 맞춘 결과"""
    start = datetime.strptime(f"{year_month}-01", "%Y-%m-%d")
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    now = datetime.now()

    schedules = db.query(Schedule).filter(
        Schedule.caregiver_id == caregiver_id,
        Schedule.scheduled_date >= start,
        Schedule.scheduled_date < end,
        Schedule.status != "cancelled",
    ).all()
    records = db.query(DailyRecord).filter(
        DailyRecord.caregiver_id == caregiver_id,
        DailyRecord.recorded_date >= start,
        DailyRecord.recorded_date < end,
    ).all()
    residents = {x.id: x for x in db.query(Resident).all()}

    used = set()
    items = []
    for s in schedules:
        planned = _codes(s.planned_items)
        day = s.scheduled_date.date()
        match = next(
            (r for r in records if r.id not in used and r.resident_id == s.resident_id and r.recorded_date.date() == day),
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
            "address": resident.address if resident else None,
            "care_notes": resident.care_notes if resident else None,
            "duration_minutes": s.duration_minutes or (match.duration_minutes if match else None),
            "planned_items": planned,
            "done_items": [c for c in _codes(match.care_items) if c in planned] if match else [],
            "state": state,
            "daily_record_id": match.id if match else None,
            "schedule_id": s.id,
            "arrived_at": s.arrived_at.isoformat() if s.arrived_at else None,
            "left_at": s.left_at.isoformat() if s.left_at else None,
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
            "address": resident.address if resident else None,
            "care_notes": resident.care_notes if resident else None,
            "duration_minutes": r.duration_minutes,
            "planned_items": [],
            "done_items": _codes(r.care_items),
            "state": "계획 외",
            "daily_record_id": r.id,
            "schedule_id": None,
            "arrived_at": None,
            "left_at": None,
            "planned": False,
        })

    items.sort(key=lambda x: (x["date"], x["time"]))
    summary = {}
    for it in items:
        summary[it["state"]] = summary.get(it["state"], 0) + 1

    return {"year_month": year_month, "items": items, "summary": summary}

@router.post("/{schedule_id}/arrive")
def mark_arrived(schedule_id: int, db: Session = Depends(get_db)):
    """도착 시각 기록 (이미 도착한 경우 처음 시각 유지)"""
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다")
    if schedule.arrived_at is None:
        schedule.arrived_at = datetime.now()
        db.commit()
    return {"status": "success", "arrived_at": schedule.arrived_at.isoformat()}

@router.post("/{schedule_id}/depart")
def mark_left(schedule_id: int, db: Session = Depends(get_db)):
    """퇴실 시각 기록 (도착 기록 이후에만 가능)"""
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="일정을 찾을 수 없습니다")
    if schedule.arrived_at is None:
        raise HTTPException(status_code=400, detail="도착 기록 후 퇴실을 기록할 수 있습니다")
    if schedule.left_at is None:
        schedule.left_at = datetime.now()
        db.commit()
    return {"status": "success", "left_at": schedule.left_at.isoformat()}
@router.get("/{schedule_id}")
async def get_schedule(schedule_id: int, db: Session = Depends(get_db)):
    """스케줄 상세 조회"""
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
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
    db: Session = Depends(get_db)
):
    """스케줄 수정 (센터장만 가능)"""
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if not schedule:
        raise HTTPException(status_code=404, detail="스케줄을 찾을 수 없습니다")

    try:
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
                "status": schedule.status,
                "notes": schedule.notes
            }
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"스케줄 수정 중 오류: {str(e)}")

@router.patch("/{schedule_id}/status")
async def update_schedule_status(
    schedule_id: int,
    status_data: ScheduleStatusUpdate,
    db: Session = Depends(get_db)
):
    """스케줄 상태 변경"""
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
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
async def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    """스케줄 삭제 (센터장만 가능)"""
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
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
