from fastapi import APIRouter, HTTPException, File, UploadFile, Depends, Query, Body
from pydantic import BaseModel
from typing import Literal, Optional
from app.billing_rules import split_visit, VALID_DURATIONS, REVENUE_STATUSES
from app.review import find_schedule
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import DailyRecord, BillingRecord, User, Resident, VoiceRecord, MonthlySummary
from app.schemas import DailyRecordResponse
from app.database import get_db
from app.auth import get_current_user, require_manager, assert_self_or_manager
from datetime import datetime, time
import os

router = APIRouter()

UPLOAD_DIR = "uploads/audio"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def get_year_month(date: datetime) -> str:
    """날짜로부터 YYYY-MM 형식의 정산월 추출"""
    return date.strftime("%Y-%m")

# Request 모델
class CreateRecordRequest(BaseModel):
    caregiver_id: int
    resident_id: int
    service_type: str
    notes: str = ""
    care_items: str = ""
    condition: Optional[str] = None
    duration_minutes: Literal[30, 60, 90, 120, 180, 240] = 60
    recorded_date: Optional[datetime] = None  # 소급 기록용 (미지정 시 현재 시각)

class UpdateRecordRequest(BaseModel):
    service_type: Optional[str] = None
    notes: Optional[str] = None
    care_grade: Optional[int] = None  # 요양등급 (스냅샷 수정)
    client_type: Optional[str] = None  # 소득분류 (스냅샷 수정)
    duration_minutes: Optional[Literal[30, 60, 90, 120, 180, 240]] = None
    care_items: Optional[str] = None
    condition: Optional[str] = None
    user_id: Optional[int] = None

class BatchDeleteRequest(BaseModel):
    record_ids: list
    user_id: int
    user_role: str

@router.post("/test")
def test_endpoint():
    """테스트 엔드포인트"""
    return {"message": "POST 작동 확인"}

