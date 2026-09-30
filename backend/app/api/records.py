from fastapi import APIRouter, HTTPException, File, UploadFile, Depends, Query, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.models import DailyRecord, BillingRecord, User, Resident
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

@router.post("/create")
async def create_record(
    request: CreateRecordRequest,
    db: Session = Depends(get_db)
):
    """
    일일 기록 생성 및 청구 자동 계산
    음성 → 텍스트 → 청구액 자동 계산
    """
    try:
        caregiver = db.query(User).filter(User.id == request.caregiver_id).first()
        if not caregiver:
            raise HTTPException(status_code=404, detail="Caregiver not found")

        resident = db.query(Resident).filter(Resident.id == request.resident_id).first()
        if not resident:
            raise HTTPException(status_code=404, detail="Resident not found")

        # 1. 일일 기록 저장
        daily_record = DailyRecord(
            resident_id=request.resident_id,
            caregiver_id=request.caregiver_id,
            recorded_date=datetime.utcnow(),
            morning_care=request.service_type == "basic_care",
            meal_intake="full" if request.service_type == "meal_service" else "partial",
            medicine_given=request.service_type == "medical_care",
            notes=request.notes,
            audio_file_url=None
        )
        db.add(daily_record)
        db.commit()
        db.refresh(daily_record)

        # 2. 청구 기록 자동 생성
        care_grade = resident.care_grade if resident.care_grade else 1
        client_type = resident.client_type if resident.client_type else "일반"

        monthly_limit = CARE_GRADE_LIMITS.get(care_grade, 1577500)

        service_category = "재가급여"
        category_rates = PATIENT_PAY_RATE.get(service_category, PATIENT_PAY_RATE["재가급여"])
        patient_rate = category_rates.get(client_type, 0.15)
        insurance_rate = 1 - patient_rate

        amount = int(monthly_limit * insurance_rate)

        billing_record = BillingRecord(
            caregiver_id=request.caregiver_id,
            resident_id=request.resident_id,
            center_id=resident.center_id,
            service_category=service_category,
            service_type=request.service_type,
            amount=amount,
            recorded_date=datetime.utcnow(),
            status="draft"
        )
        db.add(billing_record)
        db.commit()
        db.refresh(billing_record)

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
        print(f"[ERROR] create_record: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

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
            recorded_date=datetime.utcnow(),
            morning_care=True,
            meal_intake="full",
            medicine_given=False,
            notes="음성 기록으로 자동 생성",
            audio_file_url=filepath
        )
        db.add(daily_record)
        db.commit()
        db.refresh(daily_record)

        # 음성 파일로 청구 기록 생성 (월별 청구 대기)
        care_grade = resident.care_grade if resident.care_grade else 1
        client_type = resident.client_type if resident.client_type else "일반"

        monthly_limit = CARE_GRADE_LIMITS.get(care_grade, 1577500)

        service_category = "재가급여"
        category_rates = PATIENT_PAY_RATE.get(service_category, PATIENT_PAY_RATE["재가급여"])
        patient_rate = category_rates.get(client_type, 0.15)
        insurance_rate = 1 - patient_rate

        # 월 청부액 (월 한도액 기준)
        amount = int(monthly_limit * insurance_rate)

        billing_record = BillingRecord(
            caregiver_id=caregiver_id,
            resident_id=resident_id,
            center_id=resident.center_id,
            service_category=service_category,
            service_type="basic_care",
            amount=amount,
            recorded_date=datetime.utcnow(),
            status="draft"
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

@router.get("/today")
async def get_today_records(
    caregiver_id: int,
    db: Session = Depends(get_db)
):
    """
    오늘의 기록 조회 + 청부액
    """
    today = datetime.utcnow().date()
    today_start = datetime.combine(today, time.min)
    today_end = datetime.combine(today, time.max)

    records = db.query(DailyRecord).filter(
        DailyRecord.caregiver_id == caregiver_id,
        DailyRecord.recorded_date >= today_start,
        DailyRecord.recorded_date <= today_end
    ).all()

    # 관련 청구 기록 조회
    billings = db.query(BillingRecord).filter(
        BillingRecord.recorded_date >= today_start,
        BillingRecord.recorded_date <= today_end,
        BillingRecord.caregiver_id == caregiver_id
    ).all()

    # 기록 ID별 청부액/서비스유형 매핑
    billing_map = {b.id: {"amount": b.amount, "service_type": b.service_type} for b in billings}
    billing_total = sum(b.amount for b in billings)

    return {
        "date": today.isoformat(),
        "total_records": len(records),
        "total_billing_amount": billing_total,
        "records": [
            {
                "id": r.id,
                "resident_id": r.resident_id,
                "service_type": billing_map.get(r.id, {}).get("service_type", "basic_care"),
                "morning_care": r.morning_care,
                "meal_intake": r.meal_intake,
                "medicine_given": r.medicine_given,
                "notes": r.notes,
                "recorded_at": r.recorded_date.isoformat() if r.recorded_date else None,
                "billing_amount": billing_map.get(r.id, {}).get("amount", 0)
            }
            for r in records
        ]
    }

@router.get("/today/center")
async def get_today_center_records(
    db: Session = Depends(get_db)
):
    """
    센터 전체의 오늘 기록 조회 (센터장용)
    모든 요양관리사의 오늘 기록을 합산
    """
    today = datetime.utcnow().date()
    today_start = datetime.combine(today, time.min)
    today_end = datetime.combine(today, time.max)

    # 오늘 생성된 모든 기록
    records = db.query(DailyRecord).filter(
        DailyRecord.recorded_date >= today_start,
        DailyRecord.recorded_date <= today_end
    ).all()

    # 관련 청부 기록
    billings = db.query(BillingRecord).filter(
        BillingRecord.recorded_date >= today_start,
        BillingRecord.recorded_date <= today_end
    ).all()

    billing_total = sum(b.amount for b in billings)

    return {
        "date": today.isoformat(),
        "total_records": len(records),
        "total_billing_amount": billing_total,
        "records": [
            {
                "id": r.id,
                "caregiver_id": r.caregiver_id,
                "resident_id": r.resident_id,
                "recorded_at": r.recorded_date.isoformat() if r.recorded_date else None,
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

@router.delete("/{record_id}")
async def delete_record(
    record_id: int,
    user_role: str,
    db: Session = Depends(get_db)
):
    """
    기록 삭제 (센터장/운영자만 가능)
    """
    # 권한 검증: center_manager만 삭제 가능
    if user_role not in ["center_manager"]:
        raise HTTPException(status_code=403, detail="기록 삭제 권한이 없습니다 (센터장만 삭제 가능)")

    # 기록 조회
    record = db.query(DailyRecord).filter(DailyRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다")

    # 관련 청구 기록도 함께 삭제
    billings = db.query(BillingRecord).filter(
        BillingRecord.recorded_date == record.recorded_date,
        BillingRecord.caregiver_id == record.caregiver_id,
        BillingRecord.resident_id == record.resident_id
    ).all()

    try:
        # 청구 기록 삭제
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
