import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.notifications import notify
from app.auth import get_current_user, require_manager
from app.database import get_db
from app.models import BillingRecord, SalaryStatement, User
from app.salary_rules import DEFAULT_WAGE_RATIO, SALARY_STATUSES, calc_deductions, calc_wage_base

router = APIRouter()


class ConfirmBody(BaseModel):
    caregiver_id: int
    year_month: str


def _to_dict(s: SalaryStatement) -> dict:
    return {
        "year_month": s.year_month,
        "billing_total": s.billing_total,
        "wage_ratio": s.wage_ratio if s.wage_ratio is not None else DEFAULT_WAGE_RATIO,
        "wage_base": s.wage_base if s.wage_base is not None else s.billing_total,
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

    wage_ratio = caregiver.wage_ratio if caregiver.wage_ratio is not None else DEFAULT_WAGE_RATIO
    wage_base = calc_wage_base(total, wage_ratio)
    deductions = calc_deductions(wage_base)
    statement = SalaryStatement(
        center_id=manager.center_id, caregiver_id=caregiver.id, year_month=body.year_month, billing_total=total,
        wage_ratio=wage_ratio, wage_base=wage_base,
        income_tax=deductions["income_tax"], pension=deductions["pension"], health=deductions["health"],
        employment=deductions["employment"], total_deduction=deductions["total_deduction"], net=deductions["net"],
        confirmed_by=manager.id, confirmed_at=datetime.now(),
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
        wage_ratio = c.wage_ratio if c.wage_ratio is not None else DEFAULT_WAGE_RATIO
        # 중증 가산(고시 제19조의2·제26조의2)은 수급자 부담 없이 공단이 '해당 요양보호사에게 지급'하도록 한 금액이라 급여 비율과 별개로 알려 준다
        severe_bonus = sum(
            b.extra_amount or 0 for b in db.query(BillingRecord).filter(
                BillingRecord.caregiver_id == c.id,
                BillingRecord.year_month == year_month,
                BillingRecord.approval_status.in_(SALARY_STATUSES),
                BillingRecord.benefit_type.in_(("home_care", "home_bath")),
            ).all()
        )
        rows.append({
            "caregiver_id": c.id,
            "caregiver_name": c.full_name,
            "severe_bonus": severe_bonus,
            "billing_total": total,
            "wage_ratio": wage_ratio,
            "wage_base": calc_wage_base(total, wage_ratio),
            "confirmed": c.id in confirmed,
        })
    return {"year_month": year_month, "caregivers": rows}


@router.get("/ledger/{year_month}")
def pay_ledger(year_month: str, db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    """월별 급여 지급 대장: 확정된 명세서를 직원별 한 줄로 모으고, 아직 확정 안 된 직원은 따로 알려 준다.
    금액은 확정 당시 저장된 값을 그대로 쓴다(다시 계산하지 않는다)."""
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", year_month):
        raise HTTPException(status_code=400, detail="연월 형식이 올바르지 않습니다 (YYYY-MM)")
    caregivers = db.query(User).filter(User.center_id == manager.center_id, User.role == "caregiver").order_by(User.full_name).all()
    names = {c.id: c.full_name for c in caregivers}
    confirmed = db.query(SalaryStatement).filter(SalaryStatement.center_id == manager.center_id,
                                                 SalaryStatement.year_month == year_month).all()
    rows = [{
        "caregiver_id": s.caregiver_id,
        "caregiver_name": names.get(s.caregiver_id, ""),
        **_to_dict(s),
    } for s in confirmed]
    rows.sort(key=lambda r: r["caregiver_name"])
    keys = ("billing_total", "wage_base", "income_tax", "pension", "health", "employment", "total_deduction", "net")
    totals = {k: sum(r[k] or 0 for r in rows) for k in keys}
    unconfirmed = [c.full_name for c in caregivers if c.id not in {s.caregiver_id for s in confirmed}]
    return {"status": "success", "data": {"year_month": year_month, "rows": rows, "totals": totals,
                                          "unconfirmed": unconfirmed}}
