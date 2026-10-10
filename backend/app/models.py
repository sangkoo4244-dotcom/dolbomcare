from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, Text, ForeignKey, Date, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    role = Column(String)  # 'center_manager', 'caregiver', 'guardian'
    center_id = Column(Integer, ForeignKey("centers.id"), nullable=True)
    phone = Column(String, nullable=True)
    hire_date = Column(Date, nullable=True)  # 고용 시작일
    position = Column(String, nullable=True)  # 직급: '요양사', '팀장', '관리사' 등
    emergency_contact = Column(String, nullable=True)  # 긴급 연락처
    employment_status = Column(String, default="active")  # 'active', 'inactive', 'leave'
    is_active = Column(Boolean, default=True)
    alimtalk_opt_in = Column(Boolean, default=True)  # 카카오 알림톡 수신 여부 (끄면 인앱 알림만 받음)
    alimtalk_categories = Column(String, nullable=True)  # 받고 싶은 알림 종류 코드 (쉼표 구분). null=전체
    created_at = Column(DateTime, default=datetime.utcnow)

class Center(Base):
    __tablename__ = "centers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    address = Column(String)
    phone = Column(String)
    manager_id = Column(Integer, ForeignKey("users.id"))
    residents_count = Column(Integer)
    caregivers_count = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

class Resident(Base):
    __tablename__ = "residents"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"))
    name = Column(String, index=True)
    birth_date = Column(Date, nullable=True)  # 생년월일 (YYYY-MM-DD)
    age = Column(Integer)
    admission_date = Column(DateTime)
    health_status = Column(String)  # 'stable', 'warning', 'critical'
    guardian_id = Column(Integer, ForeignKey("users.id"))
    care_grade = Column(Integer, nullable=True)  # 1~5등급, null=인지지원등급 (default를 두면 SQLAlchemy가 명시적 None도 1로 바꿔버린다)
    client_type = Column(String, default="일반")  # '일반', '차상위계층', '기초생활보장', '의료급여'
    gender = Column(String, nullable=True)  # '남', '여'
    address = Column(String, nullable=True)
    recognition_number = Column(String, nullable=True)  # 장기요양인정번호
    recognition_start = Column(Date, nullable=True)  # 인정 유효기간 시작
    recognition_end = Column(Date, nullable=True)  # 인정 유효기간 종료
    guardian_name = Column(String, nullable=True)
    guardian_phone = Column(String, nullable=True)
    care_notes = Column(Text, nullable=True)  # 요양사가 편집 가능한 요양 기록
    created_at = Column(DateTime, default=datetime.utcnow)

class DailyRecord(Base):
    __tablename__ = "daily_records"

    id = Column(Integer, primary_key=True, index=True)
    resident_id = Column(Integer, ForeignKey("residents.id"))
    caregiver_id = Column(Integer, ForeignKey("users.id"))
    recorded_date = Column(DateTime, index=True)
    morning_care = Column(Boolean, default=False)
    meal_intake = Column(String)  # 'full', 'partial', 'none'
    medicine_given = Column(Boolean, default=False)
    notes = Column(Text)
    care_items = Column(String, nullable=True)  # 제공 항목 코드 (쉼표 구분)
    duration_minutes = Column(Integer, nullable=True)  # 1회 제공 시간 (30~240분)
    schedule_id = Column(Integer, ForeignKey("schedules.id"), nullable=True)  # 연결된 방문 계획
    condition = Column(String, nullable=True)  # 'good', 'normal', 'poor'
    service_type = Column(String, default="basic_care")  # 'basic_care', 'meal_service', 'medical_care'
    audio_file_url = Column(String, nullable=True)
    signature = Column(Text, nullable=True)  # 방문 확인 서명 (base64 PNG data URL)
    created_at = Column(DateTime, default=datetime.utcnow)

class HealthMetric(Base):
    __tablename__ = "health_metrics"

    id = Column(Integer, primary_key=True, index=True)
    resident_id = Column(Integer, ForeignKey("residents.id"))
    recorded_at = Column(DateTime, index=True)
    blood_pressure_sys = Column(Integer, nullable=True)
    blood_pressure_dia = Column(Integer, nullable=True)
    heart_rate = Column(Integer, nullable=True)
    temperature = Column(Float, nullable=True)
    oxygen_saturation = Column(Float, nullable=True)
    status = Column(String)  # 'normal', 'warning', 'critical'
    created_at = Column(DateTime, default=datetime.utcnow)

