from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.notifications import notify
from app.auth import get_current_user, require_manager
from app.database import get_db
from app.models import LeaveRequest, Resident, Schedule, User

router = APIRouter()

LEAVE_TYPES = {"annual": "연차", "half_am": "오전 반차", "half_pm": "오후 반차", "other": "기타 휴가"}
STAFF_ROLES = ("caregiver", "social_worker")


class LeaveBody(BaseModel):
    leave_date: date
    leave_type: str
    reason: Optional[str] = None


class DecisionBody(BaseModel):
    note: Optional[str] = None


def _to_dict(r: LeaveRequest, names: dict, visit_counts: dict) -> dict:
    return {
        "id": r.id,
        "staff_id": r.staff_id,
        "staff_name": names.get(r.staff_id, ""),
        "leave_date": r.leave_date.isoformat(),
        "leave_type": r.leave_type,
        "leave_type_label": LEAVE_TYPES.get(r.leave_type, r.leave_type),
        "reason": r.reason,
        "status": r.status,
        "decided_by_name": names.get(r.decided_by_id) if r.decided_by_id else None,
        "decision_note": r.decision_note,
        "scheduled_visits": len(visit_counts.get((r.staff_id, r.leave_date), [])),
        "visits": visit_counts.get((r.staff_id, r.leave_date), []),
    }


def _visit_counts(db: Session, center_id: int, rows: list) -> dict:
    """신청일에 잡혀 있는 방문. 승인 전에 센터장이 누구를 어떻게 옮겨야 하는지 보도록 시간과 이용자를 함께 준다."""
    if not rows:
        return {}
    days = {r.leave_date for r in rows}
    staff = {r.staff_id for r in rows}
    residents = {r.id: r.name for r in db.query(Resident).filter(Resident.center_id == center_id).all()}
    visits = {}
    for s in db.query(Schedule).filter(Schedule.center_id == center_id, Schedule.status != "cancelled",
                                       Schedule.caregiver_id.in_(staff)).order_by(Schedule.scheduled_date).all():
        d = s.scheduled_date.date() if s.scheduled_date else None
        if d in days:
            visits.setdefault((s.caregiver_id, d), []).append({
                "time": s.scheduled_date.strftime("%H:%M"),
                "resident_name": residents.get(s.resident_id, ""),
                "duration_minutes": s.duration_minutes,
            })
    return visits


@router.post("/requests")
def create_request(body: LeaveBody, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role not in STAFF_ROLES or not actor.center_id:
        raise HTTPException(status_code=403, detail="직원만 연차를 신청할 수 있습니다")
    if body.leave_type not in LEAVE_TYPES:
        raise HTTPException(status_code=400, detail="휴가 종류가 올바르지 않습니다")
    if body.leave_date < date.today():
        raise HTTPException(status_code=400, detail="지난 날짜는 신청할 수 없습니다")
    dup = db.query(LeaveRequest).filter(LeaveRequest.staff_id == actor.id, LeaveRequest.leave_date == body.leave_date,
                                        LeaveRequest.status.in_(("pending", "approved"))).first()
    if dup:
        raise HTTPException(status_code=409, detail="이미 신청했거나 승인된 날짜입니다")
    row = LeaveRequest(center_id=actor.center_id, staff_id=actor.id, leave_date=body.leave_date,
                       leave_type=body.leave_type, reason=(body.reason or "").strip() or None, status="pending")
    db.add(row)
    for m in db.query(User).filter(User.center_id == actor.center_id, User.role == "center_manager", User.is_active == True).all():  # noqa: E712
        notify(db, m.id, "leave_requested", f"{actor.full_name} 님이 {body.leave_date.strftime('%m/%d')} {LEAVE_TYPES[body.leave_type]}을 신청했습니다.")
    db.commit()
    return {"status": "success", "data": {"id": row.id}}


@router.get("/requests/mine")
def my_requests(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role not in STAFF_ROLES:
        raise HTTPException(status_code=403, detail="직원만 볼 수 있습니다")
    rows = db.query(LeaveRequest).filter(LeaveRequest.staff_id == actor.id).order_by(LeaveRequest.leave_date.desc()).limit(100).all()
    names = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}
    return {"status": "success", "data": [_to_dict(r, names, {}) for r in rows]}


@router.post("/requests/{request_id}/cancel")
def cancel_request(request_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    row = db.query(LeaveRequest).filter(LeaveRequest.id == request_id, LeaveRequest.staff_id == actor.id).first()
    if not row:
        raise HTTPException(status_code=404, detail="신청을 찾을 수 없습니다")
    if row.status != "pending":
        raise HTTPException(status_code=400, detail="승인 대기 중인 신청만 취소할 수 있습니다")
    row.status = "cancelled"
    db.commit()
    return {"status": "success"}


@router.get("/requests")
def center_requests(status: str = Query("pending", pattern="^(pending|approved|rejected|cancelled|all)$"),
                    db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    q = db.query(LeaveRequest).filter(LeaveRequest.center_id == actor.center_id)
    if status != "all":
        q = q.filter(LeaveRequest.status == status)
    rows = q.order_by(LeaveRequest.leave_date.desc(), LeaveRequest.id.desc()).limit(300).all()
    names = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}
    counts = _visit_counts(db, actor.center_id, [r for r in rows if r.status in ("pending", "approved")])
    return {"status": "success", "data": [_to_dict(r, names, counts) for r in rows]}


def _decide(db: Session, request_id: int, actor: User, status: str, note: Optional[str]):
    row = db.query(LeaveRequest).filter(LeaveRequest.id == request_id, LeaveRequest.center_id == actor.center_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="신청을 찾을 수 없습니다")
    if row.status != "pending":
        raise HTTPException(status_code=400, detail="승인 대기 중인 신청만 처리할 수 있습니다")
    row.status = status
    row.decided_by_id = actor.id
    row.decided_at = datetime.now()
    row.decision_note = (note or "").strip() or None
    word = "승인" if status == "approved" else "반려"
    msg = f"{row.leave_date.strftime('%m/%d')} {LEAVE_TYPES.get(row.leave_type, '휴가')} 신청이 {word}되었습니다."
    if status == "rejected" and row.decision_note:
        msg += f" 사유: {row.decision_note}"
    notify(db, row.staff_id, "leave_decided", msg)
    db.commit()
    return {"status": "success"}


@router.post("/requests/{request_id}/approve")
def approve(request_id: int, body: DecisionBody = DecisionBody(), db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    return _decide(db, request_id, actor, "approved", body.note)


@router.post("/requests/{request_id}/reject")
def reject(request_id: int, body: DecisionBody, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    if not (body.note or "").strip():
        raise HTTPException(status_code=400, detail="반려 사유를 적어 주세요")
    return _decide(db, request_id, actor, "rejected", body.note)
