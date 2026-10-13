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
    wage_ratio = Column(Integer, nullable=True)  # 요양사가 받는 급여 = 청구액(공단부담+본인부담) 중 이 비율(%). NULL=100(기존 동작과 동일)
    is_active = Column(Boolean, default=True)
    alimtalk_opt_in = Column(Boolean, default=True)  # 카카오 알림톡 수신 여부 (끄면 인앱 알림만 받음)
    alimtalk_categories = Column(String, nullable=True)  # 받고 싶은 알림 종류 코드 (쉼표 구분). null=전체
    profile_image = Column(Text, nullable=True)  # 프로필 사진 base64 data URL (resident_media.py와 같은 방식)
    created_at = Column(DateTime, default=datetime.utcnow)

class Center(Base):
    __tablename__ = "centers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    address = Column(String)
    phone = Column(String)
    institution_code = Column(String, nullable=True)  # 장기요양기관코드 (공단 API 조회용, 11자리)
    logo_image = Column(Text, nullable=True)  # 센터 이미지/로고 base64 data URL
    is_public_listed = Column(Boolean, default=False)  # 센터를 못 정한 예비 보호자용 공개 디렉토리(find_center.html) 노출 여부. 센터가 직접 동의해야 함 - 기본은 비공개
    latitude = Column(Float, nullable=True)  # 주소를 카카오 지오코딩한 좌표. 센터 찾기 지도/거리 계산에 사용
    longitude = Column(Float, nullable=True)
    service_types = Column(String, nullable=True)  # 센터가 직접 선택한 제공 서비스 종류, 쉼표로 구분 (예: "방문요양,방문목욕")
    alimtalk_balance = Column(Integer, default=0)  # 알림톡 월 무료 한도를 넘긴 뒤 건당 차감되는 충전 잔액(원)
    trial_ends_at = Column(DateTime, nullable=True)  # 무료 체험 종료 시각. NULL이면 체험 제한 없음(정식 전환 또는 기존 센터)
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
    primary_caregiver_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # 담당 요양보호사 (센터장이 지정, 경쟁사의 "담당 복지사 지정"과 동일 개념)
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

class AlimtalkUsage(Base):
    """센터별 월간 알림톡 발송 현황 - 무료 한도 소진 여부와 충전 잔액 차감 건수를 추적한다."""
    __tablename__ = "alimtalk_usage"
    __table_args__ = (UniqueConstraint("center_id", "year_month", name="uq_alimtalk_usage_center_month"),)

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), index=True)
    year_month = Column(String)  # 'YYYY-MM'
    free_sent = Column(Integer, default=0)  # 무료 한도로 보낸 건수
    paid_sent = Column(Integer, default=0)  # 충전 잔액으로 보낸 건수
    blocked_count = Column(Integer, default=0)  # 한도·잔액 부족으로 못 보낸 건수(참고용 - 인앱 알림은 이와 무관하게 전송됨)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    billing_total = Column(Integer)  # 승인된 청구 합계 (공단부담, 100% 기준 — 급여와는 다른 숫자)
    wage_ratio = Column(Integer, nullable=True)  # 확정 시점에 적용된 급여 비율(%)
    wage_base = Column(Integer, nullable=True)  # billing_total * wage_ratio / 100 — 공제 전 급여 산정 기준액
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
    """낙상위험도·욕창위험도·인지기능평가 - 공단 2026년 평가매뉴얼의 "위험도 평가" 지표(반기 1회).
    낙상은 Morse Fall Scale, 욕창은 Braden Scale(둘 다 공단 매뉴얼이 예시로 든 검증된 도구)을
    체크리스트로 채점하고, 응답 원본은 item_scores에 남겨 평가 시 "모든 기록 확인"에 대비한다."""
    __tablename__ = "risk_assessments"

    id = Column(Integer, primary_key=True, index=True)
    resident_id = Column(Integer, ForeignKey("residents.id"), index=True)
    assessment_type = Column(String, index=True)  # 'fall_risk', 'pressure_sore_risk', 'cognitive_function'
    assessed_by = Column(Integer, ForeignKey("users.id"))
    assessed_date = Column(DateTime, default=datetime.utcnow)
    tool_name = Column(String, nullable=True)  # 'morse_fall_scale', 'braden_scale', 'k_mmse' 등
    score = Column(Integer, nullable=True)
    risk_level = Column(String, nullable=True)  # 'low', 'high'
    item_scores = Column(Text, nullable=True)  # JSON: 체크리스트 문항별 응답 (감사 대비 원본 기록)
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


