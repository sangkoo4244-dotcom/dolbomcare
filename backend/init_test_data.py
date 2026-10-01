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
    today_daily_record_ids = []

    # 오늘 기록: 5건 (청부 5개와 연결)
    for i, resident_id in enumerate(resident_ids):
        # 이용자1: 2개 (pending, rejected)
        # 이용자2: 2개 (approved, reimbursed)
        # 이용자3: 1개 (submitted_to_nhis)
        count = 2 if i < 2 else 1

        for j in range(count):
            daily_record = DailyRecord(
                caregiver_id=caregiver_id,
                resident_id=resident_id,
                recorded_date=now,  # 오늘
                service_type="basic_care",
                morning_care=True,
                meal_intake="full",
                medicine_given=True,
                notes=f"이용자 {i+1}의 오늘 기록 #{j+1}"
            )
            db.add(daily_record)
            db.flush()
            daily_records.append(daily_record)
            today_daily_record_ids.append(daily_record.id)

    # 과거 기록: 7건 (전체 기록 테스트용)
    for i, resident_id in enumerate(resident_ids):
        for day_offset in range(1, 3):  # 1~2일 전
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

    print(f"  - 음성 기록: {len(daily_records)}건 (오늘: 2건, 과거: 7건)")

    # 6. 청부 기록 생성 (다양한 상태)
    print("✅ 청부 기록 생성 중...")

    billings = [
        # 대기 중 (오늘 + 이용자1)
        {
            "resident_id": resident_ids[0],
            "approval_status": "pending",
            "status": "draft",
            "amount": 1400000,
            "days_ago": 0
        },
        # 승인됨 (오늘 + 이용자2)
        {
            "resident_id": resident_ids[1],
            "approval_status": "approved",
            "status": "draft",
            "amount": 1260000,
            "days_ago": 0
        },
        # 건보 청구됨 (오늘 + 이용자3)
        {
            "resident_id": resident_ids[2],
            "approval_status": "submitted_to_nhis",
            "status": "draft",
            "amount": 1070000,
            "days_ago": 0
        },
        # 거절됨 (오늘 + 이용자1)
        {
            "resident_id": resident_ids[0],
            "approval_status": "rejected",
            "status": "draft",
            "amount": 1260000,
            "days_ago": 0,
            "rejection_reason": "서류 누락"
        },
        # 환급완료 (과거 + 아카이브됨 - voice_record 오늘에서 제외)
        {
            "resident_id": resident_ids[1],
            "approval_status": "reimbursed",
            "status": "draft",
            "amount": 1400000,
            "days_ago": 10,
            "is_archived": True
        },
    ]

    for i, billing_data in enumerate(billings):
        recorded_date = now - timedelta(days=billing_data["days_ago"])

        billing = BillingRecord(
            caregiver_id=caregiver_id,
            resident_id=billing_data["resident_id"],
            center_id=center_id,
            service_category="재가급여",
            service_type="basic_care",
            amount=billing_data["amount"],
            status=billing_data["status"],
            approval_status=billing_data["approval_status"],
            recorded_date=recorded_date,
            is_archived=billing_data.get("is_archived", False),
            # 오늘 청부는 DailyRecord와 연결
            daily_record_id=today_daily_record_ids[i] if i < len(today_daily_record_ids) else None,
        )

        if billing_data["approval_status"] == "approved":
            billing.approved_by = manager_id
            billing.approved_at = recorded_date + timedelta(hours=2)
        elif billing_data["approval_status"] == "rejected":
            billing.rejection_reason = billing_data.get("rejection_reason", "")
            billing.approved_by = manager_id
            billing.approved_at = recorded_date + timedelta(hours=1)
        elif billing_data["approval_status"] == "submitted_to_nhis":
            billing.approved_by = manager_id
            billing.approved_at = recorded_date + timedelta(hours=1)
        elif billing_data["approval_status"] == "reimbursed":
            billing.approved_by = manager_id
            billing.approved_at = recorded_date
            billing.archived_at = recorded_date + timedelta(hours=1)

        db.add(billing)
        status_label = {
            "pending": "⏳ 대기 중",
            "approved": "✅ 승인됨",
            "submitted_to_nhis": "📤 건보 청구",
            "rejected": "❌ 거절",
            "reimbursed": "💰 환급완료 (아카이브)"
        }
        print(f"  - 청부 {i+1}: {status_label.get(billing_data['approval_status'], '?')} (₩{billing_data['amount']:,})")

    db.commit()
    print("\n✅ 테스트 데이터 초기화 완료!")
    print("\n📋 테스트 계정:")
    print("  센터장: manager@test.com / test123")
    print("  요양사: caregiver@test.com / test123")
    print(f"\n📊 생성된 데이터:")
    print(f"  - 센터: 1개")
    print(f"  - 사용자: 2개 (센터장, 요양사)")
    print(f"  - 이용자: {len(resident_ids)}명")
    print(f"  - 음성 기록: {len(daily_records)}건")
    print(f"  - 청부 기록: {len(billings)}개 (활성: 3개, 아카이브: 1개, 거절: 1개)")

except Exception as e:
    db.rollback()
    print(f"\n❌ 오류: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