@router.post("/create")
def create_record(request: CreateRecordRequest, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """일일 기록 생성 및 청부 자동 계산"""
    caregiver_id = actor.id if actor.role == "caregiver" else request.caregiver_id
    try:
        resident = db.query(Resident).filter(Resident.id == request.resident_id).first()
        if not resident:
            raise HTTPException(status_code=404, detail="Resident not found")

        total_cost, _, amount = split_visit(request.duration_minutes, resident.client_type)

        now = request.recorded_date or datetime.now()  # 소급 기록 시 선택한 시각, 아니면 현재 시각(로컬)
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
            condition=request.condition,
            duration_minutes=request.duration_minutes,
            schedule_id=linked_schedule.id if linked_schedule else None,
            service_type=request.service_type,
            audio_file_url=None
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
            amount=amount,
            total_cost=total_cost,
            recorded_date=now,
            year_month=get_year_month(now),
            status="draft",
            approval_status="draft"
        )
        db.add(billing_record)
        db.commit()

        return {
            "status": "success",
            "message": "기록이 저장되고 청구가 자동으로 계산되었습니다",
            "data": {
                "record_id": daily_record.id,
                "billing_id": billing_record.id,
                "billing_amount": amount,
                "service_type": request.service_type,
                "recorded_at": daily_record.recorded_date.isoformat() if daily_record.recorded_date else None
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
        print(f"[ERROR] create_record: {error_msg}")
        raise HTTPException(status_code=500, detail=error_msg)

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

            billings = db.query(BillingRecord).filter(
                BillingRecord.recorded_date == record.recorded_date,
                BillingRecord.caregiver_id == record.caregiver_id,
                BillingRecord.resident_id == record.resident_id
            ).all()

            for billing in billings:
                db.delete(billing)
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
    db: Session = Depends(get_db)
):
    """
    음성 파일 업로드
    실제 Whisper API 연동 시 텍스트 변환
    """
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
    assert_self_or_manager(actor, caregiver_id)
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
                "morning_care": r.morning_care,
                "meal_intake": r.meal_intake,
                "medicine_given": r.medicine_given,
                "notes": r.notes,
                "care_items": r.care_items,
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
    assert_self_or_manager(actor, caregiver_id)
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
                "morning_care": r.morning_care,
                "meal_intake": r.meal_intake,
                "medicine_given": r.medicine_given,
                "notes": r.notes,
                "care_items": r.care_items,
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
    오늘의 기록 조회 + 청부액
    resident_id가 주어지면 해당 이용자의 기록만 조회
    """
    assert_self_or_manager(actor, caregiver_id)
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

        # 일일 기록 ID별 청부액/서비스유형 매핑
        billing_map = {}
        for b in billings:
            if b.daily_record_id:
                billing_map[b.daily_record_id] = {
                    "amount": b.amount,
                    "service_type": b.service_type,
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
                "morning_care": r.morning_care,
                "meal_intake": r.meal_intake,
                "medicine_given": r.medicine_given,
                "notes": r.notes,
                "care_items": r.care_items,
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
    _: User = Depends(require_manager)
):
    """
    센터 전체의 모든 기록 조회 (센터장용)
    해당 센터 요양관리사의 모든 기록 조회
    """
    records = db.query(DailyRecord).join(
        Resident, DailyRecord.resident_id == Resident.id
    ).filter(
        Resident.center_id == center_id
    ).order_by(DailyRecord.recorded_date.desc()).all()

    # 해당 센터의 청부 기록 (음성 기록과 매칭된 것만)
    billings = db.query(BillingRecord).filter(
        BillingRecord.center_id == center_id
    ).all()

    # daily_record_id별 청부액/승인상태 매핑
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
                "notes": r.notes,
                "care_items": r.care_items,
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
    _: User = Depends(require_manager)
):
    """
    센터 전체의 오늘 기록 조회 (센터장용)
    해당 센터 요양관리사의 오늘 기록만 조회
    """
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

    # 해당 센터의 청부 기록 (billing_amount 포함)
    billings = db.query(BillingRecord).filter(
        BillingRecord.center_id == center_id,
        BillingRecord.recorded_date >= today_start,
        BillingRecord.recorded_date <= today_end
    ).all()

    # daily_record_id별 청부액 매핑
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
                "notes": r.notes,
                "recorded_at": r.recorded_date.isoformat() if r.recorded_date else None,
                "billing_amount": billing_map.get(r.id, 0)
            }
            for r in records
        ]
    }

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
            raise HTTPException(status_code=400, detail="작성중 또는 보완 요청 상태의 청부만 수정할 수 있습니다")

        if request.service_type:
            record.service_type = request.service_type
        if request.notes is not None:
            record.notes = request.notes
        if request.duration_minutes is not None:
            record.duration_minutes = request.duration_minutes
        if request.care_items is not None:
            record.care_items = request.care_items or None
        if request.condition is not None:
            record.condition = request.condition or None

        db.commit()
        db.refresh(record)

        if billing:
            if request.service_type:
                billing.service_type = request.service_type
            if request.care_grade is not None:
                billing.care_grade = request.care_grade
            if request.client_type:
                billing.client_type = request.client_type
            total_cost, _, insurance_amount = split_visit(record.duration_minutes or 60, billing.client_type)
            billing.total_cost = total_cost
            billing.amount = insurance_amount
            if billing.approval_status == "rejected":
                billing.approval_status = "draft"
            billing.rejection_reason = None
            db.commit()
            db.refresh(billing)

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
    db: Session = Depends(get_db)
):
    """
    월별 정산 요약 조회
    - center_id: 필수 (센터 ID)
    - year_month: 선택 (YYYY-MM 형식, 미지정시 현재월)
    - caregiver_id: 선택 (특정 요양사만, 미지정시 전체)
    """
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
    db: Session = Depends(get_db)
):
    """
    월별 통계 조회
    - center_id: 필수
    - year, month: 선택 (미지정시 현재월)
    """
    if not year:
        year = datetime.now().year
    if not month:
        month = datetime.now().month

    year_month = f"{year:04d}-{month:02d}"

    # 센터 전체 청부 조회 (반려 포함 원본 목록 → 정산 중단 금액·목록에 사용)
    all_records = db.query(BillingRecord).filter(
        BillingRecord.center_id == center_id,
        BillingRecord.year_month == year_month
    ).all()
    records = [r for r in all_records if r.approval_status != "rejected"]

    residents = {x.id: x.name for x in db.query(Resident).all()}
    user_names = {u.id: u.full_name for u in db.query(User).all()}
    status_amounts = {"target": 0, "completed": 0, "pending": 0, "suspended": 0}
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
            caregiver_stats[caregiver_id]["total_amount"] += record.amount
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
            service_stats[service_type]["total_amount"] += record.amount

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

    # 관련 청구 기록도 함께 삭제 (이 DailyRecord와 연결된 청부만)
    billings = db.query(BillingRecord).filter(
        BillingRecord.daily_record_id == record.id
    ).all()

    try:
        # 청구 기록 삭제 (이 DailyRecord와 연결된 청부만)
        for billing in billings:
            db.delete(billing)

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


# ===== VoiceRecord 자동 청부 생성 =====

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
    caregiver_id = actor.id
    try:
        resident = db.query(Resident).filter(Resident.id == resident_id).first()
        if not resident:
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
        db.commit()

        return {
            "status": "success",
            "voice_record_id": voice_record.id,
            "billing_record_id": billing_record.id,
            "amount": billing_amount
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


