"""출퇴근 기록: 직원이 출근·퇴근을 누르고, 센터장은 월별 근무 현황과 방문-출근 불일치를 본다."""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_manager
from app.database import get_db
from app.models import DailyRecord, User, WorkLog

router = APIRouter()
STAFF_ROLES = ("caregiver", "social_worker", "center_manager")


def _staff(actor: User) -> User:
    if actor.role not in STAFF_ROLES or not actor.center_id:
        raise HTTPException(status_code=403, detail="직원만 출퇴근을 기록할 수 있습니다")
    return actor


def _month_range(ym: str):
    try:
        y, m = map(int, ym.split("-"))
        start = date(y, m, 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="월은 YYYY-MM 형식으로 적어 주세요")
    if not 1 <= m <= 12:
        raise HTTPException(status_code=400, detail="월은 YYYY-MM 형식으로 적어 주세요")
    end = date(y + (m == 12), (m % 12) + 1, 1)
    return start, end


def _hours(log: WorkLog) -> Optional[float]:
    if not log.clock_out:
        return None
    return round((log.clock_out - log.clock_in).total_seconds() / 3600, 2)


@router.post("/clock-in")
def clock_in(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    _staff(actor)
    open_log = db.query(WorkLog).filter(WorkLog.staff_id == actor.id, WorkLog.clock_out.is_(None)).first()
    if open_log:
        raise HTTPException(status_code=400, detail="이미 출근 중입니다. 퇴근을 먼저 눌러 주세요")
    log = WorkLog(center_id=actor.center_id, staff_id=actor.id, work_date=date.today(), clock_in=datetime.now())
    db.add(log)
    db.commit()
    return {"status": "success", "data": {"id": log.id, "clock_in": log.clock_in.strftime("%H:%M")}}


@router.post("/clock-out")
def clock_out(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    _staff(actor)
    log = db.query(WorkLog).filter(WorkLog.staff_id == actor.id, WorkLog.clock_out.is_(None)).order_by(WorkLog.id.desc()).first()
    if not log:
        raise HTTPException(status_code=400, detail="출근 기록이 없습니다")
    log.clock_out = datetime.now()
    db.commit()
    return {"status": "success", "data": {"clock_out": log.clock_out.strftime("%H:%M"), "hours": _hours(log)}}


@router.get("/me")
def my_month(year_month: str = Query(...), db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    _staff(actor)
    start, end = _month_range(year_month)
    rows = db.query(WorkLog).filter(WorkLog.staff_id == actor.id, WorkLog.work_date >= start, WorkLog.work_date < end) \
        .order_by(WorkLog.work_date, WorkLog.id).all()
    items = [{"id": r.id, "work_date": r.work_date.isoformat(), "clock_in": r.clock_in.strftime("%H:%M"),
              "clock_out": r.clock_out.strftime("%H:%M") if r.clock_out else None, "hours": _hours(r)} for r in rows]
    return {"status": "success", "data": {"items": items,
                                          "total_hours": round(sum(i["hours"] or 0 for i in items), 2),
                                          "open": any(r.clock_out is None for r in rows)}}


@router.get("/center")
def center_month(year_month: str = Query(...), db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    """센터장: 직원별 월 근무 시간과, 방문 기록은 있는데 출근 기록이 없는 날 수(방문·출근 불일치)."""
    start, end = _month_range(year_month)
    staff = db.query(User).filter(User.center_id == actor.center_id, User.role.in_(STAFF_ROLES)).all()
    logs = db.query(WorkLog).filter(WorkLog.center_id == actor.center_id, WorkLog.work_date >= start, WorkLog.work_date < end).all()
    visits = db.query(DailyRecord).join(User, User.id == DailyRecord.caregiver_id).filter(
        User.center_id == actor.center_id,
        DailyRecord.recorded_date >= datetime.combine(start, datetime.min.time()),
        DailyRecord.recorded_date < datetime.combine(end, datetime.min.time())).all()
    out = []
    for u in staff:
        mine = [l for l in logs if l.staff_id == u.id]
        worked_days = {l.work_date for l in mine}
        visit_days = {v.recorded_date.date() for v in visits if v.caregiver_id == u.id}
        out.append({"staff_id": u.id, "name": u.full_name, "work_days": len(worked_days),
                    "total_hours": round(sum(_hours(l) or 0 for l in mine), 2),
                    "open_clock_in": sum(1 for l in mine if l.clock_out is None),
                    "visit_days_without_clock_in": len(visit_days - worked_days)})
    return {"status": "success", "data": {"year_month": year_month, "staff": out}}
