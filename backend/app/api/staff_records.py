from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_manager
from app.database import get_db
from app.labor_rules import annual_leave_days, retirement_estimate
from app.models import SalaryStatement, StaffRecord, User

router = APIRouter()

# 근로기준법·공단평가가 요구하는 직원 규정준수 기록 종류.
# 연차 발생일수·퇴직금 산정 같은 구체적인 계산식은 반영하지 않고, 날짜·내용·숫자값을
# 센터가 직접 기록하는 대장(ledger) 틀만 제공한다.
RECORD_TYPES = {
    "grievance": "고충처리",
    "health_checkup": "건강검진",
    "continuing_education": "보수교육",
    "annual_leave": "연차·유급휴일",
    "retirement_reserve": "퇴직적립금",
}


def _to_dict(r: StaffRecord, recorder_name: Optional[str] = None) -> dict:
    return {
        "id": r.id,
        "staff_id": r.staff_id,
        "record_type": r.record_type,
        "record_type_label": RECORD_TYPES.get(r.record_type, r.record_type),
        "record_date": r.record_date.isoformat() if r.record_date else None,
        "title": r.title,
        "detail": r.detail,
        "status": r.status,
        "amount": r.amount,
        "recorded_by_name": recorder_name,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/options")
def get_options():
    return {"record_types": RECORD_TYPES}


class StaffRecordCreate(BaseModel):
    staff_id: int
    record_type: str
    record_date: date
    title: str = ""
    detail: str = ""
    status: str = ""
    amount: Optional[int] = None


@router.post("/")
def create_staff_record(
    body: StaffRecordCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_manager),
):
    """직원 규정준수 기록 추가 (센터장 전용)."""
    if body.record_type not in RECORD_TYPES:
        raise HTTPException(status_code=400, detail="기록 종류가 올바르지 않습니다")

    staff = db.query(User).filter(User.id == body.staff_id).first()
    if not staff or staff.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다")

    record = StaffRecord(
        staff_id=body.staff_id,
        record_type=body.record_type,
        record_date=body.record_date,
        title=body.title or None,
        detail=body.detail or None,
        status=body.status or None,
        amount=body.amount,
        recorded_by=actor.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"status": "success", "data": _to_dict(record, actor.full_name)}


@router.get("/staff/{staff_id}")
def list_staff_records(
    staff_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_manager),
):
    """한 직원의 규정준수 기록 전체 (종류별로 묶어서 최신순)."""
    staff = db.query(User).filter(User.id == staff_id).first()
    if not staff or staff.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다")

    rows = (
        db.query(StaffRecord)
        .filter(StaffRecord.staff_id == staff_id)
        .order_by(StaffRecord.record_date.desc(), StaffRecord.id.desc())
        .all()
    )
    recorders = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}

    by_type = {code: [] for code in RECORD_TYPES}
    for r in rows:
        if r.record_type in by_type:
            by_type[r.record_type].append(_to_dict(r, recorders.get(r.recorded_by)))

    return {
        "staff_name": staff.full_name,
        "records": {
            code: {"type_label": label, "items": by_type[code]}
            for code, label in RECORD_TYPES.items()
        },
    }


@router.get("/staff/{staff_id}/annual-leave")
def get_annual_leave_estimate(
    staff_id: int,
    as_of: Optional[date] = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_manager),
):
    """근로기준법 제60조 기준 연차유급휴가 발생일수 (참고용 자동계산)."""
    staff = db.query(User).filter(User.id == staff_id).first()
    if not staff or staff.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다")
    if not staff.hire_date:
        raise HTTPException(status_code=400, detail="입사일이 등록되지 않아 계산할 수 없습니다")

    return annual_leave_days(staff.hire_date, as_of or date.today())


@router.get("/staff/{staff_id}/retirement-estimate")
def get_retirement_estimate(
    staff_id: int,
    as_of: Optional[date] = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_manager),
):
    """근로자퇴직급여보장법 기준 퇴직금 추정액 (참고용 자동계산) - 최근 확정 급여 3개월을 평균임금 산정에 쓴다."""
    staff = db.query(User).filter(User.id == staff_id).first()
    if not staff or staff.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다")
    if not staff.hire_date:
        raise HTTPException(status_code=400, detail="입사일이 등록되지 않아 계산할 수 없습니다")

    recent = (
        db.query(SalaryStatement)
        .filter(SalaryStatement.caregiver_id == staff_id)
        .order_by(SalaryStatement.year_month.desc())
        .limit(3)
        .all()
    )
    recent_monthly_wages = [(s.year_month, s.billing_total) for s in reversed(recent)]
    return retirement_estimate(staff.hire_date, as_of or date.today(), recent_monthly_wages)


@router.delete("/{record_id}")
def delete_staff_record(
    record_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_manager),
):
    record = db.query(StaffRecord).filter(StaffRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다")
    staff = db.query(User).filter(User.id == record.staff_id).first()
    if not staff or staff.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다")
    db.delete(record)
    db.commit()
    return {"status": "success"}
