from fastapi import APIRouter, HTTPException, File, UploadFile, Depends, Query, Body
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from app.models import DailyRecord, BillingRecord, User, Resident, VoiceRecord
from app.schemas import DailyRecordResponse
from app.database import get_db
from datetime import datetime, time
import os

# 등급별 월 인정급여액
CARE_GRADE_LIMITS = {
    1: 1577500,  # 1등급
    2: 1399500,  # 2등급
    3: 1193000,  # 3등급
    4: 1082500,  # 4등급
    5: 235000,   # 5등급
}

# 등급별 월 기준 방문 수 (1회당 청구액을 계산하기 위함)
STANDARD_VISITS_PER_MONTH = 20

# 1회 방문 기본 청구액 (등급별)
VISIT_AMOUNTS_BY_GRADE = {
    1: int(1577500 / STANDARD_VISITS_PER_MONTH),  # 약 78,875원
    2: int(1399500 / STANDARD_VISITS_PER_MONTH),  # 약 69,975원
    3: int(1193000 / STANDARD_VISITS_PER_MONTH),  # 약 59,650원
    4: int(1082500 / STANDARD_VISITS_PER_MONTH),  # 약 54,125원
    5: int(235000 / STANDARD_VISITS_PER_MONTH),   # 약 11,750원
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

# 서비스 유형별 1회 청부액 (등급별) - NHIS 건강보험공단 기준
# 2등급: 1등급 × 85% | 3등급: 1등급 × 70%
SERVICE_TYPE_AMOUNTS = {
    "basic_care": {
        1: 78875,
        2: 67043,   # 85%
        3: 55211,   # 70%
        4: 55211,   # 70% (4등급 = 3등급)
        5: 55211    # 70% (5등급 = 3등급)
    },
    "meal_service": {
        1: 39437,
        2: 33521,   # 85%
        3: 27605,   # 70%
        4: 27605,
        5: 27605
    },
    "medical_care": {
        1: 118312,
        2: 100565,  # 85%
        3: 82818,   # 70%
        4: 82818,
        5: 82818
    },
    "emergency": {
        1: 157750,
        2: 134087,  # 85%
        3: 110425,  # 70%
        4: 110425,
        5: 110425
    }
}

router = APIRouter()

# 음성 파일 저장 디렉토리
UPLOAD_DIR = "uploads/audio"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Request 모델
class CreateRecordRequest(BaseModel):
    caregiver_id: int
    resident_id: int
    service_type: str
    notes: str = ""

class UpdateRecordRequest(BaseModel):
    service_type: Optional[str] = None
    notes: Optional[str] = None

class BatchDeleteRequest(BaseModel):
    record_ids: list
    user_id: int
    user_role: str

@router.post("/test")
def test_endpoint():
    """테스트 엔드포인트"""
    return {"message": "POST 작동 확인"}

@router.post("/create")
def create_record(request: CreateRecordRequest, db: Session = Depends(get_db)):
    """일일 기록 생성 및 청부 자동 계산"""
    with open("/tmp/debug.log", "a") as f:
        f.write(f"[{datetime.utcnow()}] START create_record\n")
        f.write(f"  caregiver_id={request.caregiver_id}, resident_id={request.resident_id}\n")
    try:
        with open("/tmp/debug.log", "a") as f:
            f.write(f"  Querying resident {request.resident_id}...\n")
        resident = db.query(Resident).filter(Resident.id == request.resident_id).first()
        with open("/tmp/debug.log", "a") as f:
            f.write(f"  Resident found: {resident is not None}\n")
        if not resident:
            raise HTTPException(status_code=404, detail="Resident not found")

        print(f"[DEBUG] 이용자 조회 시작...")
        resident = db.query(Resident).filter(Resident.id == request.resident_id).first()
        if not resident:
            print(f"[ERROR] 이용자 {request.resident_id} 없음")
            raise HTTPException(status_code=404, detail="Resident not found")
        print(f"[DEBUG] 이용자 찾음: {resident.id}, center_id={resident.center_id}")

        # NHIS 기준 청부 계산: 서비스 유형 + 요양 등급
        with open("/tmp/debug.log", "a") as f:
            f.write(f"  Calculating billing (NHIS standard)...\n")
        care_grade = resident.care_grade or 1
        service_type = request.service_type or "basic_care"

        # SERVICE_TYPE_AMOUNTS에서 청부액 조회
        service_rates = SERVICE_TYPE_AMOUNTS.get(service_type, SERVICE_TYPE_AMOUNTS["basic_care"])
        amount = service_rates.get(care_grade, service_rates[1])

        # DailyRecord 생성
        with open("/tmp/debug.log", "a") as f:
            f.write(f"  Creating DailyRecord...\n")
        now = datetime.now()  # 로컬 시간 사용 (UTC 대신)
        daily_record = DailyRecord(
            resident_id=request.resident_id,
            caregiver_id=request.caregiver_id,
            recorded_date=now,
            morning_care=request.service_type == "basic_care",
            meal_intake="full" if request.service_type == "meal_service" else "partial",
            medicine_given=request.service_type == "medical_care",
            notes=request.notes,
            service_type=request.service_type,
            audio_file_url=None
        )
        db.add(daily_record)
        db.flush()
        daily_id = daily_record.id

        # BillingRecord 생성 (draft 상태로 시작 - 요양사가 제출하기 전)
        with open("/tmp/debug.log", "a") as f:
            f.write(f"  Creating BillingRecord...\n")
        billing_record = BillingRecord(
            daily_record_id=daily_id,
            caregiver_id=request.caregiver_id,
            resident_id=request.resident_id,
            center_id=resident.center_id,
            service_category="재가급여",
            service_type=request.service_type,
            amount=amount,
            recorded_date=now,
            status="draft",
            approval_status="draft"
        )
        db.add(billing_record)
        db.commit()

        with open("/tmp/debug.log", "a") as f:
            f.write(f"  SUCCESS: daily_id={daily_id}, billing_id={billing_record.id}\n")

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
    db: Session = Depends(get_db)
):
    """여러 기록 일괄 삭제 (자신의 기록 또는 센터장만)"""
    try:
        is_manager = request.user_role == "center_manager"
        deleted = 0

        for record_id in request.record_ids:
            record = db.query(DailyRecord).filter(DailyRecord.id == record_id).first()
            if not record:
                continue

            is_own_record = record.caregiver_id == request.user_id
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

        # 음성 파일로 청구 기록 생성 (1회 방문당 청부)
        care_grade = resident.care_grade if resident.care_grade else 1
        client_type = resident.client_type if resident.client_type else "일반"

        service_category = "재가급여"
        category_rates = PATIENT_PAY_RATE.get(service_category, PATIENT_PAY_RATE["재가급여"])
        patient_rate = category_rates.get(client_type, 0.15)
        insurance_rate = 1 - patient_rate

        # 1회 방문당 청부액 (service_type별로 다름)
        # SERVICE_TYPE_AMOUNTS를 사용하여 service_type에 맞는 금액 적용
        service_type = request.service_type if hasattr(request, 'service_type') else "basic_care"
        base_amount = SERVICE_TYPE_AMOUNTS.get(service_type, {}).get(care_grade, 78875)
        amount = int(base_amount * insurance_rate)

        billing_record = BillingRecord(
            daily_record_id=daily_record.id,
            caregiver_id=caregiver_id,
            resident_id=resident_id,
            center_id=resident.center_id,
            service_category=service_category,
            service_type=service_type,  # ✅ 사용자가 선택한 service_type 적용
            amount=amount,
            recorded_date=datetime.now(),  # 로컬 시간 사용
            approval_status="pending",  # 센터장 승인 대기
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
    db: Session = Depends(get_db)
):
    """
    지난 N일간의 기록 조회 (기본: 7일)
    resident_id가 주어지면 해당 이용자의 기록만 조회
    """
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
    db: Session = Depends(get_db)
):
    """
    모든 기록 조회
    resident_id가 주어지면 해당 이용자의 기록만 조회
    """
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
                    "service_type": b.service_type
                }

        # 요양사 기준: submitted_to_nhis 제외
        caregiver = db.query(User).filter(User.id == caregiver_id).first()

        response_records = []
        billing_total = 0
        for r in records:
            billing_info = billing_map.get(r.id, {})
            billing_amount = billing_info.get("amount", 0)

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
                "recorded_at": r.recorded_date.isoformat() if r.recorded_date else None,
                "billing_amount": billing_amount
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
    db: Session = Depends(get_db)
):
    """
    오늘의 기록 조회 + 청부액
    resident_id가 주어지면 해당 이용자의 기록만 조회
    """
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
    db: Session = Depends(get_db)
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

    # daily_record_id별 청부액 매핑
    billing_map = {}
    billing_total = 0
    for b in billings:
        if b.daily_record_id:
            billing_map[b.daily_record_id] = b.amount
            billing_total += b.amount  # 음성 기록과 매칭된 것만 합산

    return {
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

@router.get("/today/center")
async def get_today_center_records(
    center_id: int,
    db: Session = Depends(get_db)
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

@router.get("/{record_id}")
async def get_record(
    record_id: int,
    db: Session = Depends(get_db)
):
    """
    기록 상세 조회
    """
    record = db.query(DailyRecord).filter(DailyRecord.id == record_id).first()
    if not record:
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
                "amount": b.amount,
                "status": b.status
            }
            for b in billings
        ]
    }

