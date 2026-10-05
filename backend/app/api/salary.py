from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from app.models import BillingRecord, User
from app.database import get_db
from app.billing_rules import REVENUE_STATUSES
from datetime import datetime, date, timedelta
from decimal import Decimal

router = APIRouter()

@router.get("/current")
async def get_current_salary(
    caregiver_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """
    현재 월의 급여 조회
    """
    today = datetime.now().date()
    year_month = f"{today.year}-{str(today.month).zfill(2)}"

    # 이번 달의 청부 기록 조회
    billings = db.query(BillingRecord).filter(
        BillingRecord.caregiver_id == caregiver_id,
        BillingRecord.approval_status.in_(REVENUE_STATUSES),
        extract('year', BillingRecord.recorded_date) == today.year,
        extract('month', BillingRecord.recorded_date) == today.month
    ).all()

    total_amount = sum(b.amount for b in billings) if billings else 0
    total_records = len(billings)

    return {
        "year_month": year_month,
        "total_amount": total_amount,
        "total_records": total_records,
        "estimated_payment_date": get_estimated_payment_date(today),
        "status": "pending"  # pending, paid 등
    }

@router.get("/history")
async def get_salary_history(
    caregiver_id: int = Query(...),
    months: int = Query(12),  # 조회할 개월 수 (기본 12개월)
    db: Session = Depends(get_db)
):
    """
    최근 급여 내역 조회 (최대 12개월)
    """
    today = datetime.now().date()
    start_date = today - timedelta(days=30 * months)

    # 월별 청부 기록 그룹화
    billings = db.query(
        extract('year', BillingRecord.recorded_date).label('year'),
        extract('month', BillingRecord.recorded_date).label('month'),
        func.count(BillingRecord.id).label('record_count'),
        func.sum(BillingRecord.amount).label('total_amount')
    ).filter(
        BillingRecord.caregiver_id == caregiver_id,
        BillingRecord.approval_status.in_(REVENUE_STATUSES),
        BillingRecord.recorded_date >= start_date
    ).group_by(
        extract('year', BillingRecord.recorded_date),
        extract('month', BillingRecord.recorded_date)
    ).order_by(
        extract('year', BillingRecord.recorded_date).desc(),
        extract('month', BillingRecord.recorded_date).desc()
    ).all()

    history = []
    for billing in billings:
        year_month = f"{int(billing.year)}-{str(int(billing.month)).zfill(2)}"
        history.append({
            "year_month": year_month,
            "record_count": billing.record_count or 0,
            "total_amount": billing.total_amount or 0,
            "status": "paid" if (year_month < today.strftime("%Y-%m")) else "pending"
        })

    return {
        "total_months": len(history),
        "salary_history": history
    }

@router.get("/monthly/{year_month}")
async def get_monthly_salary(
    year_month: str,  # YYYY-MM 형식
    caregiver_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """
    특정 월의 상세 급여 정보
    """
    try:
        year, month = map(int, year_month.split('-'))
    except:
        raise HTTPException(status_code=400, detail="Invalid year_month format (use YYYY-MM)")

    # 특정 월의 청부 기록 조회
    billings = db.query(BillingRecord).filter(
        BillingRecord.caregiver_id == caregiver_id,
        BillingRecord.approval_status.in_(REVENUE_STATUSES),
        extract('year', BillingRecord.recorded_date) == year,
        extract('month', BillingRecord.recorded_date) == month
    ).all()

    total_amount = sum(b.amount for b in billings) if billings else 0

    # 서비스 타입별 집계
    service_breakdown = {}
    for billing in billings:
        service_type = billing.service_type or "기본돌봄"
        if service_type not in service_breakdown:
            service_breakdown[service_type] = {"count": 0, "amount": 0}
        service_breakdown[service_type]["count"] += 1
        service_breakdown[service_type]["amount"] += billing.amount

    return {
        "year_month": year_month,
        "total_amount": total_amount,
        "total_records": len(billings),
        "service_breakdown": [
            {
                "service_type": service_type,
                "count": data["count"],
                "amount": data["amount"]
            }
            for service_type, data in service_breakdown.items()
        ],
        "payment_date": get_estimated_payment_date(date(year, month, 1)),
        "status": "paid" if (year_month < datetime.now().date().strftime("%Y-%m")) else "pending",
        "records": [
            {
                "id": b.id,
                "resident_id": b.resident_id,
                "service_type": b.service_type,
                "amount": b.amount,
                "recorded_date": b.recorded_date.isoformat() if b.recorded_date else None
            }
            for b in billings
        ]
    }

def get_estimated_payment_date(target_date: date) -> str:
    """
    급여 지급 예상일 계산
    한국 요양관리 기준: 매월 말일 또는 다음달 5일경
    """
    year, month = target_date.year, target_date.month

    # 다음달 5일을 지급일로 설정
    if month == 12:
        payment_date = date(year + 1, 1, 5)
    else:
        payment_date = date(year, month + 1, 5)

    return payment_date.isoformat()

@router.get("/contract")
async def get_contract(
    caregiver_id: int = Query(...),
    db: Session = Depends(get_db)
):
    """
    근로계약서 정보 조회
    실제 파일 다운로드는 별도 구현
    """
    user = db.query(User).filter(User.id == caregiver_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "caregiver_id": caregiver_id,
        "name": user.full_name,
        "email": user.email,
        "contract_status": "active",
        "contract_start_date": "2026-01-01",  # 실제로는 DB에서 가져와야 함
        "contract_type": "기간제 근로계약",
        "work_location": "서울시 강남구",
        "work_type": "방문요양 (재가급여)",
        "notes": "근로계약서는 센터에서 별도 발급"
    }
