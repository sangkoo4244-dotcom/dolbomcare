"""
향상된 청부 관리 모델
- 월별 정산 시스템
- 청부 상태 워크플로우 개선
- 청부 수정 이력 추적
- 청부 통계 지원
"""

from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, Text, ForeignKey, Date, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class BillingRecordEnhanced(Base):
    """
    향상된 청부 기록
    - 상태 관리: draft → pending → approved → submitted_to_nhis → reimbursed
    - 수정 이력 추적
    - 월별 정산 연결
    """
    __tablename__ = "billing_records_enhanced"

    id = Column(Integer, primary_key=True, index=True)

    # 기본 정보
    daily_record_id = Column(Integer, ForeignKey("daily_records.id"), nullable=True)
    caregiver_id = Column(Integer, ForeignKey("users.id"))
    resident_id = Column(Integer, ForeignKey("residents.id"))
    center_id = Column(Integer, ForeignKey("centers.id"))

    # 서비스 정보
    service_category = Column(String, default="재가급여")  # '재가급여', '시설급여'
    service_type = Column(String)  # 'basic_care', 'meal_service', 'medical_care'

    # 청부 금액
    base_amount = Column(Integer)  # 기준액
    patient_pay_amount = Column(Integer, default=0)  # 본인부담액
    insurance_amount = Column(Integer)  # 보험료액 (실제 청부액)

    # 상태 관리 (완전한 워크플로우)
    status = Column(String, default="draft")  # 'draft', 'pending', 'approved', 'submitted_to_nhis', 'reimbursed'
    approval_status = Column(String, default="pending")  # 'pending', 'approved', 'rejected'

    # 승인 관련
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # 승인자
    approved_at = Column(DateTime, nullable=True)
    approval_notes = Column(Text, nullable=True)  # 승인 메모

    # 거절 관련
    rejection_reason = Column(String, nullable=True)
    rejected_at = Column(DateTime, nullable=True)

    # 청구 관련
    submitted_to_nhis_at = Column(DateTime, nullable=True)  # 건보 청구 시간
    nhis_submission_id = Column(String, nullable=True)  # 건보 청구 ID

    # 환급 관련
    reimbursed_amount = Column(Integer, nullable=True)  # 실제 환급액
    reimbursed_at = Column(DateTime, nullable=True)
    reimbursement_id = Column(String, nullable=True)  # 환급 증명 ID

    # 아카이브
    is_archived = Column(Boolean, default=False, index=True)
    archived_at = Column(DateTime, nullable=True)

    # 시간 정보
    recorded_date = Column(DateTime, index=True)  # 서비스 제공 날짜
    year_month = Column(String, index=True)  # 'YYYY-MM' (정산월)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BillingAuditLog(Base):
    """
    청부 기록 수정 이력
    - 누가, 언제, 무엇을 수정했는지 추적
    """
    __tablename__ = "billing_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    billing_record_id = Column(Integer, ForeignKey("billing_records_enhanced.id"))

    modified_by = Column(Integer, ForeignKey("users.id"))  # 수정자
    modified_at = Column(DateTime, default=datetime.utcnow, index=True)

    # 수정 내용
    field_name = Column(String)  # 수정된 필드 (예: 'insurance_amount', 'status')
    old_value = Column(String)  # 이전 값
    new_value = Column(String)  # 새로운 값

    reason = Column(Text, nullable=True)  # 수정 사유


class MonthlySummary(Base):
    """
    월별 정산 요약
    - 센터/요양사별 월간 청부 합계
    - 정산 현황
    """
    __tablename__ = "monthly_summaries"

    id = Column(Integer, primary_key=True, index=True)

    # 대상
    center_id = Column(Integer, ForeignKey("centers.id"), index=True)
    caregiver_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # NULL이면 센터 전체

    # 정산월
    year_month = Column(String, index=True)  # 'YYYY-MM'

    # 통계
    total_records = Column(Integer, default=0)  # 총 청부 건수
    total_base_amount = Column(Integer, default=0)  # 총 기준액
    total_patient_pay = Column(Integer, default=0)  # 총 본인부담액
    total_insurance_amount = Column(Integer, default=0)  # 총 보험료액

    # 상태별 합계
    draft_count = Column(Integer, default=0)
    pending_count = Column(Integer, default=0)
    approved_count = Column(Integer, default=0)
    submitted_count = Column(Integer, default=0)
    reimbursed_count = Column(Integer, default=0)

    # 정산 현황
    submitted_to_nhis_at = Column(DateTime, nullable=True)  # 건보 청구 날짜
    reimbursement_confirmed_at = Column(DateTime, nullable=True)  # 환급 확인 날짜

    # 시간 정보
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class BillingStatistics(Base):
    """
    청부 통계 (캐시 용도)
    - 센터/요양사별 누적 통계
    - 월별 성과
    """
    __tablename__ = "billing_statistics"

    id = Column(Integer, primary_key=True, index=True)

    # 대상
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=True, index=True)
    caregiver_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # 기간
    year = Column(Integer, index=True)
    month = Column(Integer, nullable=True)  # NULL이면 연간 통계

    # 통계
    total_services = Column(Integer, default=0)  # 제공한 서비스 건수
    total_base_amount = Column(Integer, default=0)  # 청구액
    total_reimbursed = Column(Integer, default=0)  # 환급액
    average_per_service = Column(Integer, default=0)  # 서비스당 평균 청부액

    # 시간 정보
    calculated_at = Column(DateTime, default=datetime.utcnow)


class BillingInvoice(Base):
    """
    청부 송장 (서류 생성용)
    - 월별 정산 청구서
    """
    __tablename__ = "billing_invoices"

    id = Column(Integer, primary_key=True, index=True)

    # 발급 대상
    center_id = Column(Integer, ForeignKey("centers.id"))
    monthly_summary_id = Column(Integer, ForeignKey("monthly_summaries.id"))

    # 송장 정보
    invoice_number = Column(String, unique=True, index=True)  # 청구서 번호
    issue_date = Column(DateTime, default=datetime.utcnow)

    # 내용
    total_amount = Column(Integer)  # 청구액
    description = Column(Text, nullable=True)  # 상세 내용

    # 상태
    status = Column(String, default="draft")  # 'draft', 'issued', 'sent', 'received', 'approved'
    sent_at = Column(DateTime, nullable=True)
    approved_at = Column(DateTime, nullable=True)

    # 파일
    document_path = Column(String, nullable=True)  # PDF 파일 경로

    # 시간 정보
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
