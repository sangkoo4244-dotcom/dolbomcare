from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.models import BillingRecord, User, Resident, Center, DailyRecord
from app.review import review_flags
from app.billing_rules import MONTHLY_LIMITS
from app.billing_rules import REVENUE_STATUSES
from app.schemas import BillingRecordCreate, BillingRecordResponse, BillingMonthlySummary
from app.api.notifications import notify
from app.database import get_db
from app.auth import get_current_user, require_manager, assert_self_or_manager
from datetime import datetime, timedelta, time
import asyncio
import random

router = APIRouter()

# Request 모델
class ApprovalRequest(BaseModel):
    user_id: int
    user_role: str
    reason: str = ""

class RejectionRequest(BaseModel):
    user_id: int
    user_role: str
    reason: str = ""

# 등급별 월 인정급여액
CARE_GRADE_LIMITS = MONTHLY_LIMITS  # 2026년 등급별 월 한도 (billing_rules 한 곳에서 관리)

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
    monthly_limit = CARE_GRADE_LIMITS.get(care_grade, CARE_GRADE_LIMITS[1])

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
    # approval_status: pending(승인 대기), approved(승인됨), rejected(거절)
    # status: draft(미제출), submitted(제출됨), paid(완료)
    approved_amount = sum(r.amount for r in records if r.approval_status in REVENUE_STATUSES)
    submitted_count = len([r for r in records if r.status == "submitted"])
    paid_count = len([r for r in records if r.status == "paid"])
    pending_count = len([r for r in records if r.approval_status == "pending"])
    approved_count = len([r for r in records if r.approval_status == "approved"])

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
        estimated_savings=estimated_savings,
        approved_count=approved_count,
        approved_amount=approved_amount
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

