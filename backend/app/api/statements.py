from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.notifications import notify
from app.auth import get_current_user, require_manager
from app.database import get_db
from app.models import BillingRecord, SalaryStatement, User
from app.salary_rules import SALARY_STATUSES, calc_deductions

router = APIRouter()


class ConfirmBody(BaseModel):
    caregiver_id: int
    year_month: str


def _to_dict(s: SalaryStatement) -> dict:
    return {
        "year_month": s.year_month,
        "billing_total": s.billing_total,
        "income_tax": s.income_tax,
        "pension": s.pension,
        "health": s.health,
        "employment": s.employment,
        "total_deduction": s.total_deduction,
        "net": s.net,
        "confirmed_at": s.confirmed_at.isoformat() if s.confirmed_at else None,
    }


@router.post("/confirm")
def confirm_statement(body: ConfirmBody, db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    """센터장이 한 달의 급여를 확정한다. 확정한 시점의 금액을 저장하며, 이후 청구가 바뀌어도 명세는 그대로 둔다."""
    if len(body.year_month) != 7 or body.year_month[4] != "-":
        raise HTTPException(status_code=400, detail="year_month는 YYYY-MM 형식이어야 합니다")
    caregiver = db.query(User).filter(
        User.id == body.caregiver_id, User.center_id == manager.center_id, User.role == "caregiver"
    ).first()
    if not caregiver:
        raise HTTPException(status_code=404, detail="요양사를 찾을 수 없습니다")
    if db.query(SalaryStatement).filter(
        SalaryStatement.caregiver_id == caregiver.id, SalaryStatement.year_month == body.year_month
    ).first():
        raise HTTPException(status_code=400, detail="이미 확정된 달입니다")

    total = sum(
        b.amount or 0 for b in db.query(BillingRecord).filter(
            BillingRecord.caregiver_id == caregiver.id,
            BillingRecord.year_month == body.year_month,
            BillingRecord.approval_status.in_(SALARY_STATUSES),
        ).all()
    )
    if total <= 0:
        raise HTTPException(status_code=400, detail="승인된 청구가 없는 달은 확정할 수 없습니다")

    deductions = calc_deductions(total)
    statement = SalaryStatement(
        center_id=manager.center_id, caregiver_id=caregiver.id, year_month=body.year_month, billing_total=total,
        income_tax=deductions["income_tax"], pension=deductions["pension"], health=deductions["health"],
        employment=deductions["employment"], total_deduction=deductions["total_deduction"], net=deductions["net"],
        confirmed_by=manager.id, confirmed_at=datetime.utcnow(),
    )
    db.add(statement)
    notify(db, caregiver.id, "statement_confirmed", f"{body.year_month} 급여 명세가 확정되었습니다")
    db.commit()
    return {"status": "success", "statement": _to_dict(statement)}


@router.get("/mine")
def my_statements(db: Session = Depends(get_db), caregiver: User = Depends(get_current_user)):
    """요양사는 센터가 확정한 명세만 본다. 확정되지 않은 달은 여기에 나오지 않는다."""
    rows = db.query(SalaryStatement).filter(
        SalaryStatement.caregiver_id == caregiver.id
    ).order_by(SalaryStatement.year_month.desc()).all()
    return {"statements": [_to_dict(s) for s in rows]}


@router.get("/status")
def month_status(year_month: str, db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    """센터장 화면: 달별로 요양사의 승인 청구 합계와 확정 여부를 본다."""
    caregivers = db.query(User).filter(User.center_id == manager.center_id, User.role == "caregiver").all()
    confirmed = {
        s.caregiver_id: s for s in db.query(SalaryStatement).filter(
            SalaryStatement.center_id == manager.center_id, SalaryStatement.year_month == year_month
        ).all()
    }
    rows = []
    for c in caregivers:
        total = sum(
            b.amount or 0 for b in db.query(BillingRecord).filter(
                BillingRecord.caregiver_id == c.id,
                BillingRecord.year_month == year_month,
                BillingRecord.approval_status.in_(SALARY_STATUSES),
            ).all()
        )
        rows.append({
            "caregiver_id": c.id,
            "caregiver_name": c.full_name,
            "billing_total": total,
            "confirmed": c.id in confirmed,
        })
    return {"year_month": year_month, "caregivers": rows}
