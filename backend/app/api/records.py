from fastapi import APIRouter, HTTPException, File, UploadFile, Depends, Query, Body
from pydantic import BaseModel, Field
from typing import Literal, Optional
from app.billing_rules import split_visit, split_benefit, VALID_DURATIONS, REVENUE_STATUSES
from app.visit_benefit import normalize_visit_benefit
from app import benefits as benefit_catalog
from app.review import find_schedule
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from app.models import DailyRecord, BillingRecord, User, Resident, VoiceRecord, MonthlySummary, Notification, DayCareAttendance
from app.schemas import DailyRecordResponse
from app.database import get_db
from app.auth import get_current_user, require_manager, assert_self_or_manager, assert_my_center
from app.api.notifications import notify
from datetime import datetime, time, timedelta
import os

router = APIRouter()

ChangeStatus = Literal["improved", "maintained", "worsened"]  # 호전 / 유지 / 악화

UPLOAD_DIR = "uploads/audio"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def get_year_month(date: datetime) -> str:
    """날짜로부터 YYYY-MM 형식의 정산월 추출"""
    return date.strftime("%Y-%m")

SERVICE_TYPE_LABELS = {"basic_care": "기본 돌봄", "meal_service": "식사 서빙", "medical_care": "의료 관리", "emergency": "응급"}
CONDITION_LABELS = {"good": "좋음", "normal": "보통", "poor": "나쁨"}

def guardian_visit_summary(
    resident_name: str,
    service_type: str,
    duration_minutes: Optional[int] = None,
    condition: Optional[str] = None,
    note: Optional[str] = None,
    benefit_type: Optional[str] = None,
) -> str:
    """요양사가 따로 작성하지 않아도, 기록된 항목만으로 보호자에게 보낼 요약을 만든다."""
    service_label = SERVICE_TYPE_LABELS.get(service_type, service_type)
    if benefit_type in ("home_bath", "home_nursing"):
        service_label = benefit_catalog.BY_CODE[benefit_type]["label"]
    headline = f"{resident_name}님 오늘 {service_label} 서비스를 받으셨습니다"
    if duration_minutes:
        headline += f" (약 {duration_minutes}분)"
    parts = [headline]
    if condition and CONDITION_LABELS.get(condition):
        parts.append(f"컨디션: {CONDITION_LABELS[condition]}")
    if note and note.strip():
        parts.append(f"메모: {note.strip()[:40]}")
    return ". ".join(parts) + "."

# Request 모델
class CreateRecordRequest(BaseModel):
    caregiver_id: int
    resident_id: int
    service_type: str
    notes: str = ""
    care_items: str = ""
    item_minutes: Optional[str] = None  # "meal_assist:30,bath:30" 항목별 분 (선택, 공단 앱 입력용)
    condition: Optional[str] = None
    duration_minutes: int = Field(60, ge=1, le=240)  # 방문요양은 30·60·90·120·180·240분, 방문간호는 15분 이상 (급여 종류별 검사는 normalize_visit_benefit)
    benefit_type: Optional[Literal["home_care", "home_bath", "home_nursing"]] = None  # 비우면 방문요양
    bath_mode: Optional[Literal["vehicle_in", "vehicle_home", "no_vehicle"]] = None  # 방문목욕 방식
    co_caregiver_id: Optional[int] = None  # 방문목욕: 함께 간 요양보호사
    nursing_order_note: Optional[str] = Field(None, max_length=200)  # 방문간호지시서 확인 메모
    special_note: Optional[str] = Field(None, max_length=300)  # 산정 사유: 방문요양 2인 동시 제공(수급자 동의·당시 상태), 방문목욕 1인 몸 씻기 예외·주 1회 초과
    bath_solo_exception: bool = False  # 방문목욕에서 수치심 때문에 몸 씻기만 1인이 제공(차량 미이용만)
    recorded_date: Optional[datetime] = None  # 소급 기록용 (미지정 시 현재 시각)
    signature: Optional[str] = None  # 방문 확인 서명 (base64 PNG data URL)
    physical_change: Optional[ChangeStatus] = None  # 공단 제공기록지 변화상태
    meal_change: Optional[ChangeStatus] = None
    cognitive_change: Optional[ChangeStatus] = None
    stool_accidents: Optional[int] = Field(None, ge=0, le=20)
    urine_accidents: Optional[int] = Field(None, ge=0, le=20)

class UpdateRecordRequest(BaseModel):
    service_type: Optional[str] = None
    notes: Optional[str] = None
    care_grade: Optional[int] = None  # 요양등급 (스냅샷 수정)
    client_type: Optional[str] = None  # 소득분류 (스냅샷 수정)
    duration_minutes: Optional[int] = Field(None, ge=1, le=240)
    bath_mode: Optional[Literal["vehicle_in", "vehicle_home", "no_vehicle"]] = None
    co_caregiver_id: Optional[int] = None
    nursing_order_note: Optional[str] = Field(None, max_length=200)
    special_note: Optional[str] = Field(None, max_length=300)
    care_items: Optional[str] = None
    item_minutes: Optional[str] = None
    condition: Optional[str] = None
    physical_change: Optional[ChangeStatus] = None
    meal_change: Optional[ChangeStatus] = None
    cognitive_change: Optional[ChangeStatus] = None
    stool_accidents: Optional[int] = Field(None, ge=0, le=20)
    urine_accidents: Optional[int] = Field(None, ge=0, le=20)
    user_id: Optional[int] = None

class BatchDeleteRequest(BaseModel):
    record_ids: list
    user_id: int
    user_role: str

def clean_item_minutes(value, care_items):
    """항목별 분 문자열("meal_assist:30,bath:30")을 검사해 돌려준다. 제공 항목에 없는 코드나 0 이하 분은 거절한다."""
    if not value:
        return None
    allowed = {c for c in (care_items or "").split(",") if c}
    pairs = []
    for part in value.split(","):
        code, _, minutes = part.partition(":")
        if code not in allowed or not minutes.isdigit() or not 0 < int(minutes) <= 240:
            raise HTTPException(status_code=400, detail="항목별 시간이 올바르지 않습니다 (선택한 제공 항목만, 1~240분)")
        pairs.append(f"{code}:{int(minutes)}")
    return ",".join(pairs)


EDITABLE_APPROVALS = ("draft", "rejected")  # 요양보호사가 고치거나 지울 수 있는 청구 상태