class Salary(Base):
    __tablename__ = "salaries"

    id = Column(Integer, primary_key=True, index=True)
    caregiver_id = Column(Integer, ForeignKey("users.id"))
    center_id = Column(Integer, ForeignKey("centers.id"))
    year_month = Column(String, index=True)  # 'YYYY-MM'
    base_salary = Column(Integer)
    bonus = Column(Integer, default=0)
    deductions = Column(Integer, default=0)
    total = Column(Integer)
    status = Column(String)  # 'pending', 'approved', 'paid'
    created_at = Column(DateTime, default=datetime.utcnow)

class VoiceRecord(Base):
    __tablename__ = "voice_records"

    id = Column(Integer, primary_key=True, index=True)
    caregiver_id = Column(Integer, ForeignKey("users.id"))
    resident_id = Column(Integer, ForeignKey("residents.id"))
    resident_name = Column(String, nullable=True)  # 음성기록 시점의 이용자 이름 (스냅샷)
    care_grade = Column(Integer, nullable=True)  # 음성기록 시점의 요양등급 (스냅샷)
    client_type = Column(String, nullable=True)  # 음성기록 시점의 소득분류 (스냅샷)
    center_id = Column(Integer, ForeignKey("centers.id"))
    recorded_date = Column(DateTime, index=True)
    service_type = Column(String, default="basic_care")  # 'basic_care', 'meal_service', 'medical_care', 'emergency'
    transcription = Column(Text, nullable=True)  # 음성 인식 텍스트
    audio_file_url = Column(String, nullable=True)  # 음성 파일 URL
    billing_record_id = Column(Integer, ForeignKey("billing_records.id"), nullable=True)  # 자동 생성된 청부 기록
    created_at = Column(DateTime, default=datetime.utcnow)

class BillingRecord(Base):
    __tablename__ = "billing_records"

    id = Column(Integer, primary_key=True, index=True)
    daily_record_id = Column(Integer, ForeignKey("daily_records.id"), nullable=True)
    caregiver_id = Column(Integer, ForeignKey("users.id"))
    resident_id = Column(Integer, ForeignKey("residents.id"))
    resident_name = Column(String, nullable=True)  # 청구 시점의 이용자 이름 (스냅샷)
    care_grade = Column(Integer, nullable=True)  # 청구 시점의 요양등급 (스냅샷)
    client_type = Column(String, nullable=True)  # 청구 시점의 소득분류 (스냅샷)
    center_id = Column(Integer, ForeignKey("centers.id"))
    service_category = Column(String, default="재가급여")  # '재가급여' or '시설급여'
    service_type = Column(String)  # 'basic_care', 'meal_service', 'medical_care', 'emergency'
    amount = Column(Integer)  # 청구액 (원)
    total_cost = Column(Integer, nullable=True)  # 급여비용 총액 (본인부담 포함, 월한도 기준)
    review_note = Column(String, nullable=True)  # 확인 플래그가 있는 청구의 센터장 확인 사유
    status = Column(String, default="draft")  # 'draft', 'submitted', 'paid'
    approval_status = Column(String, default="pending")  # 'pending', 'approved', 'rejected'
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # 승인자 ID
    approved_at = Column(DateTime, nullable=True)  # 승인 시간
    rejection_reason = Column(String, nullable=True)  # 거절 사유
    recorded_date = Column(DateTime, index=True)
    submitted_date = Column(DateTime, nullable=True)
    year_month = Column(String, index=True, nullable=True)  # 'YYYY-MM' (정산월)
    is_archived = Column(Boolean, default=False, index=True)  # 아카이브 여부
    archived_at = Column(DateTime, nullable=True)  # 아카이브 시간
    created_at = Column(DateTime, default=datetime.utcnow)