class PasswordResetToken(Base):
    """비밀번호 찾기(self-service) - 이메일로 보낸 링크의 토큰. SMTP가 설정돼 있어야 실제로
    이메일이 나간다(app/email_service.py). 토큰은 1시간 후 만료, 한 번 쓰면 바로 지운다."""
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    token = Column(String, unique=True, index=True)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


class Counseling(Base):
    """상담 기록 - 공단 2026 방문요양 평가의 '방문상담관리'(수급자·보호자 월 1회)와 '직원 상담관리'(요양보호사 월 1회),
    '직원변경'(담당 요양보호사가 바뀌면 14일 이내 상담)을 증빙하는 대장.
    상담은 대면 또는 유선만 인정되고(문자·SNS 불인정), 내용이 '특이사항 없음' 같은 문구뿐이면 불인정된다."""
    __tablename__ = "counselings"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), index=True)
    kind = Column(String, index=True)  # 'resident'(수급자·보호자 방문상담) / 'staff'(직원 상담)
    resident_id = Column(Integer, ForeignKey("residents.id"), nullable=True, index=True)
    staff_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # 직원 상담 대상 요양보호사
    counselor_id = Column(Integer, ForeignKey("users.id"))  # 상담직원(상담한 관리자)
    counselee_name = Column(String, nullable=True)  # 상담대상자명(관계) - 예: "김영희(딸)"
    counsel_date = Column(Date, index=True)
    method = Column(String, default="visit")  # 'visit'(대면) / 'phone'(유선)
    reason = Column(String, nullable=True)  # 'monthly'(정기) / 'caregiver_change'(담당 요양보호사 변경)
    content = Column(Text)
    action_needed = Column(Boolean, default=False)  # 조치 필요 여부
    action_note = Column(Text, nullable=True)  # 조치 내용·반영 내역
    action_done_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CarePlan(Base):
    """급여제공계획서 - 공단 2026 방문요양 평가 '급여제공계획 수립 및 제공'(16)·'급여제공계획 변경'(17) 증빙.
    필수사항: 급여종류, 수급자명, 작성일자, 작성자명, 장기요양 세부목표·필요내용, 세부제공내용, 횟수, 시간, 종합의견.
    기관이 실시한 욕구사정·낙상·욕창·인지기능 평가를 반영해야 하며(계획 작성 전에 실시한 것만 인정),
    수급자(보호자)에게 설명하고 확인서명을 받아 급여제공 시작일까지 공단에 통보해야 한다.
    공단 통보는 장기요양정보시스템에서 센터가 직접 하므로 여기에는 통보한 날짜만 기록한다."""
    __tablename__ = "care_plans"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), index=True)
    resident_id = Column(Integer, ForeignKey("residents.id"), index=True)
    plan_type = Column(String, default="regular")  # 'regular'(신규·연 1회 정기) / 'change'(기능상태·욕구 변경)
    parent_id = Column(Integer, ForeignKey("care_plans.id"), nullable=True)  # 변경 전 계획서
    change_reason = Column(String, nullable=True)  # 변경 사유 (변경일 때 필수)
    service_type = Column(String, default="방문요양")
    written_date = Column(Date, index=True)
    author_id = Column(Integer, ForeignKey("users.id"))
    service_start_date = Column(Date, nullable=True)  # 이 계획에 따른 급여제공 시작일
    goals = Column(Text)  # 장기요양 세부목표
    needs = Column(Text)  # 장기요양 필요내용
    details = Column(Text)  # 세부제공내용
    frequency = Column(String)  # 횟수 (예: 주 5회)
    duration_minutes = Column(Integer, nullable=True)  # 1회 제공시간
    opinion = Column(Text)  # 종합의견
    needs_assessment_id = Column(Integer, nullable=True)  # 반영한 욕구사정
    fall_assessment_id = Column(Integer, nullable=True)
    pressure_assessment_id = Column(Integer, nullable=True)
    cognitive_assessment_id = Column(Integer, nullable=True)
    guardian_signed_date = Column(Date, nullable=True)  # 수급자(보호자) 설명·확인서명일
    guardian_signer = Column(String, nullable=True)  # 서명자명(관계)
    nhis_notified_date = Column(Date, nullable=True)  # 공단 통보일
    created_at = Column(DateTime, default=datetime.utcnow)


