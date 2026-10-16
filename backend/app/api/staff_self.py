"""직원 본인 화면: 내 건강검진·보수교육·연차 상태와 고충 접수. 센터장은 전체 현황과 고충 처리를 맡는다."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_manager
from app.database import get_db
from app.education import status_for
from app.models import StaffRecord, User

router = APIRouter()
SELF_TYPES = {"health_checkup": "건강검진", "continuing_education": "보수교육", "annual_leave": "연차·유급휴일"}
PRIVATE_NOTE = "퇴직적립금은 개인 정산 자료라 이 화면에 보여 주지 않습니다"


class GrievanceBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    detail: Optional[str] = Field(None, max_length=2000)


class StatusBody(BaseModel):
    status: str  # open / resolved


def _item(r: StaffRecord) -> dict:
    return {"id": r.id, "record_date": r.record_date.isoformat() if r.record_date else None, "title": r.title,
            "detail": r.detail, "status": r.status, "amount": r.amount}


def _is_caregiver_for_education(u: User) -> bool:
    return (u.job_type or "요양보호사") == "요양보호사" and u.role == "caregiver"


def _education(u: User, db: Session, today: date) -> Optional[dict]:
    if not _is_caregiver_for_education(u):
        return None
    rows = db.query(StaffRecord).filter(StaffRecord.staff_id == u.id, StaffRecord.record_type == "continuing_education").all()
    exempt = any((r.status or "") == "exempt" for r in rows)
    dates = [r.record_date for r in rows if r.record_date and (r.status or "") != "exempt"]
    return status_for(u.birth_date, u.hire_date, dates, exempt, today)


@router.get("/me")
def my_records(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role not in ("caregiver", "social_worker") or not actor.center_id:
        raise HTTPException(status_code=403, detail="직원만 볼 수 있습니다")
    rows = db.query(StaffRecord).filter(StaffRecord.staff_id == actor.id).order_by(StaffRecord.record_date.desc(), StaffRecord.id.desc()).all()
    out = {code: [] for code in SELF_TYPES}
    grievances = []
    for r in rows:
        if r.record_type in out:
            out[r.record_type].append(_item(r))
        elif r.record_type == "grievance":
            grievances.append(_item(r))
    today = date.today()
    return {"status": "success", "data": {
        "education": _education(actor, db, today),
        "records": {code: {"label": label, "items": out[code]} for code, label in SELF_TYPES.items()},
        "grievances": grievances,
        "note": PRIVATE_NOTE,
    }}


@router.post("/grievance")
def submit_grievance(body: GrievanceBody, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role not in ("caregiver", "social_worker") or not actor.center_id:
        raise HTTPException(status_code=403, detail="직원만 고충을 접수할 수 있습니다")
    row = StaffRecord(staff_id=actor.id, record_type="grievance", record_date=date.today(), title=body.title.strip(),
                      detail=(body.detail or "").strip() or None, status="open", recorded_by=actor.id)
    db.add(row)
    db.commit()
    return {"status": "success", "data": _item(row)}


@router.get("/education-status")
def center_education_status(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    """센터장: 보수교육 대상 요양보호사별 상태와 이수 필요 명단."""
    today = date.today()
    staff = db.query(User).filter(User.center_id == actor.center_id, User.role == "caregiver").all()
    rows = []
    for u in staff:
        st = _education(u, db, today)
        if st is None:
            continue
        rows.append({"staff_id": u.id, "name": u.full_name, **st})
    return {"status": "success", "data": {
        "staff": rows,
        "needs_action": [r for r in rows if r["state"] in ("due", "birth_missing")],
    }}


@router.put("/grievance/{record_id}/status")
def update_grievance(record_id: int, body: StatusBody, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    if body.status not in ("open", "resolved"):
        raise HTTPException(status_code=400, detail="상태는 open 또는 resolved 입니다")
    row = db.query(StaffRecord).filter(StaffRecord.id == record_id, StaffRecord.record_type == "grievance").first()
    staff = db.query(User).filter(User.id == row.staff_id, User.center_id == actor.center_id).first() if row else None
    if not row or not staff:
        raise HTTPException(status_code=404, detail="고충을 찾을 수 없습니다")
    row.status = body.status
    db.commit()
    return {"status": "success", "data": _item(row)}


@router.get("/grievances")
def center_grievances(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    """센터장: 우리 센터 직원이 접수한 고충 전체 (접수 순서 최신순)."""
    rows = db.query(StaffRecord).filter(StaffRecord.record_type == "grievance").order_by(StaffRecord.id.desc()).all()
    names = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}
    return {"status": "success", "data": [
        {**_item(r), "staff_name": names[r.staff_id]} for r in rows if r.staff_id in names
    ]}