def _week_bounds(when):
    """방문목욕 '주 1회' 판단용: 그 날이 속한 월~일 한 주."""
    monday = (when - timedelta(days=when.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday, monday + timedelta(days=7)


def _bath_visits_that_week(db, resident_id, when, exclude_id=None):
    start, end = _week_bounds(when)
    q = db.query(DailyRecord).filter(DailyRecord.resident_id == resident_id, DailyRecord.benefit_type == "home_bath",
                                     DailyRecord.recorded_date >= start, DailyRecord.recorded_date < end)
    if exclude_id:
        q = q.filter(DailyRecord.id != exclude_id)
    return q.count()


def _record_in_my_center(db, record, actor) -> bool:
    """센터장이 다른 센터의 방문 기록을 건드리지 못하게, 기록의 이용자가 내 센터 소속인지 확인한다."""
    resident = db.query(Resident).filter(Resident.id == record.resident_id).first()
    return bool(resident and actor.center_id is not None and resident.center_id == actor.center_id)


def _severe_bonus(db, caregiver_id, day, benefit_type, grade, minutes, exclude_billing_id=None) -> int:
    """중증 가산(1·2등급)을 그 요양보호사의 같은 날 같은 급여 가산과 합쳐 1일 한도(6,000원) 안에서 계산한다."""
    raw = benefit_catalog.severe_bonus(benefit_type, grade, minutes)
    if not raw:
        return 0
    start = datetime.combine(day, datetime.min.time())
    q = db.query(BillingRecord).filter(BillingRecord.caregiver_id == caregiver_id, BillingRecord.recorded_date >= start,
                                       BillingRecord.recorded_date < start + timedelta(days=1))
    q = q.filter(BillingRecord.benefit_type == "home_bath") if benefit_type == "home_bath" else q.filter(
        or_(BillingRecord.benefit_type == "home_care", BillingRecord.benefit_type.is_(None)))
    if exclude_billing_id:
        q = q.filter(BillingRecord.id != exclude_billing_id)
    used = sum(b.extra_amount or 0 for b in q.all())
    return max(0, min(raw, benefit_catalog.SEVERE_DAILY_CAP - used))


def _pair_of(db, record):
    """방문요양 2인 동시 제공으로 이어진 상대 기록과 그 청구 (없으면 (None, None))."""
    if not record.pair_record_id:
        return None, None
    other = db.query(DailyRecord).filter(DailyRecord.id == record.pair_record_id).first()
    if not other:
        return None, None
    return other, db.query(BillingRecord).filter(BillingRecord.daily_record_id == other.id).first()


def _pair_is_locked(other_billing):
    return bool(other_billing and other_billing.approval_status not in EDITABLE_APPROVALS)


@router.post("/test")
def test_endpoint():
    """테스트 엔드포인트"""
    return {"message": "POST 작동 확인"}

@router.post("/create")
def create_record(request: CreateRecordRequest, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """일일 기록 생성 및 청구 자동 계산"""
    if actor.role not in ("caregiver", "center_manager"):
        raise HTTPException(status_code=403, detail="방문 기록은 요양보호사나 센터장만 입력할 수 있습니다")
    caregiver_id = actor.id if actor.role == "caregiver" else request.caregiver_id
    try:
        resident = db.query(Resident).filter(Resident.id == request.resident_id).first()
        if not resident or (actor.role == "caregiver" and (actor.center_id is None or resident.center_id != actor.center_id)):
            raise HTTPException(status_code=404, detail="Resident not found")
        if actor.role == "center_manager":
            # 센터장이 대신 입력할 때: 우리 센터의 이용자와 우리 센터 요양보호사만 허용 (센터장 본인이나 다른 센터 사람 이름으로 기록되지 않게)
            target = db.query(User).filter(User.id == caregiver_id).first()
            if resident.center_id != actor.center_id or not target or target.role != "caregiver" or target.center_id != actor.center_id:
                raise HTTPException(status_code=400, detail="우리 센터의 요양보호사와 이용자만 선택할 수 있습니다")

        visit = normalize_visit_benefit(db, center_id=resident.center_id, caregiver_id=caregiver_id, benefit_type=request.benefit_type,
                                        bath_mode=request.bath_mode, co_caregiver_id=request.co_caregiver_id,
                                        duration_minutes=request.duration_minutes, require_duration=True, strict_home_care_duration=True,
                                        special_note=request.special_note, solo_exception=request.bath_solo_exception, for_record=True)
        try:
            now = request.recorded_date or datetime.now()  # 소급 기록 시 선택한 시각, 아니면 현재 시각(로컬)
            total_cost, _, amount = split_benefit(visit["benefit_type"], request.duration_minutes, resident.client_type, visit["bath_mode"], visit["solo_exception"], start=now)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        special_note = (request.special_note or "").strip() or None
        # 같은 날 같은 수급자에게 주·야간보호를 제공했다면 방문목욕은 청구하지 않는다(고시 제32조 ②: 한 종류만 산정)
        if visit["benefit_type"] == "home_bath" and db.query(DayCareAttendance).filter(
                DayCareAttendance.resident_id == request.resident_id, DayCareAttendance.attendance_date == now.date()).first():
            raise HTTPException(status_code=400, detail="같은 날 주·야간보호를 이용해 방문목욕은 청구할 수 없습니다. 주·야간보호와 방문목욕은 같은 날 한 종류만 산정합니다(고시 제32조 ②)")
        # 방문목욕은 주 1회까지 산정한다(고시 제26조 ③). 변실금·요실금 등 불가피한 경우에만 사유를 적고 초과한다.
        if visit["benefit_type"] == "home_bath" and _bath_visits_that_week(db, request.resident_id, now) >= 1 and not special_note:
            raise HTTPException(status_code=400, detail="방문목욕은 같은 주에 1회까지 청구할 수 있습니다. 변실금·요실금 등으로 불가피하면 산정 사유에 적어 주세요")
        linked_schedule = find_schedule(db, caregiver_id, request.resident_id, now)
        daily_record = DailyRecord(
            resident_id=request.resident_id,
            caregiver_id=caregiver_id,
            recorded_date=now,
            morning_care=request.service_type == "basic_care",
            meal_intake="full" if request.service_type == "meal_service" else "partial",
            medicine_given=request.service_type == "medical_care",
            notes=request.notes,
            care_items=request.care_items or None,
            item_minutes=clean_item_minutes(request.item_minutes, request.care_items),
            condition=request.condition,
            duration_minutes=request.duration_minutes,
            schedule_id=linked_schedule.id if linked_schedule else None,
            service_type=request.service_type,
            audio_file_url=None,
            signature=request.signature,
            physical_change=request.physical_change,
            meal_change=request.meal_change,
            cognitive_change=request.cognitive_change,
            stool_accidents=request.stool_accidents,
            urine_accidents=request.urine_accidents,
            benefit_type=visit["benefit_type"],
            bath_mode=visit["bath_mode"],
            co_caregiver_id=visit["co_caregiver_id"],
            nursing_order_note=(request.nursing_order_note or "").strip() or None,
            special_note=special_note,
            bath_solo_exception=visit["solo_exception"],
        )
        db.add(daily_record)
        db.flush()
        daily_id = daily_record.id

        # BillingRecord 생성 (draft 상태로 시작 - 요양사가 제출하기 전)
        billing_record = BillingRecord(
            daily_record_id=daily_id,
            caregiver_id=caregiver_id,
            resident_id=request.resident_id,
            center_id=resident.center_id,
            resident_name=resident.name,
            care_grade=resident.care_grade,
            client_type=resident.client_type,
            service_category="재가급여",
            service_type=request.service_type,
            benefit_type=visit["benefit_type"],
            amount=amount,
            total_cost=total_cost,
            extra_amount=_severe_bonus(db, caregiver_id, now.date(), visit["benefit_type"], resident.care_grade, request.duration_minutes),
            recorded_date=now,
            year_month=get_year_month(now),
            status="draft",
            approval_status="draft"
        )
        db.add(billing_record)
        db.flush()
        pair_record = pair_billing = None
        if visit["benefit_type"] == "home_care" and visit["co_caregiver_id"]:
            # 방문요양 2인 동시 제공(고시 제19조 ⑦): 요양보호사별로 각각 산정하므로 함께 제공한 요양보호사의 기록·청구를 따로 만들어 서로 잇는다
            co_id = visit["co_caregiver_id"]
            co_schedule = find_schedule(db, co_id, request.resident_id, now)
            pair_record = DailyRecord(
                resident_id=request.resident_id, caregiver_id=co_id, recorded_date=now,
                morning_care=daily_record.morning_care, meal_intake=daily_record.meal_intake, medicine_given=daily_record.medicine_given,
                notes=request.notes, care_items=daily_record.care_items, item_minutes=daily_record.item_minutes, condition=request.condition,
                duration_minutes=request.duration_minutes, schedule_id=co_schedule.id if co_schedule else None, service_type=request.service_type,
                signature=request.signature, physical_change=request.physical_change, meal_change=request.meal_change,
                cognitive_change=request.cognitive_change, stool_accidents=request.stool_accidents, urine_accidents=request.urine_accidents,
                benefit_type="home_care", co_caregiver_id=caregiver_id, special_note=special_note, bath_solo_exception=False,
                pair_record_id=daily_record.id,
            )
            db.add(pair_record)
            db.flush()
            daily_record.pair_record_id = pair_record.id
            pair_billing = BillingRecord(
                daily_record_id=pair_record.id, caregiver_id=co_id, resident_id=request.resident_id, center_id=resident.center_id,
                resident_name=resident.name, care_grade=resident.care_grade, client_type=resident.client_type, service_category="재가급여",
                service_type=request.service_type, benefit_type="home_care", amount=amount, total_cost=total_cost, recorded_date=now,
                extra_amount=_severe_bonus(db, co_id, now.date(), "home_care", resident.care_grade, request.duration_minutes),
                year_month=get_year_month(now), status="draft", approval_status="draft",
            )
            db.add(pair_billing)
            notify(db, co_id, "record_pair", f"{resident.name} 어르신 방문요양이 2인 동시 제공으로 기록되었습니다 (함께 제공: {actor.full_name or '동료'}). 나의 청구에서 확인해 주세요.")
        if resident.guardian_id:
            summary = guardian_visit_summary(
                resident.name, request.service_type, request.duration_minutes, request.condition, request.notes,
                benefit_type=visit["benefit_type"],
            )
            notify(db, resident.guardian_id, "visit_completed", summary)
        # 이 이용자의 '방문 기록을 작성해 주세요' 알림은 기록을 썼으니 읽음으로 바꾼다
        db.query(Notification).filter(
            Notification.user_id == caregiver_id, Notification.kind == "record_needed",
            Notification.is_read == False, Notification.message.like(f"{resident.name} %"),  # noqa: E712
        ).update({Notification.is_read: True}, synchronize_session=False)
        db.commit()

        return {
            "status": "success",
            "message": "기록이 저장되고 청구가 자동으로 계산되었습니다",
            "data": {
                "record_id": daily_record.id,
                "billing_id": billing_record.id,
                "billing_amount": amount,
                "service_type": request.service_type,
                "benefit_type": visit["benefit_type"],
                "pair_record_id": pair_record.id if pair_record else None,
                "recorded_at": daily_record.recorded_date.isoformat() if daily_record.recorded_date else None
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        db.rollback()
        print(f"[ERROR] create_record: {type(e).__name__}: {e}\n{traceback.format_exc()}")  # 자세한 내용은 서버 기록에만 남긴다
        raise HTTPException(status_code=500, detail="기록을 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.")

@router.post("/batch-delete")
def batch_delete_records(
    request: BatchDeleteRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """여러 기록 일괄 삭제 (자신의 기록 또는 센터장만)"""
    try:
        is_manager = actor.role == "center_manager"
        deleted = 0

        for record_id in request.record_ids:
            record = db.query(DailyRecord).filter(DailyRecord.id == record_id).first()
            if not record:
                continue

            is_own_record = record.caregiver_id == actor.id
            if not (is_manager or is_own_record):
                continue
            if is_manager and not is_own_record and not _record_in_my_center(db, record, actor):
                continue  # 다른 센터 기록은 지울 수 없다

            pair, pair_billing = _pair_of(db, record)
            if pair and _pair_is_locked(pair_billing):
                continue  # 함께 제공한 요양보호사의 청구가 이미 제출·승인됐으면 이 기록만 지울 수 없다

            billings = db.query(BillingRecord).filter(
                BillingRecord.recorded_date == record.recorded_date,
                BillingRecord.caregiver_id == record.caregiver_id,
                BillingRecord.resident_id == record.resident_id
            ).all()

            for billing in billings:
                db.delete(billing)
            if pair:
                if pair_billing:
                    db.delete(pair_billing)
                db.delete(pair)
            db.delete(record)
            deleted += 1

        db.commit()

        return {"status": "success", "deleted_count": deleted}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload-audio")
async def upload_audio(
    caregiver_id: int,
    resident_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """
    음성 파일 업로드
    실제 Whisper API 연동 시 텍스트 변환
    """
    if actor.role not in ("caregiver", "center_manager"):
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    assert_self_or_manager(actor, caregiver_id, db)
    upload_target = db.query(Resident).filter(Resident.id == resident_id).first()
    if not upload_target or upload_target.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    try:
        # 파일 저장
        filename = f"{caregiver_id}_{resident_id}_{datetime.utcnow().timestamp()}.wav"
        filepath = os.path.join(UPLOAD_DIR, filename)

        with open(filepath, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # 음성 파일로 기록 생성
        resident = db.query(Resident).filter(Resident.id == resident_id).first()
        daily_record = DailyRecord(
            resident_id=resident_id,
            caregiver_id=caregiver_id,
            recorded_date=datetime.now(),  # 로컬 시간 사용
            morning_care=True,
            meal_intake="full",
            medicine_given=False,
            notes="음성 기록으로 자동 생성",
            service_type="basic_care",
            audio_file_url=filepath
        )
        db.add(daily_record)
        db.commit()
        db.refresh(daily_record)

        total_cost, _, amount = split_visit(60, resident.client_type)

        billing_record = BillingRecord(
            daily_record_id=daily_record.id,
            caregiver_id=caregiver_id,
            resident_id=resident_id,
            center_id=resident.center_id,
            service_category="재가급여",
            service_type="basic_care",
            amount=amount,
            total_cost=total_cost,
            recorded_date=datetime.now(),  # 로컬 시간 사용
            approval_status="draft",  # 요양사 제출 전 작성중
            status="draft"  # 아직 미제출 상태
        )
        db.add(billing_record)
        db.commit()

        return {
            "status": "success",
            "message": "음성 파일이 저장되고 자동으로 청구되었습니다",
            "data": {
                "filename": filename,
                "record_id": daily_record.id,
                "billing_amount": 30000
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/recent")
async def get_recent_records(
    caregiver_id: int,
    days: int = 7,
    resident_id: int = None,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """
    지난 N일간의 기록 조회 (기본: 7일)
    resident_id가 주어지면 해당 이용자의 기록만 조회
    """
    assert_self_or_manager(actor, caregiver_id, db)
    try:
        from datetime import date, datetime as dt, time as time_cls, timedelta

        today = date.today()
        start_date = today - timedelta(days=days - 1)
        start_datetime = dt.combine(start_date, time_cls.min)
        end_datetime = dt.combine(today, time_cls.max)

        query = db.query(DailyRecord).filter(
            DailyRecord.caregiver_id == caregiver_id,
            DailyRecord.recorded_date >= start_datetime,
            DailyRecord.recorded_date <= end_datetime
        )

        if resident_id:
            query = query.filter(DailyRecord.resident_id == resident_id)

        records = query.order_by(DailyRecord.recorded_date.desc()).all()

        billings = db.query(BillingRecord).filter(
            BillingRecord.recorded_date >= start_datetime,
            BillingRecord.recorded_date <= end_datetime,
            BillingRecord.caregiver_id == caregiver_id
        ).all()

        billing_map = {}
        for b in billings:
            if b.daily_record_id:
                billing_map[b.daily_record_id] = {
                    "amount": b.amount,
                    "service_type": b.service_type,
                    "benefit_type": getattr(b, "benefit_type", None) or "home_care",
                    "approval_status": b.approval_status
                }

        # 요양사 기준: submitted_to_nhis 제외
        caregiver = db.query(User).filter(User.id == caregiver_id).first()

        response_records = []
        billing_total = 0
        for r in records:
            billing_info = billing_map.get(r.id, {})
            billing_amount = billing_info.get("amount", 0)
            approval_status = billing_info.get("approval_status", "")

            # 요양사도 모든 자신의 기록을 조회할 수 있어야 함 (submitted_to_nhis 포함)
            billing_total += billing_amount
            response_records.append({
                "id": r.id,
                "caregiver_id": r.caregiver_id,
                "resident_id": r.resident_id,
                "service_type": r.service_type or "basic_care",
                "benefit_type": getattr(r, "benefit_type", None) or "home_care",
                "morning_care": r.morning_care,
                "meal_intake": r.meal_intake,
                "medicine_given": r.medicine_given,
                "notes": r.notes,
                "care_items": r.care_items,
                "item_minutes": r.item_minutes,
                "condition": r.condition,
                "recorded_at": r.recorded_date.isoformat() if r.recorded_date else None,
                "billing_amount": billing_amount
            })

        return {
            "days": days,
            "total_records": len(response_records),
            "total_billing_amount": billing_total,
            "records": response_records
        }
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[ERROR] get_recent_records: {type(e).__name__}: {e}\n{error_trace}")
        raise HTTPException(status_code=500, detail=f"기록 조회 중 오류 발생: {str(e)}")

@router.get("/all")
async def get_all_records(
    caregiver_id: int,
    resident_id: int = None,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """
    모든 기록 조회
    resident_id가 주어지면 해당 이용자의 기록만 조회
    """
    assert_self_or_manager(actor, caregiver_id, db)
    try:
        query = db.query(DailyRecord).filter(
            DailyRecord.caregiver_id == caregiver_id
        )

        if resident_id:
            query = query.filter(DailyRecord.resident_id == resident_id)

        records = query.order_by(DailyRecord.recorded_date.desc()).all()

        billings = db.query(BillingRecord).filter(
            BillingRecord.caregiver_id == caregiver_id
            # 아카이브 여부 상관없이 모든 기록 포함
        ).all()

        billing_map = {}
        for b in billings:
            if b.daily_record_id:
                billing_map[b.daily_record_id] = {
                    "amount": b.amount,
                    "total_cost": b.total_cost,
                    "service_type": b.service_type,
                    "benefit_type": getattr(b, "benefit_type", None) or "home_care",
                    "approval_status": b.approval_status
                }

        resident_names = {rid: name for rid, name in db.query(Resident.id, Resident.name).all()}

        caregiver = db.query(User).filter(User.id == caregiver_id).first()

        response_records = []
        billing_total = 0
        for r in records:
            billing_info = billing_map.get(r.id, {})
            billing_amount = billing_info.get("amount", 0)

            billing_total += billing_amount
            response_records.append({
                "id": r.id,
                "caregiver_id": r.caregiver_id,
                "resident_id": r.resident_id,
                "resident_name": resident_names.get(r.resident_id),
                "service_type": r.service_type or "basic_care",
                "benefit_type": getattr(r, "benefit_type", None) or "home_care",
                "morning_care": r.morning_care,
                "meal_intake": r.meal_intake,
                "medicine_given": r.medicine_given,
                "notes": r.notes,
                "care_items": r.care_items,
                "item_minutes": r.item_minutes,
                "condition": r.condition,
                "duration_minutes": r.duration_minutes,
                "recorded_date": r.recorded_date.isoformat() if r.recorded_date else None,
                "recorded_at": r.recorded_date.isoformat() if r.recorded_date else None,
                "amount": billing_amount,
                "billing_amount": billing_amount,
                "total_cost": billing_info.get("total_cost") or billing_amount,
                "approval_status": billing_info.get("approval_status") or "pending"
            })

        return {
            "total_records": len(response_records),  # 제외 후 크기 사용
            "total_billing_amount": billing_total,
            "records": response_records
        }
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[ERROR] get_all_records: {type(e).__name__}: {e}\n{error_trace}")
        raise HTTPException(status_code=500, detail=f"기록 조회 중 오류 발생: {str(e)}")

@router.get("/today")
async def get_today_records(
    caregiver_id: int,
    resident_id: int = None,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """
    오늘의 기록 조회 + 청구액
    resident_id가 주어지면 해당 이용자의 기록만 조회
    """
    assert_self_or_manager(actor, caregiver_id, db)
    try:
        from datetime import date, datetime as dt, time as time_cls

        today = date.today()
        today_start = dt.combine(today, time_cls.min)
        today_end = dt.combine(today, time_cls.max)

        query = db.query(DailyRecord).filter(
            DailyRecord.caregiver_id == caregiver_id,
            DailyRecord.recorded_date >= today_start,
            DailyRecord.recorded_date <= today_end
        )

        if resident_id:
            query = query.filter(DailyRecord.resident_id == resident_id)

        records = query.all()

        # 관련 청구 기록 조회
        billings = db.query(BillingRecord).filter(
            BillingRecord.recorded_date >= today_start,
            BillingRecord.recorded_date <= today_end,
            BillingRecord.caregiver_id == caregiver_id
        ).all()

        # 일일 기록 ID별 청구액/서비스유형 매핑
        billing_map = {}
        for b in billings:
            if b.daily_record_id:
                billing_map[b.daily_record_id] = {
                    "amount": b.amount,
                    "service_type": b.service_type,
                    "benefit_type": getattr(b, "benefit_type", None) or "home_care",
                    "approval_status": b.approval_status
                }

        # 요양사 기준: submitted_to_nhis 제외
        caregiver = db.query(User).filter(User.id == caregiver_id).first()

        response_records = []
        billing_total = 0
        for r in records:
            billing_info = billing_map.get(r.id, {})
            billing_amount = billing_info.get("amount", 0)
            approval_status = billing_info.get("approval_status", "")

            # 요양사도 모든 자신의 기록을 조회할 수 있어야 함 (submitted_to_nhis 포함)
            billing_total += billing_amount
            response_records.append({
                "id": r.id,
                "caregiver_id": r.caregiver_id,
                "resident_id": r.resident_id,
                "service_type": r.service_type or "basic_care",
                "benefit_type": getattr(r, "benefit_type", None) or "home_care",
                "morning_care": r.morning_care,
                "meal_intake": r.meal_intake,
                "medicine_given": r.medicine_given,
                "notes": r.notes,
                "care_items": r.care_items,
                "item_minutes": r.item_minutes,
                "condition": r.condition,
                "recorded_at": r.recorded_date.isoformat() if r.recorded_date else None,
                "billing_amount": billing_amount
            })

        return {
            "date": today.isoformat(),
            "total_records": len(response_records),
            "total_billing_amount": billing_total,
            "records": response_records
        }
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[ERROR] get_today_records: {type(e).__name__}: {e}\n{error_trace}")
        raise HTTPException(status_code=500, detail=f"기록 조회 중 오류 발생: {str(e)}")

@router.get("/all/center")
async def get_all_center_records(
    center_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_manager)
):
    """
    센터 전체의 모든 기록 조회 (센터장용)
    해당 센터 요양관리사의 모든 기록 조회
    """
    assert_my_center(actor, center_id)
    records = db.query(DailyRecord).join(
        Resident, DailyRecord.resident_id == Resident.id
    ).filter(
        Resident.center_id == center_id
    ).order_by(DailyRecord.recorded_date.desc()).all()

    # 해당 센터의 청구 기록 (음성 기록과 매칭된 것만)
    billings = db.query(BillingRecord).filter(
        BillingRecord.center_id == center_id
    ).all()

    # daily_record_id별 청구액/승인상태 매핑
    billing_map = {}
    billing_total = 0
    for b in billings:
        if b.daily_record_id:
            billing_map[b.daily_record_id] = {"amount": b.amount, "approval_status": b.approval_status}
            billing_total += b.amount  # 음성 기록과 매칭된 것만 합산

    resident_names = {rid: name for rid, name in db.query(Resident.id, Resident.name).filter(Resident.center_id == center_id).all()}
    caregiver_names = {uid: name for uid, name in db.query(User.id, User.full_name).all()}

    return {
        "total_records": len(records),
        "total_billing_amount": billing_total,
        "records": [
            {
                "id": r.id,
                "caregiver_id": r.caregiver_id,
                "caregiver_name": caregiver_names.get(r.caregiver_id, "-"),
                "resident_id": r.resident_id,
                "resident_name": resident_names.get(r.resident_id, "-"),
                "service_type": r.service_type or "basic_care",
                "benefit_type": getattr(r, "benefit_type", None) or "home_care",
                "notes": r.notes,
                "care_items": r.care_items,
                "item_minutes": r.item_minutes,
                "condition": r.condition,
                "recorded_at": r.recorded_date.isoformat() if r.recorded_date else None,
                "billing_amount": billing_map.get(r.id, {}).get("amount", 0),
                "approval_status": billing_map.get(r.id, {}).get("approval_status", "draft")
            }
            for r in records
        ]
    }

@router.get("/today/center")
async def get_today_center_records(
    center_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(require_manager)
):
    """
    센터 전체의 오늘 기록 조회 (센터장용)
    해당 센터 요양관리사의 오늘 기록만 조회
    """
    assert_my_center(actor, center_id)
    today = datetime.now().date()  # 로컬 시간 사용
    today_start = datetime.combine(today, time.min)
    today_end = datetime.combine(today, time.max)

    # 해당 센터의 오늘 기록만 조회
    records = db.query(DailyRecord).join(
        Resident, DailyRecord.resident_id == Resident.id
    ).filter(
        Resident.center_id == center_id,
        DailyRecord.recorded_date >= today_start,
        DailyRecord.recorded_date <= today_end
    ).all()

    # 해당 센터의 청구 기록 (billing_amount 포함)
    billings = db.query(BillingRecord).filter(
        BillingRecord.center_id == center_id,
        BillingRecord.recorded_date >= today_start,
        BillingRecord.recorded_date <= today_end
    ).all()

    # daily_record_id별 청구액 매핑
    billing_map = {}
    billing_total = 0
    for b in billings:
        if b.daily_record_id:
            billing_map[b.daily_record_id] = b.amount
            billing_total += b.amount  # 음성 기록과 매칭된 것만 합산

    return {
        "date": today.isoformat(),
        "total_records": len(records),
        "total_billing_amount": billing_total,
        "records": [
            {
                "id": r.id,
                "caregiver_id": r.caregiver_id,
                "resident_id": r.resident_id,
                "service_type": r.service_type or "basic_care",
                "benefit_type": getattr(r, "benefit_type", None) or "home_care",
                "notes": r.notes,
                "recorded_at": r.recorded_date.isoformat() if r.recorded_date else None,
                "billing_amount": billing_map.get(r.id, 0)
            }
            for r in records
        ]
    }

@router.get("/prefill")
def prefill_record(
    resident_id: int,
    caregiver_id: Optional[int] = None,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """기록을 쓰기 전에 미리 채워 줄 값: 오늘 승인된 방문 계획의 제공 항목, 지난 방문의 항목·상태 (요양보호사가 확인·수정한다)."""
    if actor.role not in ("caregiver", "center_manager"):
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    resident = db.query(Resident).filter(Resident.id == resident_id, Resident.center_id == actor.center_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    writer_id = actor.id if actor.role == "caregiver" else caregiver_id

    planned = None
    schedule = find_schedule(db, writer_id, resident_id, datetime.now()) if writer_id else None
    if schedule:
        planned = {
            "schedule_id": schedule.id,
            "items": [c for c in (schedule.planned_items or "").split(",") if c],
            "duration_minutes": schedule.duration_minutes,
            "service_type": schedule.service_type,
            "benefit_type": schedule.benefit_type or "home_care",
            "bath_mode": schedule.bath_mode,
            "co_caregiver_id": schedule.co_caregiver_id,
            "time": schedule.scheduled_date.strftime("%H:%M"),
            "arrived_at": schedule.arrived_at.strftime("%Y-%m-%dT%H:%M") if schedule.arrived_at else None,
            "left_at": schedule.left_at.strftime("%Y-%m-%dT%H:%M") if schedule.left_at else None,
        }

    last_q = db.query(DailyRecord).filter(DailyRecord.resident_id == resident_id)
    last = None
    if writer_id:
        last = last_q.filter(DailyRecord.caregiver_id == writer_id).order_by(DailyRecord.recorded_date.desc()).first()
    if last is None:
        last = last_q.order_by(DailyRecord.recorded_date.desc()).first()  # 담당이 바뀐 경우 이전 담당자의 기록을 참고한다
    last_data = None
    if last:
        last_data = {
            "date": last.recorded_date.strftime("%Y-%m-%d") if last.recorded_date else None,
            "items": [c for c in (last.care_items or "").split(",") if c],
            "condition": last.condition,
            "physical_change": last.physical_change,
            "meal_change": last.meal_change,
            "cognitive_change": last.cognitive_change,
            "duration_minutes": last.duration_minutes,
            "service_type": last.service_type,
        }
    return {"planned": planned, "last": last_data}


@router.get("/daily/{record_id}")
async def get_record(
    record_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """
    기록 상세 조회
    - 센터장: 모든 기록 조회 가능
    - 요양사: 자신의 기록만 조회 가능
    """
    record = db.query(DailyRecord).filter(DailyRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")

    is_manager = actor.role == "center_manager"
    if not (is_manager or record.caregiver_id == actor.id):
        raise HTTPException(status_code=403, detail="조회 권한이 없습니다 (자신의 기록만 조회 가능)")
    if is_manager and record.caregiver_id != actor.id and not _record_in_my_center(db, record, actor):
        raise HTTPException(status_code=404, detail="Record not found")

    # 관련 청구 기록 조회
    billings = db.query(BillingRecord).filter(
        BillingRecord.recorded_date == record.recorded_date,
        BillingRecord.caregiver_id == record.caregiver_id
    ).all()

    return {
        "id": record.id,
        "resident_id": record.resident_id,
        "caregiver_id": record.caregiver_id,
        "morning_care": record.morning_care,
        "meal_intake": record.meal_intake,
        "medicine_given": record.medicine_given,
        "notes": record.notes,
        "audio_file_url": record.audio_file_url,
        "recorded_at": record.recorded_date.isoformat() if record.recorded_date else None,
        "billings": [
            {
                "id": b.id,
                "service_type": b.service_type,
                "benefit_type": getattr(b, "benefit_type", None) or "home_care",
                "amount": b.amount,
                "status": b.status
            }
            for b in billings
        ]
    }

@router.patch("/daily/{record_id}")
async def update_record(
    record_id: int,
    request: UpdateRecordRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """
    음성기록 수정 (메모/서비스 유형 변경)
    """
    try:
        record = db.query(DailyRecord).filter(DailyRecord.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다")

        billing = db.query(BillingRecord).filter(
            BillingRecord.daily_record_id == record_id
        ).first()

        if actor.id is not None and record.caregiver_id != actor.id:
            raise HTTPException(status_code=403, detail="본인의 기록만 수정할 수 있습니다")
        if billing and billing.approval_status not in ("draft", "rejected"):
            raise HTTPException(status_code=400, detail="작성중 또는 보완 요청 상태의 청구만 수정할 수 있습니다")

        resident = db.query(Resident).filter(Resident.id == record.resident_id).first()
        pair, pair_billing = _pair_of(db, record)
        if pair and _pair_is_locked(pair_billing):
            raise HTTPException(status_code=400, detail="함께 제공한 요양보호사의 청구가 이미 제출·승인되어 이 기록을 수정할 수 없습니다")
        if (record.benefit_type or "home_care") == "home_care" and request.co_caregiver_id and request.co_caregiver_id != record.co_caregiver_id:
            raise HTTPException(status_code=400, detail="2인 동시 제공은 기록을 새로 입력할 때만 지정할 수 있습니다")
        new_note = request.special_note if request.special_note is not None else record.special_note
        visit = normalize_visit_benefit(
            db, center_id=resident.center_id if resident else None, caregiver_id=record.caregiver_id, benefit_type=record.benefit_type,
            bath_mode=request.bath_mode or record.bath_mode, co_caregiver_id=request.co_caregiver_id or record.co_caregiver_id,
            duration_minutes=request.duration_minutes, strict_home_care_duration=True,
            special_note=new_note, solo_exception=bool(record.bath_solo_exception), for_record=True)

        if request.service_type:
            record.service_type = request.service_type
        if request.notes is not None:
            record.notes = request.notes
        if request.duration_minutes is not None:
            record.duration_minutes = request.duration_minutes
        record.bath_mode = visit["bath_mode"]
        record.co_caregiver_id = visit["co_caregiver_id"]
        if request.nursing_order_note is not None:
            record.nursing_order_note = request.nursing_order_note.strip() or None
        if request.special_note is not None:
            record.special_note = request.special_note.strip() or None
        if request.care_items is not None:
            record.care_items = request.care_items or None
        if request.item_minutes is not None:
            record.item_minutes = clean_item_minutes(request.item_minutes, request.care_items if request.care_items is not None else record.care_items)
        if request.condition is not None:
            record.condition = request.condition or None
        for field in ("physical_change", "meal_change", "cognitive_change", "stool_accidents", "urine_accidents"):
            value = getattr(request, field)
            if value is not None:
                setattr(record, field, value)

        db.commit()
        db.refresh(record)

        if billing:
            if request.service_type:
                billing.service_type = request.service_type
            if request.care_grade is not None:
                billing.care_grade = request.care_grade
            if request.client_type:
                billing.client_type = request.client_type
            try:
                total_cost, _, insurance_amount = split_benefit(visit["benefit_type"], record.duration_minutes or (60 if visit["benefit_type"] == "home_care" else None),
                                                                billing.client_type, visit["bath_mode"], visit["solo_exception"], start=record.recorded_date)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            billing.total_cost = total_cost
            billing.amount = insurance_amount
            billing.extra_amount = _severe_bonus(db, billing.caregiver_id, billing.recorded_date.date(), visit["benefit_type"], billing.care_grade,
                                                 record.duration_minutes, exclude_billing_id=billing.id)
            if billing.approval_status == "rejected":
                billing.approval_status = "draft"
            billing.rejection_reason = None
            db.commit()
            db.refresh(billing)

        if pair:
            # 2인 동시 제공이면 함께 제공한 요양보호사의 기록·청구도 같은 내용으로 맞춘다(요양보호사별로 같은 금액을 각각 청구)
            for field in ("service_type", "notes", "duration_minutes", "care_items", "item_minutes", "condition", "special_note",
                          "physical_change", "meal_change", "cognitive_change", "stool_accidents", "urine_accidents"):
                setattr(pair, field, getattr(record, field))
            if pair_billing:
                pair_billing.service_type = record.service_type
                pair_billing.total_cost = billing.total_cost if billing else pair_billing.total_cost
                pair_billing.amount = billing.amount if billing else pair_billing.amount
                pair_billing.extra_amount = _severe_bonus(db, pair_billing.caregiver_id, pair_billing.recorded_date.date(), "home_care", pair_billing.care_grade,
                                                          record.duration_minutes, exclude_billing_id=pair_billing.id)
                if pair_billing.approval_status == "rejected":
                    pair_billing.approval_status = "draft"
                pair_billing.rejection_reason = None
            db.commit()

        return {
            "status": "success",
            "record_id": record.id,
            "message": "기록이 수정되었습니다",
            "data": {
                "id": record.id,
                "resident_id": record.resident_id,
                "caregiver_id": record.caregiver_id,
                "service_type": record.service_type,
                "notes": record.notes,
                "recorded_date": record.recorded_date.isoformat() if record.recorded_date else None
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[ERROR] update_record: {type(e).__name__}: {e}\n{error_trace}")
        raise HTTPException(status_code=500, detail=f"수정 중 오류 발생: {str(e)}")


# ===== 월별 정산 (구체적 경로는 DELETE보다 먼저) =====

@router.get("/monthly-summary")
def get_monthly_summary(
    center_id: int,
    year_month: Optional[str] = None,
    caregiver_id: Optional[int] = None,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """
    월별 정산 요약 조회
    - center_id: 필수 (센터 ID, 내 센터만)
    - year_month: 선택 (YYYY-MM 형식, 미지정시 현재월)
    - caregiver_id: 선택 (특정 요양사만, 미지정시 전체)
    """
    if actor.role not in ("caregiver", "center_manager"):
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    assert_my_center(actor, center_id)
    if not year_month:
        year_month = datetime.now().strftime("%Y-%m")

    # year_month 형식 검증
    if len(year_month) != 7 or year_month[4] != "-":
        raise HTTPException(status_code=400, detail="year_month는 YYYY-MM 형식이어야 합니다")

    query = db.query(BillingRecord).filter(
        BillingRecord.center_id == center_id,
        BillingRecord.year_month == year_month,
        BillingRecord.approval_status != "rejected"
    )

    if caregiver_id:
        query = query.filter(BillingRecord.caregiver_id == caregiver_id)

    records = query.all()

    # 통계 계산
    total_records = len(records)
    total_amount = sum(r.amount for r in records if r.approval_status in REVENUE_STATUSES)
    approved_count = sum(1 for r in records if r.approval_status == "approved")
    submitted_count = sum(1 for r in records if r.approval_status == "submitted_to_nhis")
    paid_count = sum(1 for r in records if r.approval_status == "reimbursed")
    resident_names = {rid: name for rid, name in db.query(Resident.id, Resident.name).all()}

    return {
        "status": "success",
        "year_month": year_month,
        "center_id": center_id,
        "caregiver_id": caregiver_id,
        "summary": {
            "total_records": total_records,
            "total_amount": total_amount,
            "approved_count": approved_count,
            "submitted_count": submitted_count,
            "paid_count": paid_count,
            "pending_count": total_records - approved_count - submitted_count - paid_count
        },
        "records": [
            {
                "id": r.id,
                "resident_id": r.resident_id,
                "resident_name": resident_names.get(r.resident_id, r.resident_name),
                "care_grade": r.care_grade,  # 정산 시점의 요양등급
                "client_type": r.client_type,  # 정산 시점의 소득분류
                "caregiver_id": r.caregiver_id,
                "service_type": r.service_type,
                "amount": r.amount,
                "approval_status": r.approval_status,
                "recorded_date": r.recorded_date.isoformat() if r.recorded_date else None
            }
            for r in records
        ]
    }


@router.get("/monthly-statistics")
def get_monthly_statistics(
    center_id: int,
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """
    월별 통계 조회
    - center_id: 필수 (내 센터만)
    - year, month: 선택 (미지정시 현재월)
    """
    if actor.role not in ("caregiver", "center_manager"):
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    assert_my_center(actor, center_id)
    if not year:
        year = datetime.now().year
    if not month:
        month = datetime.now().month

    year_month = f"{year:04d}-{month:02d}"

    # 센터 전체 청구 조회 (반려 포함 원본 목록 → 정산 중단 금액·목록에 사용)
    all_records = db.query(BillingRecord).filter(
        BillingRecord.center_id == center_id,
        BillingRecord.year_month == year_month
    ).all()
    records = [r for r in all_records if r.approval_status != "rejected"]

    residents = {x.id: x.name for x in db.query(Resident).all()}
    user_names = {u.id: u.full_name for u in db.query(User).all()}
    status_amounts = {"target": 0, "completed": 0, "pending": 0, "suspended": 0}
    daily_ids = [r.daily_record_id for r in all_records if r.daily_record_id]
    minutes_by_daily = {d.id: d.duration_minutes for d in db.query(DailyRecord).filter(DailyRecord.id.in_(daily_ids)).all()} if daily_ids else {}
    record_rows = []
    for r in all_records:
        amount = r.amount or 0
        status_amounts["target"] += amount
        if r.approval_status in REVENUE_STATUSES:
            status_amounts["completed"] += amount
        elif r.approval_status == "pending":
            status_amounts["pending"] += amount
        elif r.approval_status == "rejected":
            status_amounts["suspended"] += amount
        record_rows.append({
            "id": r.id,
            "resident_name": residents.get(r.resident_id) or r.resident_name,
            "caregiver_name": user_names.get(r.caregiver_id),
            "service_type": r.service_type,
            "amount": amount,
            "duration_minutes": minutes_by_daily.get(r.daily_record_id),
            "extra_amount": r.extra_amount or 0,  # 수급자 부담 없이 공단이 따로 지급하는 가산(중증 가산·주야간 이동서비스·목욕 가산)
            "approval_status": r.approval_status,
            "year_month": r.year_month
        })

    # 요양사별 통계
    caregiver_stats = {}
    for record in records:
        caregiver_id = record.caregiver_id
        if caregiver_id not in caregiver_stats:
            caregiver = db.query(User).filter(User.id == caregiver_id).first()
            caregiver_stats[caregiver_id] = {
                "caregiver_id": caregiver_id,
                "caregiver_name": caregiver.full_name if caregiver else "Unknown",
                "total_records": 0,
                "total_amount": 0,
                "approved_count": 0,
                "pending_count": 0
            }

        caregiver_stats[caregiver_id]["total_records"] += 1
        if record.approval_status in REVENUE_STATUSES:
            caregiver_stats[caregiver_id]["total_amount"] += (record.amount or 0) + (record.extra_amount or 0)
            caregiver_stats[caregiver_id]["approved_count"] += 1
        elif record.approval_status == "pending":
            caregiver_stats[caregiver_id]["pending_count"] += 1

    # 서비스 유형별 통계
    service_stats = {}
    for record in records:
        service_type = record.service_type
        if service_type not in service_stats:
            service_stats[service_type] = {
                "service_type": service_type,
                "total_records": 0,
                "total_amount": 0
            }

        service_stats[service_type]["total_records"] += 1
        if record.approval_status in REVENUE_STATUSES:
            service_stats[service_type]["total_amount"] += (record.amount or 0) + (record.extra_amount or 0)

    return {
        "status": "success",
        "year_month": year_month,
        "center_id": center_id,
        "total_summary": {
            "total_records": len(records),
            "total_amount": sum(r.amount for r in records if r.approval_status in REVENUE_STATUSES),
            "approved_count": sum(1 for r in records if r.approval_status in REVENUE_STATUSES),
            "pending_count": sum(1 for r in records if r.approval_status == "pending")
        },
        "by_caregiver": list(caregiver_stats.values()),
        "by_service": list(service_stats.values()),
        "status_amounts": status_amounts,
        "records": record_rows
    }


@router.delete("/daily/{record_id}")
async def delete_record(
    record_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """
    기록 삭제
    - 센터장: 모든 기록 삭제 가능
    - 요양사: 자신의 기록만 삭제 가능

    Query Parameters:
    - 요청자는 로그인 토큰으로 확인합니다 (본인 기록 또는 센터장)
    """

    # 기록 조회
    record = db.query(DailyRecord).filter(DailyRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다")

    is_manager = actor.role == "center_manager"
    is_own_record = record.caregiver_id == actor.id

    if not (is_manager or is_own_record):
        raise HTTPException(status_code=403, detail="삭제 권한이 없습니다 (자신의 기록만 삭제 가능)")
    if is_manager and not is_own_record and not _record_in_my_center(db, record, actor):
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다")

    pair, pair_billing = _pair_of(db, record)
    if pair and _pair_is_locked(pair_billing):
        raise HTTPException(status_code=400, detail="함께 제공한 요양보호사의 청구가 이미 제출·승인되어 이 기록을 삭제할 수 없습니다")

    # 관련 청구 기록도 함께 삭제 (이 DailyRecord와 연결된 청구만)
    billings = db.query(BillingRecord).filter(
        BillingRecord.daily_record_id == record.id
    ).all()

    try:
        # 청구 기록 삭제 (이 DailyRecord와 연결된 청구만)
        for billing in billings:
            db.delete(billing)
        if pair:  # 2인 동시 제공은 함께 제공한 요양보호사의 기록·청구도 같이 지운다
            if pair_billing:
                db.delete(pair_billing)
            db.delete(pair)

        # 일일 기록 삭제
        db.delete(record)
        db.commit()

        return {
            "status": "success",
            "message": "기록이 삭제되었습니다",
            "record_id": record_id
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"삭제 중 오류 발생: {str(e)}")


# ===== VoiceRecord 자동 청구 생성 =====

@router.post("/voice/create")
async def create_voice_record(
    resident_id: int,
    service_type: str = "basic_care",
    duration_minutes: int = 60,
    transcription: str = "",
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """Create voice record + auto-generate billing"""
    if actor.role != "caregiver":
        raise HTTPException(status_code=403, detail="음성 기록은 요양보호사만 입력할 수 있습니다")
    caregiver_id = actor.id
    try:
        resident = db.query(Resident).filter(Resident.id == resident_id).first()
        if not resident or resident.center_id != actor.center_id:
            raise HTTPException(status_code=404, detail="Resident not found")
        
        if service_type not in ("basic_care", "meal_service", "medical_care", "emergency"):
            raise HTTPException(status_code=400, detail="Invalid service_type")
        if duration_minutes not in VALID_DURATIONS:
            raise HTTPException(status_code=400, detail="Invalid duration_minutes")
        
        now = datetime.now()

        # 음성기록 시점의 이용자 정보 스냅샷 저장
        care_grade = resident.care_grade or 1
        client_type = resident.client_type or "일반"

        voice_record = VoiceRecord(
            caregiver_id=caregiver_id,
            resident_id=resident_id,
            resident_name=resident.name,  # 스냅샷: 음성기록 시점의 이용자 이름
            care_grade=care_grade,  # 스냅샷: 음성기록 시점의 요양등급
            client_type=client_type,  # 스냅샷: 음성기록 시점의 소득분류
            center_id=resident.center_id,
            recorded_date=now,
            service_type=service_type,
            transcription=transcription,
            created_at=now
        )
        db.add(voice_record)
        db.flush()

        total_cost, _, billing_amount = split_visit(duration_minutes, client_type)

        billing_record = BillingRecord(
            caregiver_id=caregiver_id,
            resident_id=resident_id,
            resident_name=resident.name,  # 스냅샷: 청구 시점의 이용자 이름
            care_grade=care_grade,  # 스냅샷: 청구 시점의 요양등급
            client_type=client_type,  # 스냅샷: 청구 시점의 소득분류
            center_id=resident.center_id,
            service_category="재가급여",
            service_type=service_type,
            amount=billing_amount,
            total_cost=total_cost,
            status="draft",
            approval_status="draft",
            recorded_date=now,
            year_month=get_year_month(now),
            created_at=now
        )
        db.add(billing_record)
        db.flush()

        voice_record.billing_record_id = billing_record.id
        if resident.guardian_id:
            summary = guardian_visit_summary(resident.name, service_type, duration_minutes, note=transcription)
            notify(db, resident.guardian_id, "visit_completed", summary)
        db.commit()

        return {
            "status": "success",
            "voice_record_id": voice_record.id,
            "billing_record_id": billing_record.id,
            "amount": billing_amount
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