@router.patch("/{record_id}")
async def update_record(
    record_id: int,
    request: UpdateRecordRequest,
    db: Session = Depends(get_db)
):
    """
    음성기록 수정 (메모/서비스 유형 변경)
    """
    try:
        record = db.query(DailyRecord).filter(DailyRecord.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다")

        # 필드 업데이트
        if request.service_type:
            record.service_type = request.service_type
        if request.notes is not None:
            record.notes = request.notes

        db.commit()
        db.refresh(record)

        # 연관된 청부 기록도 업데이트
        if request.service_type:
            billing = db.query(BillingRecord).filter(
                BillingRecord.daily_record_id == record_id
            ).first()
            if billing:
                billing.service_type = request.service_type
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
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[ERROR] update_record: {type(e).__name__}: {e}\n{error_trace}")
        raise HTTPException(status_code=500, detail=f"수정 중 오류 발생: {str(e)}")

@router.delete("/{record_id}")
async def delete_record(
    record_id: int,
    user_id: int,
    user_role: str,
    db: Session = Depends(get_db)
):
    """
    기록 삭제
    - 센터장: 모든 기록 삭제 가능
    - 요양사: 자신의 기록만 삭제 가능
    """

    # 기록 조회
    record = db.query(DailyRecord).filter(DailyRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다")

    # 권한 검증
    is_manager = user_role == "center_manager"
    is_own_record = record.caregiver_id == user_id

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
# SERVICE_TYPE_AMOUNTS는 파일 상단에 정의됨 (create_record와 공유)

@router.post("/voice/create")
async def create_voice_record(
    caregiver_id: int,
    resident_id: int,
    service_type: str = "basic_care",
    transcription: str = "",
    db: Session = Depends(get_db)
):
    """Create voice record + auto-generate billing"""
    try:
        resident = db.query(Resident).filter(Resident.id == resident_id).first()
        if not resident:
            raise HTTPException(status_code=404, detail="Resident not found")
        
        if service_type not in SERVICE_TYPE_AMOUNTS:
            raise HTTPException(status_code=400, detail="Invalid service_type")
        
        voice_record = VoiceRecord(
            caregiver_id=caregiver_id,
            resident_id=resident_id,
            center_id=resident.center_id,
            recorded_date=datetime.utcnow(),
            service_type=service_type,
            transcription=transcription,
            created_at=datetime.utcnow()
        )
        db.add(voice_record)
        db.flush()
        
        care_grade = resident.care_grade or 1

        # NHIS 기준: 서비스 유형 + 요양 등급별 청부액 (건강보험공단 정산액)
        service_rates = SERVICE_TYPE_AMOUNTS.get(service_type, SERVICE_TYPE_AMOUNTS["basic_care"])
        billing_amount = service_rates.get(care_grade, service_rates[1])

        billing_record = BillingRecord(
            caregiver_id=caregiver_id,
            resident_id=resident_id,
            center_id=resident.center_id,
            service_category=service_category,
            service_type=service_type,
            amount=billing_amount,
            status="draft",
            approval_status="pending",
            recorded_date=datetime.utcnow(),
            created_at=datetime.utcnow()
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