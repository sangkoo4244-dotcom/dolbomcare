from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_manager
from app.billing_rules import REVENUE_STATUSES
from app.database import get_db
from app.models import BillingRecord, Center, CopayInvoice, Resident, User

router = APIRouter()


def _resident_month_total(db: Session, resident_id: int, year_month: str) -> int:
    """이 이용자의 해당 월 본인부담금 총액 = 승인된 청구 건들의 (급여비용 총액 - 청구액) 합."""
    rows = db.query(BillingRecord).filter(
        BillingRecord.resident_id == resident_id,
        BillingRecord.year_month == year_month,
        BillingRecord.approval_status.in_(REVENUE_STATUSES),
        BillingRecord.is_archived == False,  # noqa: E712
    ).all()
    return sum((r.total_cost or 0) - (r.amount or 0) for r in rows)


def _derive_status(total_amount: int, paid_amount: int) -> str:
    if paid_amount > 0 and paid_amount >= total_amount > 0:
        return "paid"
    if paid_amount > 0:
        return "partial"
    return "unpaid"


def _get_or_sync_invoice(db: Session, resident: Resident, year_month: str) -> CopayInvoice:
    invoice = db.query(CopayInvoice).filter(
        CopayInvoice.resident_id == resident.id,
        CopayInvoice.year_month == year_month,
    ).first()
    fresh_total = _resident_month_total(db, resident.id, year_month)
    if not invoice:
        invoice = CopayInvoice(
            resident_id=resident.id,
            center_id=resident.center_id,
            year_month=year_month,
            total_amount=fresh_total,
        )
        db.add(invoice)
    elif invoice.total_amount != fresh_total:
        invoice.total_amount = fresh_total  # 청구가 승인/반려되며 바뀔 수 있어 조회 시마다 최신화
        invoice.status = _derive_status(fresh_total, invoice.paid_amount)  # 총액이 바뀌면 상태도 다시 계산한다
    db.commit()
    db.refresh(invoice)
    return invoice


def _to_dict(invoice: CopayInvoice, resident_name: str) -> dict:
    return {
        "resident_id": invoice.resident_id,
        "resident_name": resident_name,
        "year_month": invoice.year_month,
        "total_amount": invoice.total_amount,
        "paid_amount": invoice.paid_amount,
        "balance": max(invoice.total_amount - invoice.paid_amount, 0),
        "status": invoice.status,
        "payment_method": invoice.payment_method,
        "paid_date": invoice.paid_date.isoformat() if invoice.paid_date else None,
        "memo": invoice.memo,
    }


@router.get("/summary")
def get_copay_summary(
    year_month: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_manager),
):
    """해당 월, 센터 전체 이용자의 본인부담금 청구/수납 현황."""
    residents = db.query(Resident).filter(Resident.center_id == actor.center_id).all()
    results = []
    for resident in residents:
        invoice = _get_or_sync_invoice(db, resident, year_month)
        if invoice.total_amount <= 0 and invoice.paid_amount <= 0:
            continue  # 해당 월에 청구 자체가 없는 이용자는 목록에서 뺀다
        results.append(_to_dict(invoice, resident.name))
    results.sort(key=lambda x: x["resident_name"])
    return {
        "year_month": year_month,
        "invoices": results,
        "summary": {
            "total_amount": sum(r["total_amount"] for r in results),
            "paid_amount": sum(r["paid_amount"] for r in results),
            "unpaid_count": sum(1 for r in results if r["status"] != "paid"),
        },
    }


class CopayPaymentRequest(BaseModel):
    year_month: str
    amount: int
    payment_method: str = ""
    memo: str = ""


@router.post("/{resident_id}/pay")
def record_copay_payment(
    resident_id: int,
    body: CopayPaymentRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_manager),
):
    """본인부담금 수납 기록 (분할 납부 가능 - 여러 번 호출하면 누적된다)."""
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="수납액은 0보다 커야 합니다")

    resident = db.query(Resident).filter(Resident.id == resident_id).first()
    if not resident or resident.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")

    invoice = _get_or_sync_invoice(db, resident, body.year_month)
    invoice.paid_amount += body.amount
    invoice.status = _derive_status(invoice.total_amount, invoice.paid_amount)
    invoice.payment_method = body.payment_method or invoice.payment_method
    invoice.memo = body.memo or invoice.memo
    invoice.paid_date = datetime.utcnow()
    invoice.recorded_by = actor.id
    db.commit()
    db.refresh(invoice)
    return {"status": "success", "data": _to_dict(invoice, resident.name)}


@router.get("/resident/{resident_id}/history")
def get_resident_copay_history(
    resident_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """한 이용자의 월별 본인부담금 납부 이력 (최신순). 연말정산용 연간 납부확인서에도 쓸 수 있다."""
    resident = db.query(Resident).filter(Resident.id == resident_id).first()
    if not resident or resident.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")

    invoices = db.query(CopayInvoice).filter(
        CopayInvoice.resident_id == resident_id,
    ).order_by(CopayInvoice.year_month.desc()).all()
    return {"resident_name": resident.name, "invoices": [_to_dict(i, resident.name) for i in invoices]}


@router.get("/resident/{resident_id}/annual-statement")
def get_annual_payment_statement(
    resident_id: int,
    year: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_manager),
):
    """연말정산용 본인부담금 납부확인서 - 세액공제는 "실제로 낸 돈" 기준이라 total_amount(청구액)가 아니라
    paid_amount(실제 수납액)를 월별로 집계한다."""
    resident = db.query(Resident).filter(Resident.id == resident_id).first()
    if not resident or resident.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    center = db.query(Center).filter(Center.id == resident.center_id).first()

    months = [f"{year}-{m:02d}" for m in range(1, 13)]
    invoices_by_month = {
        i.year_month: i
        for i in db.query(CopayInvoice).filter(
            CopayInvoice.resident_id == resident_id,
            CopayInvoice.year_month.in_(months),
        ).all()
    }
    monthly = [
        {"year_month": ym, "paid_amount": invoices_by_month[ym].paid_amount if ym in invoices_by_month else 0}
        for ym in months
    ]

    return {
        "resident_name": resident.name,
        "resident_birth_date": resident.birth_date.isoformat() if resident.birth_date else None,
        "center_name": center.name if center else None,
        "center_address": center.address if center else None,
        "center_phone": center.phone if center else None,
        "year": year,
        "monthly": monthly,
        "total_paid": sum(m["paid_amount"] for m in monthly),
    }
