import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.notifications import notify
from app.auth import get_current_user, require_manager
from app.database import get_db
from app.models import BillingRecord, DailyRecord, SalaryStatement, User
from app.salary_rules import DEFAULT_WAGE_RATIO, SALARY_STATUSES, calc_deductions, calc_hourly_base, calc_wage_base

router = APIRouter()


class ConfirmBody(BaseModel):
    caregiver_id: int
    year_month: str


def _to_dict(s: SalaryStatement) -> dict:
    hourly = s.pay_method == "hourly"
    return {
        "year_month": s.year_month,
        "pay_method": s.pay_method or "ratio",
        "work_minutes": s.work_minutes,
        "billing_total": s.billing_total,
        "wage_ratio": None if hourly else (s.wage_ratio if s.wage_ratio is not None else DEFAULT_WAGE_RATIO),
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
    caregiver = _own_caregiver(db, body.caregiver_id, manager)
    if db.query(SalaryStatement).filter(
        SalaryStatement.caregiver_id == caregiver.id, SalaryStatement.year_month == body.year_month
    ).first():
        raise HTTPException(status_code=400, detail="이미 확정된 달입니다")

    total = _approved_total(db, caregiver.id, body.year_month)
    if total <= 0:
        raise HTTPException(status_code=400, detail="승인된 청구가 없는 달은 확정할 수 없습니다")

    statement = SalaryStatement(center_id=manager.center_id, caregiver_id=caregiver.id, year_month=body.year_month)
    _fill_statement(db, statement, caregiver, manager, total)
    db.add(statement)
    notify(db, caregiver.id, "statement_confirmed", f"{body.year_month} 급여 명세가 확정되었습니다")
    db.commit()
    return {"status": "success", "statement": _to_dict(statement)}


@router.post("/reconfirm")
def reconfirm_statement(body: ConfirmBody, db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    """확정 후 승인 청구가 바뀐 달의 명세 금액을 현재 승인 청구 기준으로 다시 저장한다. 바뀐 것이 없으면 하지 않는다."""
    caregiver = _own_caregiver(db, body.caregiver_id, manager)
    statement = db.query(SalaryStatement).filter(
        SalaryStatement.caregiver_id == caregiver.id, SalaryStatement.year_month == body.year_month
    ).first()
    if not statement:
        raise HTTPException(status_code=400, detail="아직 확정하지 않은 달입니다. 먼저 확정해 주세요")
    total = _approved_total(db, caregiver.id, body.year_month)
    if total <= 0:
        raise HTTPException(status_code=400, detail="승인된 청구가 없어 다시 확정할 수 없습니다")
    if not _is_stale(db, caregiver, statement, total):
        raise HTTPException(status_code=400, detail="확정 후 바뀐 승인 청구가 없습니다")

    _fill_statement(db, statement, caregiver, manager, total)
    notify(db, caregiver.id, "statement_confirmed", f"{body.year_month} 급여 명세가 청구 변경을 반영해 다시 확정되었습니다")
    db.commit()
    return {"status": "success", "statement": _to_dict(statement)}


def _own_caregiver(db: Session, caregiver_id: int, manager: User) -> User:
    caregiver = db.query(User).filter(
        User.id == caregiver_id, User.center_id == manager.center_id, User.role == "caregiver"
    ).first()
    if not caregiver:
        raise HTTPException(status_code=404, detail="요양사를 찾을 수 없습니다")
    return caregiver


def _approved_total(db: Session, caregiver_id: int, year_month: str) -> int:
    return sum(
        b.amount or 0 for b in db.query(BillingRecord).filter(
            BillingRecord.caregiver_id == caregiver_id,
            BillingRecord.year_month == year_month,
            BillingRecord.approval_status.in_(SALARY_STATUSES),
        ).all()
    )


def _work_minutes(db: Session, caregiver_id: int, year_month: str) -> int:
    """시급 계산용 제공 시간 합계(분). 제공 기록의 1회 제공 시간을 월별로 더한다."""
    start = datetime.strptime(f"{year_month}-01", "%Y-%m-%d")
    end = datetime(start.year + (start.month == 12), start.month % 12 + 1, 1)
    rows = db.query(DailyRecord.duration_minutes).filter(
        DailyRecord.caregiver_id == caregiver_id,
        DailyRecord.recorded_date >= start,
        DailyRecord.recorded_date < end,
    ).all()
    return sum(r[0] or 0 for r in rows)


def _pay_basis(db: Session, caregiver: User, year_month: str, billing_total: int) -> dict:
    """요양사의 급여 산정액. 시급 방식은 제공 시간 × 시급, 기본 방식은 청구액 × 급여 비율이다."""
    if caregiver.pay_method == "hourly" and caregiver.hourly_wage:
        minutes = _work_minutes(db, caregiver.id, year_month)
        return {"pay_method": "hourly", "wage_ratio": None, "work_minutes": minutes,
                "wage_base": calc_hourly_base(minutes, caregiver.hourly_wage)}
    wage_ratio = caregiver.wage_ratio if caregiver.wage_ratio is not None else DEFAULT_WAGE_RATIO
    return {"pay_method": "ratio", "wage_ratio": wage_ratio, "work_minutes": None,
            "wage_base": calc_wage_base(billing_total, wage_ratio)}


def _is_stale(db: Session, caregiver: User, snapshot: SalaryStatement, live_total: int) -> bool:
    """확정 뒤 승인 청구가 바뀌었거나, 시급 방식이라 제공 시간이 바뀌었으면 재확정이 필요하다."""
    if live_total != snapshot.billing_total:
        return True
    if snapshot.pay_method == "hourly":
        return _pay_basis(db, caregiver, snapshot.year_month, live_total)["wage_base"] != snapshot.wage_base
    return False


def _fill_statement(db: Session, statement: SalaryStatement, caregiver: User, manager: User, total: int) -> None:
    basis = _pay_basis(db, caregiver, statement.year_month, total)
    wage_ratio, wage_base = basis["wage_ratio"], basis["wage_base"]
    deductions = calc_deductions(wage_base)
    statement.billing_total = total
    statement.wage_ratio = wage_ratio
    statement.wage_base = wage_base
    statement.pay_method = basis["pay_method"]
    statement.work_minutes = basis["work_minutes"]
    statement.income_tax = deductions["income_tax"]
    statement.pension = deductions["pension"]
    statement.health = deductions["health"]
    statement.employment = deductions["employment"]
    statement.total_deduction = deductions["total_deduction"]
    statement.net = deductions["net"]
    statement.confirmed_by = manager.id
    statement.confirmed_at = datetime.now()


@router.get("/mine")
def my_statements(db: Session = Depends(get_db), caregiver: User = Depends(get_current_user)):
    """요양사는 센터가 확정한 명세만 본다. 확정되지 않은 달은 여기에 나오지 않는다."""
    rows = db.query(SalaryStatement).filter(
        SalaryStatement.caregiver_id == caregiver.id
    ).order_by(SalaryStatement.year_month.desc()).all()
    return {"statements": [_to_dict(s) for s in rows]}


@router.get("/status")
def month_status(year_month: str, db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    """센터장 화면: 달별로 요양사의 승인 청구 합계와 확정 여부를 본다.
    확정한 요양사는 확정 당시 저장된 금액을 보여 주고, 그 뒤 승인 청구가 바뀌었으면 stale로 알려 준다(재확정 필요)."""
    caregivers = db.query(User).filter(User.center_id == manager.center_id, User.role == "caregiver").all()
    confirmed = {
        s.caregiver_id: s for s in db.query(SalaryStatement).filter(
            SalaryStatement.center_id == manager.center_id, SalaryStatement.year_month == year_month
        ).all()
    }
    rows = []
    for c in caregivers:
        live_total = _approved_total(db, c.id, year_month)
        # 중증 가산(고시 제19조의2·제26조의2)은 수급자 부담 없이 공단이 '해당 요양보호사에게 지급'하도록 한 금액이라 급여 비율과 별개로 알려 준다
        severe_bonus = sum(
            b.extra_amount or 0 for b in db.query(BillingRecord).filter(
                BillingRecord.caregiver_id == c.id,
                BillingRecord.year_month == year_month,
                BillingRecord.approval_status.in_(SALARY_STATUSES),
                BillingRecord.benefit_type.in_(("home_care", "home_bath")),
            ).all()
        )
        snapshot = confirmed.get(c.id)
        basis = _pay_basis(db, c, year_month, live_total)
        if snapshot:
            rows.append({
                "caregiver_id": c.id,
                "caregiver_name": c.full_name,
                "severe_bonus": severe_bonus,
                "billing_total": snapshot.billing_total,
                "live_billing_total": live_total,
                "stale": _is_stale(db, c, snapshot, live_total),
                "pay_method": snapshot.pay_method or "ratio",
                "wage_ratio": None if snapshot.pay_method == "hourly" else (snapshot.wage_ratio if snapshot.wage_ratio is not None else DEFAULT_WAGE_RATIO),
                "wage_base": snapshot.wage_base if snapshot.wage_base is not None else snapshot.billing_total,
                "net": snapshot.net,
                "confirmed": True,
            })
            continue
        rows.append({
            "caregiver_id": c.id,
            "caregiver_name": c.full_name,
            "severe_bonus": severe_bonus,
            "billing_total": live_total,
            "live_billing_total": live_total,
            "stale": False,
            "pay_method": basis["pay_method"],
            "wage_ratio": basis["wage_ratio"],
            "wage_base": basis["wage_base"],
            "net": None,
            "confirmed": False,
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
