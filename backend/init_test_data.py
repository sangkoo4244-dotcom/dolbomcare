#!/usr/bin/env python3
"""테스트 데이터 초기화 스크립트"""

from app.database import SessionLocal
from app.models import User, Center, Resident, BillingRecord, DailyRecord
from datetime import datetime, timedelta
from passlib.context import CryptContext

# 비밀번호 해싱
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

db = SessionLocal()

try:
    print("🔄 테스트 데이터 초기화 중...")

    # 1. 센터 생성
    print("✅ 센터 생성 중...")
    center = Center(
        name="우리요양센터",
        address="서울시 강남구 테헤란로 123",
        phone="02-1234-5678",
        residents_count=5,
        caregivers_count=3
    )
    db.add(center)
    db.flush()
    center_id = center.id
    print(f"  - 센터 생성: {center.name} (ID: {center_id})")

    # 2. 센터장 생성
    print("✅ 센터장 계정 생성 중...")
    manager = User(
        email="manager@test.com",
        hashed_password=hash_password("test123"),
        full_name="김센터장",
        role="center_manager",
        center_id=center_id,
        phone="010-1234-5678",
        is_active=True
    )
    db.add(manager)
    db.flush()
    manager_id = manager.id
    print(f"  - 센터장: {manager.full_name} ({manager.email})")

    # 3. 요양사 생성
    print("✅ 요양사 계정 생성 중...")
    caregiver = User(
        email="caregiver@test.com",
        hashed_password=hash_password("test123"),
        full_name="이요양사",
        role="caregiver",
        center_id=center_id,
        phone="010-9876-5432",
        is_active=True
    )
    db.add(caregiver)
    db.flush()
    caregiver_id = caregiver.id
    print(f"  - 요양사: {caregiver.full_name} ({caregiver.email})")

    # 4. 이용자(입소자) 생성
    print("✅ 이용자 생성 중...")
    residents_data = [
        {"name": "박철수", "care_grade": 1, "client_type": "일반"},
        {"name": "최영희", "care_grade": 2, "client_type": "차상위계층"},
        {"name": "정민준", "care_grade": 3, "client_type": "기초생활보장"},
    ]
    resident_ids = []
    for resident_data in residents_data:
        resident = Resident(
            center_id=center_id,
            name=resident_data["name"],
            birth_date=(datetime.now() - timedelta(days=365*75)).date(),  # 약 75세
            age=75,
            admission_date=datetime.now() - timedelta(days=30),
            health_status="stable",
            guardian_id=manager_id,
            care_grade=resident_data["care_grade"],
            client_type=resident_data["client_type"]
        )
        db.add(resident)
        db.flush()
        resident_ids.append(resident.id)
        print(f"  - 이용자: {resident.name} ({resident_data['care_grade']}등급, {resident_data['client_type']})")

    # 5. 음성 기록(DailyRecord) 생성
    print("✅ 음성 기록 생성 중...")
    now = datetime.now()
    daily_records = []
    daily_record_by_resident = {}  # resident_id별 daily_record_ids 저장

    # 음성 기록: 9건 (각 이용자별 3건씩: 오늘, 1일전, 2일전)
    for i, resident_id in enumerate(resident_ids):
        daily_record_by_resident[resident_id] = []

        # 각 이용자별 3개 기록 (오늘, 1일전, 2일전)
        for day_offset in range(0, 3):
            daily_record = DailyRecord(
                caregiver_id=caregiver_id,
                resident_id=resident_id,
                recorded_date=now - timedelta(days=day_offset),
                service_type="basic_care",
                morning_care=True,
                meal_intake="full",
                medicine_given=True,
                notes=f"이용자 {i+1}의 {day_offset}일전 기록"
            )
            db.add(daily_record)
            db.flush()
            daily_records.append(daily_record)
            daily_record_by_resident[resident_id].append((daily_record.id, day_offset))

    print(f"  - 음성 기록: {len(daily_records)}건 (이용자당 3건씩)")

    # 6. 청부 기록 생성 (모든 음성 기록과 일대일 대응)
    print("✅ 청부 기록 생성 중...")

    billings = []

    # 각 이용자별 3개 청부 기록 (각 음성 기록에 대응)
    billing_statuses = [
        ("pending", "⏳ 대기 중"),
        ("approved", "✅ 승인됨"),
        ("submitted_to_nhis", "📤 건보 청구"),
        ("rejected", "❌ 거절"),
        ("reimbursed", "💰 환급완료"),
    ]

    billing_index = 0
    for resident_idx, resident_id in enumerate(resident_ids):
        for daily_record_id, day_offset in daily_record_by_resident[resident_id]:
            # 상태를 순환하며 할당 (pending → approved → submitted_to_nhis → rejected → reimbursed)
            approval_status, status_label = billing_statuses[billing_index % len(billing_statuses)]

            # 과거 기록은 아카이브 (reimbursed 상태만)
            is_archived = (day_offset > 0 and approval_status == "reimbursed")

            recorded_date = now - timedelta(days=day_offset)

            billing = BillingRecord(
                caregiver_id=caregiver_id,
                resident_id=resident_id,
                center_id=center_id,
                service_category="재가급여",
                service_type="basic_care",
                amount=1300000 + (resident_idx * 100000),  # 이용자별 다른 금액
                status="draft",
                approval_status=approval_status,
                recorded_date=recorded_date,
                is_archived=is_archived,
                daily_record_id=daily_record_id,  # 모든 청부를 음성 기록과 연결
            )

            if approval_status == "approved":
                billing.approved_by = manager_id
                billing.approved_at = recorded_date + timedelta(hours=2)
            elif approval_status == "rejected":
                billing.rejection_reason = "서류 누락"
                billing.approved_by = manager_id
                billing.approved_at = recorded_date + timedelta(hours=1)
            elif approval_status == "submitted_to_nhis":
                billing.approved_by = manager_id
                billing.approved_at = recorded_date + timedelta(hours=1)
            elif approval_status == "reimbursed":
                billing.approved_by = manager_id
                billing.approved_at = recorded_date
                billing.archived_at = recorded_date + timedelta(hours=1)

            db.add(billing)
            billings.append((billing, status_label))
            billing_index += 1

    # 출력
    for i, (billing, status_label) in enumerate(billings):
        print(f"  - 청부 {i+1}: {status_label} (₩{billing.amount:,}) → 음성기록 ID {billing.daily_record_id}")

    db.commit()
    print("\n✅ 테스트 데이터 초기화 완료!")
    print("\n📋 테스트 계정:")
    print("  센터장: manager@test.com / test123")
    print("  요양사: caregiver@test.com / test123")
    print(f"\n📊 생성된 데이터:")
    print(f"  - 센터: 1개")
    print(f"  - 사용자: 2개 (센터장, 요양사)")
    print(f"  - 이용자: {len(resident_ids)}명")
    print(f"  - 음성 기록: {len(daily_records)}건 (이용자당 3건)")
    print(f"  - 청부 기록: {len(billings)}개 (음성 기록과 1:1 대응)")
    print(f"\n✅ 모든 음성 기록이 청부 기록과 연결됨!")

except Exception as e:
    db.rollback()
    print(f"\n❌ 오류: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
