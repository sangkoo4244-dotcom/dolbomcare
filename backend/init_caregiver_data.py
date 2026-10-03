#!/usr/bin/env python3
"""요양사 실제 작업 패턴 기반 테스트 데이터 생성"""

from app.database import SessionLocal
from app.models import User, Center, Resident, BillingRecord, DailyRecord
from datetime import datetime, timedelta
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# SERVICE_TYPE_AMOUNTS - records.py와 동일한 NHIS 기준 청부액
SERVICE_TYPE_AMOUNTS = {
    "basic_care": {1: 78875, 2: 67043, 3: 55211},
    "meal_service": {1: 39437, 2: 33521, 3: 27605},
    "medical_care": {1: 118312, 2: 100565, 3: 82818},
}

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

db = SessionLocal()

try:
    print("🔄 요양사 실제 패턴 기반 데이터 초기화 중...")

    # 1. 센터 생성
    print("✅ 센터 생성 중...")
    center = Center(
        name="요양보호사 센터",
        address="서울시 강남구",
        phone="02-1234-5678",
        residents_count=3,
        caregivers_count=1
    )
    db.add(center)
    db.flush()
    center_id = center.id
    print(f"  - 센터: {center.name} (ID: {center_id})")

    # 2. 센터장 생성
    print("✅ 센터장 생성 중...")
    manager = User(
        email="manager@test.com",
        hashed_password=hash_password("test123"),
        full_name="이센터장",
        role="center_manager",
        center_id=center_id,
        phone="010-1111-1111",
        is_active=True
    )
    db.add(manager)
    db.flush()
    manager_id = manager.id
    print(f"  - 센터장: {manager.full_name}")

    # 3. 요양사 생성
    print("✅ 요양사 생성 중...")
    caregiver = User(
        email="caregiver@test.com",
        hashed_password=hash_password("test123"),
        full_name="박요양사",
        role="caregiver",
        center_id=center_id,
        phone="010-9999-9999",
        is_active=True
    )
    db.add(caregiver)
    db.flush()
    caregiver_id = caregiver.id
    print(f"  - 요양사: {caregiver.full_name}")

    # 4. 이용자 생성 (3명)
    print("✅ 이용자 생성 중...")
    residents_data = [
        {"name": "김할머니", "care_grade": 1, "client_type": "일반"},
        {"name": "이할머니", "care_grade": 2, "client_type": "차상위계층"},
        {"name": "박할머니", "care_grade": 3, "client_type": "기초생활보장"},
    ]
    resident_ids = []
    for data in residents_data:
        resident = Resident(
            center_id=center_id,
            name=data["name"],
            birth_date=(datetime.now() - timedelta(days=365*80)).date(),
            age=80,
            admission_date=datetime.now() - timedelta(days=90),
            health_status="stable",
            guardian_id=manager_id,
            care_grade=data["care_grade"],
            client_type=data["client_type"]
        )
        db.add(resident)
        db.flush()
        resident_ids.append(resident.id)
        print(f"  - {data['name']} ({data['care_grade']}등급)")

    # 5. 음성 기록 생성 (요양사 실제 작업 패턴)
    print("✅ 음성 기록 생성 중... (요양사 일일 기록)")

    now = datetime.now()
    daily_records_by_day = {}
    record_counter = 0

    # 3일간의 기록 (오늘, 어제, 그저께)
    service_types = ["basic_care", "meal_service", "medical_care"]
    service_labels = ["기본 돌봄", "식사 서빙", "의료 관리"]

    for day_offset in [0, 1, 2]:  # 0=오늘, 1=어제, 2=그저께
        recorded_date = now - timedelta(days=day_offset)
        daily_records_by_day[day_offset] = []

        # 각 이용자마다 기록
        for resident_idx, resident_id in enumerate(resident_ids):
            # 이용자당 3개 기록 (기본돌봄, 식사, 의료관리)
            for service_idx, service_type in enumerate(service_types):
                record_counter += 1

                # 실제 요양사가 작성하는 기록 패턴
                daily_record = DailyRecord(
                    caregiver_id=caregiver_id,
                    resident_id=resident_id,
                    recorded_date=recorded_date,
                    service_type=service_type,
                    morning_care=(service_type == "basic_care"),
                    meal_intake="full" if service_type == "meal_service" else "partial",
                    medicine_given=(service_type == "medical_care"),
                    notes=f"{residents_data[resident_idx]['name']} {day_offset}일전 {service_labels[service_idx]}"
                )
                db.add(daily_record)
                db.flush()
                daily_records_by_day[day_offset].append(daily_record)

    print(f"  - 음성 기록: {record_counter}건 생성 (3명 × 3서비스 × 3일)")

    # 6. 청부 기록 생성 (음성 기록과 1:1 대응)
    print("✅ 청부 기록 생성 중...")

    # 다양한 상태 순환
    statuses = ["pending", "approved", "submitted_to_nhis", "rejected", "reimbursed"]
    status_labels = {
        "pending": "⏳ 대기 중",
        "approved": "✅ 승인됨",
        "submitted_to_nhis": "📤 건보 청구",
        "rejected": "❌ 거절",
        "reimbursed": "💰 환급완료"
    }

    billing_count = 0
    status_idx = 0

    # 모든 음성 기록에 대해 청부 생성
    for day_offset in sorted(daily_records_by_day.keys()):
        for daily_record in daily_records_by_day[day_offset]:
            status = statuses[status_idx % len(statuses)]
            status_idx += 1

            # 건강보험공단 기준: 서비스 유형 + 요양 등급별 청부액
            resident = db.query(Resident).filter(Resident.id == daily_record.resident_id).first()

            # SERVICE_TYPE_AMOUNTS에서 청부액 조회 (records.py와 동일)
            service_rates = SERVICE_TYPE_AMOUNTS.get(daily_record.service_type, SERVICE_TYPE_AMOUNTS["basic_care"])
            amount = service_rates.get(resident.care_grade, service_rates[1])

            billing = BillingRecord(
                caregiver_id=caregiver_id,
                resident_id=daily_record.resident_id,
                center_id=center_id,
                service_category="재가급여",
                service_type=daily_record.service_type,
                amount=amount,  # NHIS 기준 청부액
                status="draft",
                approval_status=status,
                recorded_date=daily_record.recorded_date,
                year_month=daily_record.recorded_date.strftime("%Y-%m"),
                is_archived=(status == "reimbursed"),
                daily_record_id=daily_record.id  # 반드시 연결!
            )

            # 상태별 추가 정보
            if status == "approved":
                billing.approved_by = manager_id
                billing.approved_at = daily_record.recorded_date + timedelta(hours=1)
            elif status == "submitted_to_nhis":
                billing.approved_by = manager_id
                billing.approved_at = daily_record.recorded_date + timedelta(hours=1)
            elif status == "reimbursed":
                billing.approved_by = manager_id
                billing.approved_at = daily_record.recorded_date + timedelta(hours=1)
                billing.archived_at = daily_record.recorded_date + timedelta(hours=2)
            elif status == "rejected":
                billing.rejection_reason = "서류 미흡"
                billing.approved_by = manager_id
                billing.approved_at = daily_record.recorded_date + timedelta(hours=1)

            db.add(billing)
            billing_count += 1

    db.commit()

    print(f"\n✅ 테스트 데이터 초기화 완료!")
    print(f"\n📋 테스트 계정:")
    print(f"  센터장: manager@test.com / test123")
    print(f"  요양사: caregiver@test.com / test123")
    print(f"\n📊 생성된 데이터:")
    print(f"  - 센터: 1개")
    print(f"  - 이용자: 3명 (김할머니, 이할머니, 박할머니)")
    print(f"  - 음성 기록: {record_counter}건")
    print(f"  - 청부 기록: {billing_count}건 (1:1 연결됨)")
    print(f"\n✅ 요양사가 실제 작성하는 패턴으로 생성됨!")

except Exception as e:
    db.rollback()
    print(f"\n❌ 오류: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
