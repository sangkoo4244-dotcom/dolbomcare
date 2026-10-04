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

@router.get("/caregiver-view")
def caregiver_schedule_view(
    caregiver_id: int,
    year_month: str,
    db: Session = Depends(get_db)
):
    """요양사 방문 계획: 계획된 방문과 실제 기록을 날짜·이용자 기준으로 맞추고, 계획 항목 이행 여부를 함께 반환"""
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
    names = {rid: name for rid, name in db.query(Resident.id, Resident.name).all()}

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
            state = "완료"
            done = [c for c in _codes(match.care_items) if c in planned]
            record_id = match.id
            duration = s.duration_minutes or match.duration_minutes
        else:
            state = "미기록" if s.scheduled_date < now else "예정"
            done = []
            record_id = None
            duration = s.duration_minutes
        items.append({
            "date": day.isoformat(),
            "time": s.scheduled_date.strftime("%H:%M"),
            "resident_id": s.resident_id,
            "resident_name": names.get(s.resident_id),
            "duration_minutes": duration,
            "planned_items": planned,
            "done_items": done,
            "state": state,
            "daily_record_id": record_id,
            "schedule_id": s.id,
            "planned": True,
        })

    for r in records:
        if r.id in used:
            continue
        items.append({
            "date": r.recorded_date.date().isoformat(),
            "time": r.recorded_date.strftime("%H:%M"),
            "resident_id": r.resident_id,
            "resident_name": names.get(r.resident_id),
            "duration_minutes": r.duration_minutes,
            "planned_items": [],
            "done_items": _codes(r.care_items),
            "state": "계획 외",
            "daily_record_id": r.id,
            "schedule_id": None,
            "planned": False,
        })

    items.sort(key=lambda x: (x["date"], x["time"]))
    summary = {}
    for it in items:
        summary[it["state"]] = summary.get(it["state"], 0) + 1

    return {"year_month": year_month, "items": items, "summary": summary}
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