class MonthlySummary(Base):
    """월별 정산 요약"""
    __tablename__ = "monthly_summaries"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), index=True)
    caregiver_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # NULL이면 센터 전체
    year_month = Column(String, index=True)  # 'YYYY-MM'

    total_records = Column(Integer, default=0)  # 총 청부 건수
    total_amount = Column(Integer, default=0)  # 총 청부액
    approved_count = Column(Integer, default=0)  # 승인된 건수
    submitted_count = Column(Integer, default=0)  # 제출된 건수
    paid_count = Column(Integer, default=0)  # 환급된 건수

    submitted_to_nhis_at = Column(DateTime, nullable=True)  # 건보 청구 날짜
    reimbursement_confirmed_at = Column(DateTime, nullable=True)  # 환급 확인 날짜

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)
    caregiver_id = Column(Integer, ForeignKey("users.id"), index=True)  # 요양사
    resident_id = Column(Integer, ForeignKey("residents.id"), index=True)  # 이용자
    center_id = Column(Integer, ForeignKey("centers.id"), index=True)

    scheduled_date = Column(DateTime, index=True)  # 예정 날짜/시간
    duration_minutes = Column(Integer, nullable=True)  # 계획 제공 시간
    planned_items = Column(String, nullable=True)  # 계획된 제공 항목 코드 (쉼표 구분)
    arrived_at = Column(DateTime, nullable=True)  # 실제 도착 시각
    left_at = Column(DateTime, nullable=True)  # 실제 퇴실 시각
    review_note = Column(String, nullable=True)  # 계획 반려 사유
    service_type = Column(String, default="basic_care")  # 'basic_care', 'meal_service', 'medical_care'

    status = Column(String, default="scheduled")  # 'scheduled', 'completed', 'cancelled'
    notes = Column(Text, nullable=True)  # 특이사항

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ResidentChangeRequest(Base):
    __tablename__ = "resident_change_requests"

    id = Column(Integer, primary_key=True, index=True)
    resident_id = Column(Integer, ForeignKey("residents.id"), index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), index=True)
    requested_by = Column(Integer, ForeignKey("users.id"))
    field = Column(String)  # 바꾸려는 항목 이름
    new_value = Column(String, nullable=True)  # 요청한 새 값 (문자열로 저장)
    status = Column(String, default="pending")  # pending, approved, rejected
    reason = Column(String, nullable=True)  # 반려 사유
    decided_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)  # 받는 사람
    kind = Column(String)  # 'change_approved', 'change_rejected', 'plan_rejected'
    message = Column(String)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class GuardianInvite(Base):
    __tablename__ = "guardian_invites"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    resident_id = Column(Integer, ForeignKey("residents.id"), index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), index=True)
    status = Column(String, default="issued")  # issued, submitted, approved, rejected
    guardian_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

class ResidentMessage(Base):
    __tablename__ = "resident_messages"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), index=True)
    resident_id = Column(Integer, ForeignKey("residents.id"), index=True)
    sender_id = Column(Integer, ForeignKey("users.id"))
    sender_role = Column(String)  # 'guardian', 'caregiver', 'center_manager'
    body = Column(Text)
    is_deleted = Column(Boolean, default=False)  # 센터장만 삭제 가능, 행은 감사를 위해 남긴다
    created_at = Column(DateTime, default=datetime.utcnow)

class ResidentThreadRead(Base):
    __tablename__ = "resident_thread_reads"
    __table_args__ = (UniqueConstraint("user_id", "resident_id", name="uq_thread_read"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    resident_id = Column(Integer, ForeignKey("residents.id"), index=True)
    last_read_message_id = Column(Integer, default=0)


class SalaryStatement(Base):
    __tablename__ = "salary_statements"
    __table_args__ = (UniqueConstraint("caregiver_id", "year_month", name="uq_statement_month"),)

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), index=True)
    caregiver_id = Column(Integer, ForeignKey("users.id"), index=True)
    year_month = Column(String)
    billing_total = Column(Integer)
    income_tax = Column(Integer)
    pension = Column(Integer)
    health = Column(Integer)
    employment = Column(Integer)
    total_deduction = Column(Integer)
    net = Column(Integer)
    confirmed_by = Column(Integer, ForeignKey("users.id"))
    confirmed_at = Column(DateTime, default=datetime.utcnow)

