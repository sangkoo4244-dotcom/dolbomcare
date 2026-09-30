from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from app.models import BillingRecord, User, Resident, Center
from app.schemas import BillingRecordCreate, BillingRecordResponse, BillingMonthlySummary
from app.database import get_db
from datetime import datetime, timedelta, time

router = APIRouter()

# 등급별 월 인정급여액
CARE_GRADE_LIMITS = {
    1: 1577500,  # 1등급 (최중증)
    2: 1399500,  # 2등급 (중증)
    3: 1193000,  # 3등급 (중중증)
    4: 1082500,  # 4등급 (중등증)
    5: 235000,   # 5등급 (경증)
}

# 서비스 카테고리별 본인부담율 (건강보험공단 기준)
PATIENT_PAY_RATE = {
    "재가급여": {  # 방문요양 등
        "일반": 0.15,              # 본인 15%, 공단 85%
        "차상위계층": 0.10,        # 본인 10%, 공단 90% (감경: 8~12% 범위)
        "기초생활보장": 0.00,      # 본인 0%, 공단 100%
        "의료급여": 0.00,         # 본인 0%, 공단 100%
    },
    "시설급여": {  # 요양원 등
        "일반": 0.20,              # 본인 20%, 공단 80%
        "차상위계층": 0.10,        # 본인 10%, 공단 90% (감경: 8~12% 범위)
        "기초생활보장": 0.00,      # 본인 0%, 공단 100%
        "의료급여": 0.00,         # 본인 0%, 공단 100%
    }
}

# 기본 청부액 (등급 미지정 시)
BILLING_RATES = {
    "basic_care": 30000,      # 기본 요양 30,000원
    "meal_service": 10000,    # 식사 서비스 10,000원
    "medical_care": 50000,    # 의료 처치 50,000원
    "emergency": 100000,      # 응급 대응 100,000원
}

@router.post("/record", response_model=BillingRecordResponse)
async def create_billing_record(
    record: BillingRecordCreate,
    db: Session = Depends(get_db),
    service_category: str = "재가급여"
):
    """음성 기록 → 청구 기록 자동 생성 (등급별 청부액 적용)"""
    caregiver = db.query(User).filter(User.id == record.caregiver_id).first()
    if not caregiver:
        raise HTTPException(status_code=404, detail="Caregiver not found")

    resident = db.query(Resident).filter(Resident.id == record.resident_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="Resident not found")

    # 청구액 계산: 등급 기반
    care_grade = resident.care_grade if resident.care_grade else 1
    client_type = resident.client_type if resident.client_type else "일반"

    # 월 인정급여액을 기준으로 청부액 계산 (공단 기준: 월 1회 청구)
    monthly_limit = CARE_GRADE_LIMITS.get(care_grade, 1577500)

    # 서비스 카테고리별 본인부담율 적용
    category_rates = PATIENT_PAY_RATE.get(service_category, PATIENT_PAY_RATE["재가급여"])
    patient_rate = category_rates.get(client_type, 0.15)
    insurance_rate = 1 - patient_rate

    # 월 청부액 (월 한도액 기준)
    amount = int(monthly_limit * insurance_rate)

    # 상태: "draft" = 미확인 기록, 월별 청구 시 "submitted"로 변환
    db_record = BillingRecord(
        caregiver_id=record.caregiver_id,
        resident_id=record.resident_id,
        center_id=resident.center_id,
        service_category=service_category,
        service_type=record.service_type,
        amount=amount,
        recorded_date=record.recorded_date,
        status="draft"
    )
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    return db_record

@router.get("/monthly/{year_month}", response_model=BillingMonthlySummary)
async def get_monthly_billing(
    year_month: str,  # 'YYYY-MM' format
    db: Session = Depends(get_db)
):
    """월간 청구 현황 조회 (자동 계산)"""
    records = db.query(BillingRecord).filter(
        BillingRecord.recorded_date >= datetime.strptime(f"{year_month}-01", "%Y-%m-%d"),
        BillingRecord.recorded_date < (
            datetime.strptime(f"{year_month}-01", "%Y-%m-%d") + timedelta(days=32)
        ).replace(day=1)
    ).all()

    total_amount = sum(r.amount for r in records)
    # draft: 미제출, pending/submitted: 제출됨, paid: 완료
    submitted_count = len([r for r in records if r.status in ["draft", "pending", "submitted"]])
    paid_count = len([r for r in records if r.status == "paid"])
    pending_count = len([r for r in records if r.status == "draft"])

    # 청구 시간 절감: 기본 40시간에서 70% 절감 → 12시간
    # 시간당 평균 급여 15,000원 기준
    estimated_savings = len(records) * 1000  # 기록 건당 1,000원 절감

    return BillingMonthlySummary(
        year_month=year_month,
        total_records=len(records),
        total_amount=total_amount,
        submitted_count=submitted_count,
        paid_count=paid_count,
        pending_count=pending_count,
        estimated_savings=estimated_savings
    )

@router.get("/today")
async def get_today_billing(db: Session = Depends(get_db)):
    """오늘의 청구 현황"""
    today = datetime.utcnow().date()
    records = db.query(BillingRecord).filter(
        BillingRecord.recorded_date >= datetime.combine(today, time.min),
        BillingRecord.recorded_date <= datetime.combine(today, time.max)
    ).all()

    total_amount = sum(r.amount for r in records)

    return {
        "date": today.isoformat(),
        "total_records": len(records),
        "total_amount": total_amount,
        "average_per_record": total_amount // len(records) if records else 0,
        "breakdown": {
            service_type: len([r for r in records if r.service_type == service_type])
            for service_type in BILLING_RATES.keys()
        }
    }

@router.put("/{record_id}/submit")
async def submit_billing_record(
    record_id: int,
    db: Session = Depends(get_db)
):
    """청구 기록을 공단에 제출"""
    record = db.query(BillingRecord).filter(BillingRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Billing record not found")

    record.status = "submitted"
    record.submitted_date = datetime.utcnow()
    db.commit()
    db.refresh(record)

    return {
        "status": "success",
        "record_id": record_id,
        "submitted_date": record.submitted_date,
        "message": "청구가 공단에 제출되었습니다"
    }

@router.put("/{record_id}/pay")
async def pay_billing_record(
    record_id: int,
    db: Session = Depends(get_db)
):
    """청구 기록을 지급 완료"""
    record = db.query(BillingRecord).filter(BillingRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Billing record not found")

    record.status = "paid"
    db.commit()
    db.refresh(record)

    return {
        "status": "success",
        "record_id": record_id,
        "message": "청구가 지급 완료되었습니다"
    }

@router.get("/")
async def list_billing_records(
    center_id: int = None,
    status: str = None,
    db: Session = Depends(get_db)
):
    """청구 기록 목록 조회"""
    query = db.query(BillingRecord)

    if center_id:
        query = query.filter(BillingRecord.center_id == center_id)

    if status:
        query = query.filter(BillingRecord.status == status)

    records = query.all()

    return {
        "total_records": len(records),
        "records": [
            {
                "id": r.id,
                "resident_id": r.resident_id,
                "caregiver_id": r.caregiver_id,
                "center_id": r.center_id,
                "service_type": r.service_type,
                "amount": r.amount,
                "status": r.status,
                "recorded_date": r.recorded_date.isoformat() if r.recorded_date else None,
                "submitted_date": r.submitted_date.isoformat() if r.submitted_date else None,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in records
        ]
    }