class ServiceEvaluation(Base):
    """급여제공 결과평가 - 공단 2026 방문요양 평가 '급여제공결과평가'(23). 수급자별 급여제공계획에 따른 결과를
    반기별 1회 이상 평가하고(필수: 일자·총평(종합소견)·작성자명), 평가를 반영해 30일 이내에 급여제공계획을 재작성한다.
    수급자 상태 변화가 없으면 총평에 '상태가 동일하다는 판단근거'를 적고 재작성하지 않아도 예외로 인정된다."""
    __tablename__ = "service_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), index=True)
    resident_id = Column(Integer, ForeignKey("residents.id"), index=True)
    evaluated_date = Column(Date, index=True)
    author_id = Column(Integer, ForeignKey("users.id"))
    summary = Column(Text)  # 총평 또는 종합소견
    status_changed = Column(Boolean, default=True)  # 수급자 상태 변화 여부
    no_change_basis = Column(Text, nullable=True)  # 상태 변화가 없을 때 '동일하다고 판단한 근거'
    created_at = Column(DateTime, default=datetime.utcnow)


class CaseConference(Base):
    """사례관리 회의 - 공단 2026 방문요양 평가 '사례관리'(22). 분기별 1회 이상, 총 3인 이상(시설장 포함) 참석,
    참가 직원별 의견 필수, 사례관리 계획을 회의 다음날부터 30일 이내 급여에 반영하고 평가(해결 여부·미해결 시 추가 조치)한다."""
    __tablename__ = "case_conferences"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), index=True)
    resident_id = Column(Integer, ForeignKey("residents.id"), index=True)
    conference_date = Column(Date, index=True)
    author_id = Column(Integer, ForeignKey("users.id"))
    reason = Column(Text)  # 선정사유
    content = Column(Text)  # 회의내용
    attendees = Column(Text)  # JSON: [{"name","role","opinion","signed"}]
    plan = Column(Text)  # 사례관리 계획
    reflected_date = Column(Date, nullable=True)  # 급여 등에 반영한 날
    reflected_note = Column(Text, nullable=True)
    evaluated_date = Column(Date, nullable=True)  # 반영 후 평가일
    evaluator_name = Column(String, nullable=True)
    resolved = Column(Boolean, nullable=True)  # 선정사유 해결 여부
    next_action = Column(Text, nullable=True)  # 미해결 시 추가 조치 계획
    created_at = Column(DateTime, default=datetime.utcnow)


class TrainingSession(Base):
    """직원 교육 기록 - 공단 2026 방문요양 평가 '직원교육'(4)·'노인인권보호'(13)·'직원인권보호'(5)·'질향상노력'(7).
    필수사항: 교육일자·교육방법·강사명·교육내용·참석자명(서명)."""
    __tablename__ = "training_sessions"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), index=True)
    topic = Column(String, index=True)  # operating_rules / care_guidelines / elder_rights / staff_rights_response / cognitive_program
    session_date = Column(Date, index=True)
    method = Column(String)  # self(자체교육) / external(외부강사) / online(온라인)
    instructor = Column(String)
    content = Column(Text)
    attendee_ids = Column(Text)  # JSON: 참석한 직원 user id 목록
    signed_ids = Column(Text)  # JSON: 그중 서명한 직원 user id 목록
    recorded_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)


class ResidentNotice(Base):
    """수급자(보호자) 안내 기록 - 공단 2026 평가 '노인인권보호'(8가지 지침 제공·설명)·'직원인권보호'(폭언·폭행·성희롱 예방 및
    상호존중 안내, 연 1회)·'급여제공안내'(급여제공범위·급여외행위·직원 인권보호 안내, 대면 필수)."""
    __tablename__ = "resident_notices"

    id = Column(Integer, primary_key=True, index=True)
    center_id = Column(Integer, ForeignKey("centers.id"), index=True)
    resident_id = Column(Integer, ForeignKey("residents.id"), index=True)
    notice_type = Column(String, index=True)  # rights_guide / staff_respect / service_scope
    notice_date = Column(Date, index=True)
    method = Column(String)  # visit(대면) / mail(우편) / sms(문자) / email(이메일)
    recipient = Column(String)  # 안내받은 사람: 수급자 본인 또는 보호자명(관계)
    items = Column(Text, nullable=True)  # JSON: 제공한 지침 코드 목록 (rights_guide)
    note = Column(Text, nullable=True)
    recorded_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