class StaffCertificate(Base):
    __tablename__ = "staff_certificates"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    name = Column(String, nullable=False)  # 자격증 이름 (예: 요양보호사)
    grade = Column(String, nullable=True)  # 등급 (예: 1급)
    issued_on = Column(Date, nullable=True)
    expires_on = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class NeedsAssessment(Base):
    """기초평가(욕구조사) - 공단 표준 욕구사정 서식의 핵심 영역. 방문마다가 아니라 주기적으로(보통 월 1회) 작성한다."""
    __tablename__ = "needs_assessments"

    id = Column(Integer, primary_key=True, index=True)
    resident_id = Column(Integer, ForeignKey("residents.id"), index=True)
    assessed_by = Column(Integer, ForeignKey("users.id"))
    assessed_date = Column(DateTime, default=datetime.utcnow)
    diseases = Column(String, nullable=True)  # 보유질환 코드 (쉼표 구분, care_items와 동일한 저장 방식)
    nutrition_status = Column(String, nullable=True)  # 'good', 'poor'
    nutrition_detail = Column(String, nullable=True)  # 쉼표 구분: appetite_loss, weight_loss, weight_gain
    mobility_status = Column(String, nullable=True)  # 'independent', 'independent_with_device', 'assisted', 'assisted_with_device', 'unable'
    function_status = Column(Text, nullable=True)  # JSON 문자열: {"stand_up": "alone", "eating": "guided", ...}
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class CopayInvoice(Base):
    """본인부담금 청구/수납 - 이용자(보호자)가 실제로 낸 돈을 월 단위로 추적한다.
    청구액 자체는 billing_records(total_cost - amount)에서 매월 집계해 total_amount로 저장하고,
    이 테이블은 그 금액을 "수납했는지"만 따로 관리한다."""
    __tablename__ = "copay_invoices"
    __table_args__ = (UniqueConstraint("resident_id", "year_month", name="uq_copay_resident_month"),)

    id = Column(Integer, primary_key=True, index=True)
    resident_id = Column(Integer, ForeignKey("residents.id"), index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), index=True)
    year_month = Column(String, index=True)  # 'YYYY-MM'
    total_amount = Column(Integer, default=0)  # 해당 월 본인부담금 총액 (billing_records 집계값)
    paid_amount = Column(Integer, default=0)  # 실제 수납액 (분할 납부 가능)
    status = Column(String, default="unpaid")  # 'unpaid', 'partial', 'paid'
    payment_method = Column(String, nullable=True)  # '현금', '계좌이체', '카드', 'CMS자동이체' 등
    paid_date = Column(DateTime, nullable=True)
    memo = Column(String, nullable=True)
    recorded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class RiskAssessment(Base):
    """낙상위험도·욕창위험도·인지기능평가 등, 공단이 표준 체크리스트/배점 기준을 정해둔 반기별 평가의 틀.
    구체적인 문항과 배점표는 공식 서식을 확보하기 전까지 반영하지 않았다 - 점수와 위험군만
    센터가 직접 판단해 입력한다 (문항은 나중에 추가 가능)."""
    __tablename__ = "risk_assessments"

    id = Column(Integer, primary_key=True, index=True)
    resident_id = Column(Integer, ForeignKey("residents.id"), index=True)
    assessment_type = Column(String, index=True)  # 'fall_risk', 'pressure_sore_risk', 'cognitive_function'
    assessed_by = Column(Integer, ForeignKey("users.id"))
    assessed_date = Column(DateTime, default=datetime.utcnow)
    score = Column(Integer, nullable=True)
    risk_level = Column(String, nullable=True)  # 'low', 'high'
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class StaffRecord(Base):
    """직원 규정준수 기록 - 고충처리/건강검진/보수교육/연차·유급휴일/퇴직적립금.
    근로기준법·공단평가가 요구하는 각 기록의 정확한 서식·계산식(연차 발생일수, 퇴직금 산정 등)은
    반영하지 않았다 - 날짜·내용·숫자값을 센터가 직접 기록해두는 대장(ledger) 역할만 한다."""
    __tablename__ = "staff_records"

    id = Column(Integer, primary_key=True, index=True)
    staff_id = Column(Integer, ForeignKey("users.id"), index=True)
    record_type = Column(String, index=True)  # 'grievance', 'health_checkup', 'continuing_education', 'annual_leave', 'retirement_reserve'
    record_date = Column(Date)
    title = Column(String, nullable=True)
    detail = Column(Text, nullable=True)
    status = Column(String, nullable=True)  # 고충처리: 'open'/'resolved' 등. 다른 종류는 비워둔다.
    amount = Column(Integer, nullable=True)  # 연차: 일수, 퇴직적립금: 금액 등 종류별로 다르게 쓰는 숫자값
    recorded_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

class ResidentMedia(Base):
    """이용자 사진첩 - 보호자 신뢰 구축용 (어린이집 알림장과 같은 개념).
    별도 파일 스토리지(S3 등) 연동 전이라 base64로 DB에 저장한다 - 서명(signature) 필드와 같은 방식.
    Render 등 컨테이너 배포 환경은 로컬 디스크가 배포마다 초기화되어 파일시스템 저장은 쓸 수 없다."""
    __tablename__ = "resident_media"

    id = Column(Integer, primary_key=True, index=True)
    resident_id = Column(Integer, ForeignKey("residents.id"), index=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    uploaded_by_role = Column(String)  # 업로드 시점의 역할 스냅샷: 'caregiver', 'center_manager', 'guardian'
    image_data = Column(Text)  # base64 data URL (image/jpeg,png 등)
    caption = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
