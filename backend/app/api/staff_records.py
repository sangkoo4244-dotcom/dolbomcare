from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_manager
from app.database import get_db
from app.labor_rules import annual_leave_days, retirement_estimate
from app.models import LeaveRequest, SalaryStatement, StaffRecord, User

router = APIRouter()

LEAVE_USE_DAYS = {"annual": 1, "half_am": 0.5, "half_pm": 0.5}  # 기타 휴가(other)는 연차를 쓴 것이 아니라 0일

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


def _anniversary(hire: date, year: int) -> date:
    try:
        return hire.replace(year=year)
    except ValueError:  # 2월 29일 입사
        return date(year, 2, 28)


def _leave_period_start(hire: date, as_of: date) -> date:
    """연차 year의 시작일: 입사기념일(첫 1년은 입사일)."""
    start = _anniversary(hire, as_of.year)
    if start > as_of:
        start = _anniversary(hire, as_of.year - 1)
    return max(start, hire)


@router.get("/staff/{staff_id}/annual-leave")
def get_annual_leave_estimate(
    staff_id: int,
    as_of: Optional[date] = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_manager),
):
    """근로기준법 제60조 기준 연차유급휴가 발생일수 (참고용 자동계산) + 같은 연차 year에 승인된 사용 일수."""
    staff = db.query(User).filter(User.id == staff_id).first()
    if not staff or staff.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다")
    if not staff.hire_date:
        raise HTTPException(status_code=400, detail="입사일이 등록되지 않아 계산할 수 없습니다")

    as_of = as_of or date.today()
    period_start = _leave_period_start(staff.hire_date, as_of)
    approved = (
        db.query(LeaveRequest)
        .filter(
            LeaveRequest.staff_id == staff_id,
            LeaveRequest.status == "approved",
            LeaveRequest.leave_date >= period_start,
            LeaveRequest.leave_date <= as_of,
        )
        .all()
    )
    used_days = sum(LEAVE_USE_DAYS.get(r.leave_type, 0) for r in approved)

    result = annual_leave_days(staff.hire_date, as_of)
    result.update({
        "period_start": period_start.isoformat(),
        "used_days": used_days,
        "remaining_days": result["days"] - used_days,
    })
    return result


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
    # billing_total은 공단 청구액(센터 매출)이지 급여가 아니다 - 평균임금은 실제 급여 산정액(wage_base)
    # 기준이어야 한다. 비율 분리 이전에 확정된 과거 명세는 wage_base가 비어 있으므로 그때는
    # billing_total을 그대로 쓴다 (당시엔 둘이 같은 값이었다).
    recent_monthly_wages = [
        (s.year_month, s.wage_base if s.wage_base is not None else s.billing_total) for s in reversed(recent)
    ]
    return retirement_estimate(staff.hire_date, as_of or date.today(), recent_monthly_wages)


class DutyBody(BaseModel):
    duty_summary: str = Field("", max_length=2000)


@router.get("/duties")
def list_duties(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    """업무분장표: 같은 센터 직원의 직급·직무·맡은 업무 (센터장 전용)."""
    staff = (
        db.query(User)
        .filter(User.center_id == actor.center_id, User.role.in_(("center_manager", "caregiver", "social_worker")))
        .order_by(User.full_name)
        .all()
    )
    return {"status": "success", "data": [
        {"staff_id": u.id, "full_name": u.full_name, "role": u.role, "position": u.position,
         "job_type": u.job_type, "duty_summary": u.duty_summary or ""}
        for u in staff
    ]}


@router.put("/duties/{staff_id}")
def update_duty(staff_id: int, body: DutyBody, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    staff = db.query(User).filter(User.id == staff_id, User.center_id == actor.center_id).first()
    if not staff:
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다")
    staff.duty_summary = body.duty_summary.strip() or None
    db.commit()
    return {"status": "success"}


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
