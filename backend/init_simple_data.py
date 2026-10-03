#!/usr/bin/env python3
"""10명의 간단한 테스트 데이터 - 정확한 검증용"""

from app.database import SessionLocal
from app.models import User, Center, Resident, BillingRecord, DailyRecord
from datetime import datetime, timedelta
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# SERVICE_TYPE_AMOUNTS - records.py와 동일
SERVICE_TYPE_AMOUNTS = {
    "basic_care": {1: 78875, 2: 67043, 3: 55211},
    "meal_service": {1: 39437, 2: 33521, 3: 27605},
    "medical_care": {1: 118312, 2: 100565, 3: 82818},
}

db = SessionLocal()

try:
    print("🔄 간단한 테스트 데이터 생성 (10명)")
    print("=" * 60)

    # 1. 센터 생성
    center = Center(
        name="테스트센터",
        address="서울시",
        phone="02-0000-0000",
        residents_count=10,
        caregivers_count=2
    )
    db.add(center)
    db.flush()
    center_id = center.id
    print(f"✅ 센터: {center.name} (ID: {center_id})")

    # 2. 센터장 생성
    manager = User(
        email="manager@test.com",
        hashed_password=pwd_context.hash("test123"),
        full_name="센터장",
        role="center_manager",
        center_id=center_id,
        phone="010-1111-1111",
        is_active=True
    )
    db.add(manager)
    db.flush()
    manager_id = manager.id
    print(f"✅ 센터장: {manager.full_name}")

    # 3. 요양사 2명
    caregivers = []
    for i in range(1, 3):
        caregiver = User(
            email=f"caregiver{i}@test.com",
            hashed_password=pwd_context.hash("test123"),
            full_name=f"요양사{i}",
            role="caregiver",
            center_id=center_id,
            phone=f"010-{9000+i}000-0000",
            is_active=True
        )
        db.add(caregiver)
        db.flush()
        caregivers.append((caregiver.id, f"요양사{i}"))
    print(f"✅ 요양사: {len(caregivers)}명")

    # 4. 이용자 10명 (1등급 3명, 2등급 3명, 3등급 4명)
    print("\n✅ 이용자 생성:")
    residents = []
    resident_idx = 0

    # 1등급 3명
    for i in range(1, 4):
        resident = Resident(
            center_id=center_id,
            name=f"김{i}",
            birth_date=(datetime.now() - timedelta(days=365*80)).date(),
            age=80,
            admission_date=datetime.now() - timedelta(days=90),
            health_status="stable",
            guardian_id=manager_id,
            care_grade=1,
            client_type="일반"
        )
        db.add(resident)
        db.flush()
        residents.append(resident.id)
        resident_idx += 1
        print(f"  {resident_idx}. 김{i} (1등급, 일반)")

    # 2등급 3명
    for i in range(1, 4):
        resident = Resident(
            center_id=center_id,
            name=f"이{i}",
            birth_date=(datetime.now() - timedelta(days=365*75)).date(),
            age=75,
            admission_date=datetime.now() - timedelta(days=90),
            health_status="stable",
            guardian_id=manager_id,
            care_grade=2,
            client_type="차상위계층"
        )
        db.add(resident)
        db.flush()
        residents.append(resident.id)
        resident_idx += 1
        print(f"  {resident_idx}. 이{i} (2등급, 차상위)")

    # 3등급 4명
    for i in range(1, 5):
        resident = Resident(
            center_id=center_id,
            name=f"박{i}",
            birth_date=(datetime.now() - timedelta(days=365*70)).date(),
            age=70,
            admission_date=datetime.now() - timedelta(days=90),
            health_status="stable",
            guardian_id=manager_id,
            care_grade=3,
            client_type="기초생활보장"
        )
        db.add(resident)
        db.flush()
        residents.append(resident.id)
        resident_idx += 1
        print(f"  {resident_idx}. 박{i} (3등급, 기초)")

    print(f"\n✅ 이용자: {len(residents)}명 생성")

    # 5. 음성기록 + 청부 (각 이용자당 1건만 - 간단하게)
    print("\n✅ 음성기록 + 청부 생성:")

    today = datetime.now()
    caregiver_id = caregivers[0][0]  # 첫 번째 요양사

    total_billing = 0
    record_count = 0

    for idx, resident_id in enumerate(residents):
        # 이용자 등급 조회
        resident = db.query(Resident).filter(Resident.id == resident_id).first()
        care_grade = resident.care_grade
        service_type = "basic_care"  # 모두 기본요양으로 통일

        # 음성기록 생성
        daily_record = DailyRecord(
            caregiver_id=caregiver_id,
            resident_id=resident_id,
            recorded_date=today,
            service_type=service_type,
            morning_care=True,
            meal_intake="full",
            medicine_given=False,
            notes=f"{resident.name} 기본요양"
        )
        db.add(daily_record)
        db.flush()

        # SERVICE_TYPE_AMOUNTS에서 청부액 조회
        service_rates = SERVICE_TYPE_AMOUNTS.get(service_type, SERVICE_TYPE_AMOUNTS["basic_care"])
        amount = service_rates.get(care_grade, service_rates[1])

        # 청부 생성
        billing = BillingRecord(
            caregiver_id=caregiver_id,
            resident_id=resident_id,
            center_id=center_id,
            service_category="재가급여",
            service_type=service_type,
            amount=amount,
            status="draft",
            approval_status="pending",
            recorded_date=today,
            daily_record_id=daily_record.id
        )
        db.add(billing)

        total_billing += amount
        record_count += 1
        print(f"  {idx+1}. {resident.name} (등급{care_grade}): ₩{amount:,}")

    db.commit()

    print("\n" + "=" * 60)
    print("✅ 테스트 데이터 생성 완료!")
    print("=" * 60)
    print(f"\n📊 최종 통계:")
    print(f"  센터: 1개")
    print(f"  센터장: 1명")
    print(f"  요양사: 2명")
    print(f"  이용자: 10명")
    print(f"  음성기록: {record_count}건")
    print(f"  청부기록: {record_count}건")
    print(f"  총 청부액: ₩{total_billing:,}")

    print(f"\n📋 테스트 계정:")
    print(f"  센터장: manager@test.com / test123")
    print(f"  요양사1: caregiver1@test.com / test123")
    print(f"  요양사2: caregiver2@test.com / test123")

    print(f"\n💡 예상 청부액 계산:")
    print(f"  1등급(3명) × ₩78,875 = ₩236,625")
    print(f"  2등급(3명) × ₩67,043 = ₩201,129")
    print(f"  3등급(4명) × ₩55,211 = ₩220,844")
    print(f"  ─────────────────────────────")
    print(f"  합계: ₩658,598")
    print(f"\n✅ 실제 청부액: ₩{total_billing:,}")

    if total_billing == 658598:
        print("✅ 정확히 일치!")
    else:
        print(f"❌ 차이: ₩{abs(total_billing - 658598):,}")

except Exception as e:
    db.rollback()
    print(f"\n❌ 오류: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
