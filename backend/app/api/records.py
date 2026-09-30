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

        # 청계 계산
        with open("/tmp/debug.log", "a") as f:
            f.write(f"  Calculating billing...\n")
        care_grade = resident.care_grade or 1
        client_type = resident.client_type or "일반"
        rates = PATIENT_PAY_RATE.get("재가급여", {})
        patient_rate = rates.get(client_type, 0.15)
        insurance_rate = 1 - patient_rate
        base_amount = VISIT_AMOUNTS_BY_GRADE.get(care_grade, 78875)
        amount = int(base_amount * insurance_rate)

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
            audio_file_url=None
        )
        db.add(daily_record)
        db.flush()
        daily_id = daily_record.id

        # BillingRecord 생성
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
            approval_status="pending"
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

        # 1회 방문당 청부액
        base_amount = VISIT_AMOUNTS_BY_GRADE.get(care_grade, 78875)
        amount = int(base_amount * insurance_rate)

        billing_record = BillingRecord(
            daily_record_id=daily_record.id,
            caregiver_id=caregiver_id,
            resident_id=resident_id,
            center_id=resident.center_id,
            service_category=service_category,
            service_type="basic_care",
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

@router.get("/today/center")
async def get_center_today_records(
    center_id: int,
    db: Session = Depends(get_db)
):
    """
    센터의 오늘의 전체 기록 조회
    """
    today = datetime.now().date()  # 로컬 시간 사용
    today_start = datetime.combine(today, time.min)
    today_end = datetime.combine(today, time.max)

    records = db.query(DailyRecord).filter(
        DailyRecord.recorded_date >= today_start,
        DailyRecord.recorded_date <= today_end
    ).join(Resident).filter(Resident.center_id == center_id).all()

    return {
        "date": today.isoformat(),
        "total_records": len(records),
        "center_id": center_id
    }

@router.get("/recent")
async def get_recent_records(
    caregiver_id: int,
    days: int = 7,
    db: Session = Depends(get_db)
):
    """
    지난 N일간의 기록 조회 (기본: 7일)
    """
    try:
        from datetime import date, datetime as dt, time as time_cls, timedelta

        today = date.today()
        start_date = today - timedelta(days=days - 1)
        start_datetime = dt.combine(start_date, time_cls.min)
        end_datetime = dt.combine(today, time_cls.max)

        records = db.query(DailyRecord).filter(
            DailyRecord.caregiver_id == caregiver_id,
            DailyRecord.recorded_date >= start_datetime,
            DailyRecord.recorded_date <= end_datetime
        ).order_by(DailyRecord.recorded_date.desc()).all()

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
                    "service_type": b.service_type
                }

        billing_total = sum(b.amount for b in billings if b.amount)

        response_records = []
        for r in records:
            billing_info = billing_map.get(r.id, {})
            response_records.append({
                "id": r.id,
                "caregiver_id": r.caregiver_id,
                "resident_id": r.resident_id,
                "service_type": billing_info.get("service_type", "basic_care"),
                "morning_care": r.morning_care,
                "meal_intake": r.meal_intake,
                "medicine_given": r.medicine_given,
                "notes": r.notes,
                "recorded_at": r.recorded_date.isoformat() if r.recorded_date else None,
                "billing_amount": billing_info.get("amount", 0)
            })

        return {
            "days": days,
            "total_records": len(records),
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
    db: Session = Depends(get_db)
):
    """
    모든 기록 조회
    """
    try:
        records = db.query(DailyRecord).filter(
            DailyRecord.caregiver_id == caregiver_id
        ).order_by(DailyRecord.recorded_date.desc()).all()

        billings = db.query(BillingRecord).filter(
            BillingRecord.caregiver_id == caregiver_id
        ).all()

        billing_map = {}
        for b in billings:
            if b.daily_record_id:
                billing_map[b.daily_record_id] = {
                    "amount": b.amount,
                    "service_type": b.service_type
                }

        billing_total = sum(b.amount for b in billings if b.amount)

        response_records = []
        for r in records:
            billing_info = billing_map.get(r.id, {})
            response_records.append({
                "id": r.id,
                "caregiver_id": r.caregiver_id,
                "resident_id": r.resident_id,
                "service_type": billing_info.get("service_type", "basic_care"),
                "morning_care": r.morning_care,
                "meal_intake": r.meal_intake,
                "medicine_given": r.medicine_given,
                "notes": r.notes,
                "recorded_at": r.recorded_date.isoformat() if r.recorded_date else None,
                "billing_amount": billing_info.get("amount", 0)
            })

        return {
            "total_records": len(records),
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
    db: Session = Depends(get_db)
):
    """
    오늘의 기록 조회 + 청부액
    """
    try:
        from datetime import date, datetime as dt, time as time_cls

        today = date.today()
        today_start = dt.combine(today, time_cls.min)
        today_end = dt.combine(today, time_cls.max)

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

        # 일일 기록 ID별 청부액/서비스유형 매핑
        billing_map = {}
        for b in billings:
            if b.daily_record_id:
                billing_map[b.daily_record_id] = {
                    "amount": b.amount,
                    "service_type": b.service_type
                }

        billing_total = sum(b.amount for b in billings if b.amount)

        response_records = []
        for r in records:
            billing_info = billing_map.get(r.id, {})
            response_records.append({
                "id": r.id,
                "caregiver_id": r.caregiver_id,
                "resident_id": r.resident_id,
                "service_type": billing_info.get("service_type", "basic_care"),
                "morning_care": r.morning_care,
                "meal_intake": r.meal_intake,
                "medicine_given": r.medicine_given,
                "notes": r.notes,
                "recorded_at": r.recorded_date.isoformat() if r.recorded_date else None,
                "billing_amount": billing_info.get("amount", 0)
            })

        return {
            "date": today.isoformat(),
            "total_records": len(records),
            "total_billing_amount": billing_total,
            "records": response_records
        }
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[ERROR] get_today_records: {type(e).__name__}: {e}\n{error_trace}")
        raise HTTPException(status_code=500, detail=f"기록 조회 중 오류 발생: {str(e)}")

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

    # 해당 센터의 청부 기록만 조회
    billings = db.query(BillingRecord).filter(
        BillingRecord.center_id == center_id,
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
