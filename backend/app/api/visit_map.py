"""방문 지도: 하루 방문을 시간 순서로 번호 매겨 지도에 보여 준다.

센터장은 센터 전체를, 요양보호사는 자기 방문만 본다. 이용자 주소는 처음 한 번만 좌표로 바꿔 저장한다.
주소를 카카오에 보내는 것이므로(외부 서비스) 개인정보 위탁 검토가 끝나야 실제 운영에 쓸 수 있다."""
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.kakao_local import geocode_address
from app.models import Resident, Schedule, SocialVisitPlan, User

router = APIRouter()


def _coordinates(db: Session, resident: Resident):
    """저장된 좌표가 있으면 그대로 쓰고, 없으면 주소를 한 번 변환해 저장한다. 실패하면 None."""
    if resident.latitude is not None and resident.longitude is not None:
        return resident.latitude, resident.longitude
    if not resident.address:
        return None
    found = geocode_address(resident.address)
    if not found:
        return None
    resident.latitude, resident.longitude = found
    db.commit()
    return found


def _social_day(db: Session, actor: User, target: date):
    """사회복지사 가정방문: 날짜만 있는 방문 예정을 등록 순서대로 번호 매긴다 (시각 정보가 없다)."""
    plans = db.query(SocialVisitPlan).filter(SocialVisitPlan.center_id == actor.center_id,
                                              SocialVisitPlan.planned_date == target).order_by(SocialVisitPlan.id).all()
    residents = {r.id: r for r in db.query(Resident).filter(Resident.id.in_({p.resident_id for p in plans})).all()} if plans else {}
    visits = []
    for number, plan in enumerate(plans, start=1):
        resident = residents.get(plan.resident_id)
        point = _coordinates(db, resident) if resident else None
        visits.append({
            "number": number, "schedule_id": None, "time": "", "duration": None,
            "resident": resident.name if resident else "", "address": resident.address if resident else None,
            "caregiver": "사회복지사 방문", "note": plan.note or "", "done": bool(plan.done),
            "latitude": point[0] if point else None, "longitude": point[1] if point else None,
        })
    return {"status": "success", "data": {"date": target.isoformat(), "visits": visits, "kind": "social"}}


@router.get("/day")
def day_map(
    day: Optional[date] = Query(None),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    if actor.role not in ("center_manager", "caregiver", "social_worker") or not actor.center_id:
        return {"status": "success", "data": {"date": None, "visits": [], "message": "이 화면은 센터장, 요양보호사, 사회복지사만 봅니다"}}
    target = day or datetime.now().date()
    if actor.role == "social_worker":
        return _social_day(db, actor, target)
    start = datetime.combine(target, datetime.min.time())
    end = start + timedelta(days=1)
    query = db.query(Schedule).filter(
        Schedule.center_id == actor.center_id, Schedule.status != "cancelled",
        Schedule.scheduled_date >= start, Schedule.scheduled_date < end)
    if actor.role == "caregiver":
        query = query.filter(Schedule.caregiver_id == actor.id)
    schedules = query.order_by(Schedule.scheduled_date).all()

    residents = {r.id: r for r in db.query(Resident).filter(Resident.id.in_({s.resident_id for s in schedules})).all()} if schedules else {}
    staff = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}
    visits = []
    for number, s in enumerate(schedules, start=1):
        resident = residents.get(s.resident_id)
        point = _coordinates(db, resident) if resident else None
        visits.append({
            "number": number,
            "schedule_id": s.id,
            "time": s.scheduled_date.strftime("%H:%M"),
            "duration": s.duration_minutes,
            "resident": resident.name if resident else "",
            "address": resident.address if resident else None,
            "caregiver": staff.get(s.caregiver_id, ""),
            "latitude": point[0] if point else None,
            "longitude": point[1] if point else None,
        })
    return {"status": "success", "data": {"date": target.isoformat(), "visits": visits}}