@router.post("/{record_id}/approve")
async def approve_billing_record(
    record_id: int,
    request: ApprovalRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """청구 기록을 승인 (센터장만 가능)"""
    if actor.role != "center_manager":
        raise HTTPException(status_code=403, detail="센터장만 승인 가능합니다")

    record = db.query(BillingRecord).filter(BillingRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Billing record not found")
    if record.approval_status != "pending":
        raise HTTPException(status_code=400, detail="대기 중인 청부만 승인 가능합니다")

    record.approval_status = "approved"
    record.approved_by = actor.id
    record.approved_at = datetime.utcnow()
    notify(db, record.caregiver_id, "claim_approved", f"청구가 승인되었습니다 ({record.amount:,}원)")
    db.commit()
    db.refresh(record)

    return {
        "status": "success",
        "record_id": record_id,
        "approval_status": record.approval_status,
        "message": "청구 기록이 승인되었습니다"
    }

@router.post("/{record_id}/reject")
async def reject_billing_record(
    record_id: int,
    request: RejectionRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """청구 기록을 거절 (센터장만 가능)"""
    if actor.role != "center_manager":
        raise HTTPException(status_code=403, detail="센터장만 거절 가능합니다")

    record = db.query(BillingRecord).filter(BillingRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Billing record not found")

    record.approval_status = "rejected"
    record.rejection_reason = request.reason
    reason = (request.reason or "").strip()
    notify(db, record.caregiver_id, "claim_rejected", f"청구가 반려되었습니다: {reason}" if reason else "청구가 반려되었습니다")
    db.commit()
    db.refresh(record)

    return {
        "status": "success",
        "record_id": record_id,
        "approval_status": record.approval_status,
        "message": "청구 기록이 거절되었습니다"
    }

@router.get("/")
async def list_billing_records(
    center_id: int = None,
    caregiver_id: int = None,
    status: str = None,
    include_archived: bool = False,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """청구 기록 목록 조회 (기본: 활성 청부만, include_archived=true면 아카이브도 포함)"""
    if actor.role == "caregiver":
        caregiver_id = actor.id
    query = db.query(BillingRecord)

    if center_id:
        query = query.filter(BillingRecord.center_id == center_id)

    if caregiver_id:
        query = query.filter(BillingRecord.caregiver_id == caregiver_id)

    if status:
        query = query.filter(BillingRecord.approval_status == status)

    # 기본적으로 활성 청부만 표시 (is_archived=False)
    if not include_archived:
        query = query.filter(BillingRecord.is_archived == False)

    records = query.all()

    # caregiver 기준: submitted_to_nhis 제외 (voice_record와 일치)
    caregiver = None
    if caregiver_id:
        caregiver = db.query(User).filter(User.id == caregiver_id).first()

    residents = {x.id: x for x in db.query(Resident).all()}
    caregiver_names = {u.id: u.full_name for u in db.query(User).all()}
    daily_ids = [r.daily_record_id for r in records if r.daily_record_id]
    dailies = {d.id: d for d in db.query(DailyRecord).filter(DailyRecord.id.in_(daily_ids)).all()} if daily_ids else {}

    response_records = []
    for r in records:
        # caregiver는 submitted_to_nhis 기록 제외
        if caregiver and caregiver.role == 'caregiver':
            if r.approval_status == 'submitted_to_nhis':
                continue

        current = residents.get(r.resident_id)
        response_records.append({
            "id": r.id,
            "daily_record_id": r.daily_record_id,
            "review_flags": review_flags(db, r, dailies.get(r.daily_record_id)),
            "review_note": r.review_note,
            "resident_id": r.resident_id,
            "resident_name": current.name if current else r.resident_name,
            "care_grade": r.care_grade or (current.care_grade if current else None),
            "client_type": r.client_type or (current.client_type if current else None),
            "caregiver_id": r.caregiver_id,
            "caregiver_name": caregiver_names.get(r.caregiver_id),
            "center_id": r.center_id,
            "service_type": r.service_type,
            "amount": r.amount,
            "total_amount": r.amount,
            "status": r.status,
            "approval_status": r.approval_status,
            "rejection_reason": r.rejection_reason,
            "is_archived": r.is_archived,
            "recorded_date": r.recorded_date.isoformat() if r.recorded_date else None,
            "submitted_date": r.submitted_date.isoformat() if r.submitted_date else None,
            "archived_at": r.archived_at.isoformat() if r.archived_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None
        })

    return {
        "total_records": len(response_records),
        "records": response_records
    }

# ===== 상태별 처리 API =====

@router.post("/{billing_id}/submit-to-nhis")
async def submit_billing_to_nhis(
    billing_id: int,
    request: ApprovalRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """청부를 건강보험공단에 청구 제출 (센터장만 가능, 수동 처리)"""
    if actor.role != "center_manager":
        raise HTTPException(status_code=403, detail="센터장만 건보 청구 가능합니다")

    billing = db.query(BillingRecord).filter(BillingRecord.id == billing_id).first()
    if not billing:
        raise HTTPException(status_code=404, detail="청부 기록을 찾을 수 없습니다")

    if billing.approval_status != "approved":
        raise HTTPException(status_code=400, detail="승인된 청부만 건보 청구 가능합니다")

    # 건보 청구 처리 (자동 진행 없음 - 센터장이 수동으로 건보 확인 후 [환급 확인] 클릭)
    billing.approval_status = "submitted_to_nhis"
    billing.approved_at = datetime.now()
    db.commit()
    db.refresh(billing)

    return {
        "status": "success",
        "message": "청부가 건강보험공단에 청구되었습니다. 건보 확인 후 [환급 확인]을 클릭하세요.",
        "data": {
            "id": billing.id,
            "approval_status": billing.approval_status,
            "submitted_at": billing.approved_at.isoformat() if billing.approved_at else None
        }
    }

@router.post("/{billing_id}/confirm-reimbursement")
async def confirm_reimbursement(
    billing_id: int,
    request: ApprovalRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """건보 환급 확인 (센터장만 가능, 완료된 청부는 자동 아카이브)"""
    if actor.role != "center_manager":
        raise HTTPException(status_code=403, detail="센터장만 환급 확인 가능합니다")

    billing = db.query(BillingRecord).filter(BillingRecord.id == billing_id).first()
    if not billing:
        raise HTTPException(status_code=404, detail="청부 기록을 찾을 수 없습니다")

    if billing.approval_status != "submitted_to_nhis":
        raise HTTPException(status_code=400, detail="건보 청구된 청부만 환급 확인 가능합니다")

    # 환급 확인 처리
    billing.approval_status = "reimbursed"
    billing.is_archived = True  # 자동 아카이브
    billing.archived_at = datetime.now()
    db.commit()
    db.refresh(billing)

    return {
        "status": "success",
        "message": "환급이 확인되었습니다",
        "data": {
            "id": billing.id,
            "approval_status": billing.approval_status
        }
    }

@router.patch("/{billing_id}/cancel-nhis-submission")
async def cancel_nhis_submission(
    billing_id: int,
    request: ApprovalRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """건보 청구 취소 (센터장만 가능, submitted_to_nhis → approved)"""
    if actor.role != "center_manager":
        raise HTTPException(status_code=403, detail="센터장만 건보 청구 취소 가능합니다")

    billing = db.query(BillingRecord).filter(BillingRecord.id == billing_id).first()
    if not billing:
        raise HTTPException(status_code=404, detail="청부 기록을 찾을 수 없습니다")

    if billing.approval_status != "submitted_to_nhis":
        raise HTTPException(status_code=400, detail="건보 청구된 청부만 취소 가능합니다")

    # 건보 청구 취소 처리
    billing.approval_status = "approved"
    db.commit()
    db.refresh(billing)

    return {
        "status": "success",
        "message": "건보 청구가 취소되었습니다",
        "data": {
            "id": billing.id,
            "approval_status": billing.approval_status
        }
    }

@router.post("/{billing_id}/submit")
async def submit_billing_for_approval(
    billing_id: int,
    request: ApprovalRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """청부를 센터장 승인을 위해 제출 (요양사만 가능)"""
    if actor.role != "caregiver":
        raise HTTPException(status_code=403, detail="요양사만 제출 가능합니다")

    billing = db.query(BillingRecord).filter(BillingRecord.id == billing_id).first()
    if not billing:
        raise HTTPException(status_code=404, detail="청부 기록을 찾을 수 없습니다")

    if billing.caregiver_id != actor.id:
        raise HTTPException(status_code=403, detail="자신의 청부만 제출 가능합니다")

    # draft 또는 rejected 상태의 청부만 제출 가능
    if billing.approval_status not in ["draft", "rejected"]:
        raise HTTPException(status_code=400, detail="임시 저장 또는 거절된 청부만 다시 제출 가능합니다")

    # 제출 처리
    billing.approval_status = "pending"
    billing.status = "submitted"
    db.commit()
    db.refresh(billing)

    return {
        "status": "success",
        "message": "청부가 센터장 승인을 위해 제출되었습니다",
        "data": {
            "id": billing.id,
            "approval_status": billing.approval_status,
            "status": billing.status
        }
    }

class BillingStatusUpdate(BaseModel):
    approval_status: str
    user_id: int
    user_role: str

@router.patch("/{billing_id}")
async def update_billing_status(
    billing_id: int,
    status_update: BillingStatusUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """청부 상태 되돌리기 (센터장만: approved → pending, pending → draft)"""
    if actor.role != "center_manager":
        raise HTTPException(status_code=403, detail="센터장만 상태를 변경할 수 있습니다")

    billing = db.query(BillingRecord).filter(BillingRecord.id == billing_id).first()
    if not billing:
        raise HTTPException(status_code=404, detail="청부 기록을 찾을 수 없습니다")

    allowed = {("approved", "pending"), ("pending", "draft")}
    if (billing.approval_status, status_update.approval_status) not in allowed:
        raise HTTPException(
            status_code=400,
            detail="승인됨 상태는 대기로, 대기 상태는 작성 중으로만 되돌릴 수 있습니다"
        )

    billing.approval_status = status_update.approval_status
    db.commit()
    db.refresh(billing)

    return {
        "status": "success",
        "message": "청부 상태가 변경되었습니다",
        "data": {
            "id": billing.id,
            "approval_status": billing.approval_status,
            "status": billing.status
        }
    }

@router.delete("/{billing_id}")
async def delete_billing(
    billing_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """청부 삭제 (요양사: draft 상태만, 센터장: 자신 것만)"""
    billing = db.query(BillingRecord).filter(BillingRecord.id == billing_id).first()
    if not billing:
        raise HTTPException(status_code=404, detail="청부 기록을 찾을 수 없습니다")

    # 권한 확인
    is_owner = billing.caregiver_id == actor.id
    is_manager = actor.role == "center_manager"

    if actor.role == "caregiver":
        # 요양사: draft 또는 rejected 상태의 자신 것만 삭제 가능
        if not is_owner:
            raise HTTPException(status_code=403, detail="자신의 청부만 삭제 가능합니다")
        if billing.status != "draft" and billing.approval_status != "rejected":
            raise HTTPException(status_code=400, detail="임시 저장되었거나 거절된 청부만 삭제 가능합니다")
    elif is_manager:
        # 센터장: pending/approved/rejected 상태 삭제 가능
        if billing.approval_status not in ["pending", "approved", "rejected"]:
            raise HTTPException(status_code=400, detail="대기 중, 승인됨, 또는 반려된 청부만 삭제 가능합니다")
    else:
        raise HTTPException(status_code=403, detail="삭제 권한이 없습니다")

    db.delete(billing)
    db.commit()

    return {
        "status": "success",
        "message": "청부가 삭제되었습니다",
        "data": {"id": billing_id}
    }
