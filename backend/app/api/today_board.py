"""오늘 방문 현황판: 그날 계획된 방문이 지금 어떤 상태인지(예정·진행중·기록완료·확인 필요)를 센터장에게 보여준다.

공단 전송 여부는 전자태그 기기 연동이 없어 여기서 알 수 없다. 그 확인은 '공단 태그 대조' 화면에서 파일로 한다."""
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import require_manager
from app.database import get_db
from app.models import DailyRecord, Resident, Schedule, User

router = APIRouter()
LATE_MINUTES = 30  # 계획 시각이 이만큼 지났는데도 도착 기록이 없으면 확인 필요


def _status(s: Schedule, has_record: bool, now: datetime) -> str:
    if has_record or s.status == "completed":
        return "recorded"
    if s.arrived_at and not s.left_at:
        return "in_progress"
    if s.arrived_at and s.left_at:
        return "left_unrecorded"
    if now >= s.scheduled_date + timedelta(minutes=LATE_MINUTES):
        return "check"
    return "upcoming"


@router.get("")
def board(day: Optional[date] = Query(None), db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    now = datetime.now()
    target = day or now.date()
    start = datetime.combine(target, datetime.min.time())
    end = start + timedelta(days=1)
    schedules = db.query(Schedule).filter(
        Schedule.center_id == actor.center_id, Schedule.status != "cancelled",
        Schedule.scheduled_date >= start, Schedule.scheduled_date < end).order_by(Schedule.scheduled_date).all()
    recorded_ids = {r.schedule_id for r in db.query(DailyRecord).join(Resident, Resident.id == DailyRecord.resident_id).filter(
        Resident.center_id == actor.center_id, DailyRecord.schedule_id.isnot(None),
        DailyRecord.recorded_date >= start, DailyRecord.recorded_date < end).all()}
    names = {r.id: r.name for r in db.query(Resident).filter(Resident.center_id == actor.center_id).all()}
    staff = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}

    rows = []
    for s in schedules:
        status = _status(s, s.id in recorded_ids, now)
        rows.append({"schedule_id": s.id, "resident": names.get(s.resident_id, ""), "caregiver": staff.get(s.caregiver_id, ""),
                     "planned": s.scheduled_date.strftime("%H:%M"), "duration": s.duration_minutes,
                     "arrived": s.arrived_at.strftime("%H:%M") if s.arrived_at else None,
                     "left": s.left_at.strftime("%H:%M") if s.left_at else None, "status": status})
    counts = {k: sum(1 for r in rows if r["status"] == k)
              for k in ("upcoming", "in_progress", "left_unrecorded", "check", "recorded")}
    total = len(rows)
    return {"status": "success", "data": {
        "date": target.isoformat(), "generated_at": now.strftime("%H:%M"),
        "total": total, "counts": counts,
        "record_rate": round(counts["recorded"] * 100 / total) if total else None,
        "rows": rows,
        "note": "공단 전송 여부는 이 화면에서 알 수 없습니다. 전송 확인은 '공단 태그 대조'에서 합니다.",
    }}
