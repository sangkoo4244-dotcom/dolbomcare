#!/usr/bin/env python3
"""전체 통합 감사 - voice_record 기준으로 모든 화면 검증"""

from app.database import SessionLocal
from app.models import BillingRecord, User, DailyRecord, Resident
from datetime import date, datetime, timedelta

db = SessionLocal()

print("\n" + "="*90)
print("🎯 전체 통합 감사 - voice_record 기준 검증")
print("="*90)

# 요양사 데이터
caregiver = db.query(User).filter(User.role == 'caregiver').first()
caregiver_id = caregiver.id if caregiver else None

# 오늘 데이터
today = date.today()
today_start = datetime.combine(today, datetime.min.time())
today_end = datetime.combine(today, datetime.max.time())

print(f"\n📋 요양사: {caregiver.email if caregiver else 'N/A'}")
print(f"📅 기준 날짜: {today.strftime('%Y-%m-%d')}")

# 1. voice_record 기준 데이터
print("\n\n🎤 1️⃣ voice_record.html 기준 데이터")
print("-" * 90)

# 오늘
today_records = db.query(DailyRecord).filter(
    DailyRecord.caregiver_id == caregiver_id,
    DailyRecord.recorded_date >= today_start,
    DailyRecord.recorded_date <= today_end
).all()

print(f"📅 오늘 (/records/today):")
print(f"  - 음성 기록: {len(today_records)}건")
voice_today_amount = 0
for r in today_records:
    billing = db.query(BillingRecord).filter(BillingRecord.daily_record_id == r.id).first()
    amount = billing.amount if billing else 0
    voice_today_amount += amount
    print(f"    - {r.notes}: ₩{amount:,}")
print(f"  - 청부액 (voice_record): ₩{voice_today_amount:,}")

# 2. caregiver_billing.html 검증
print("\n\n📊 2️⃣ caregiver_billing.html (나의 청부 현황) 검증")
print("-" * 90)

all_billings = db.query(BillingRecord).filter(
    BillingRecord.caregiver_id == caregiver_id,
    BillingRecord.is_archived == False
).all()

active_today = [b for b in all_billings if b.recorded_date >= today_start and b.recorded_date <= today_end]
all_active = all_billings

print(f"오늘 청부: {len(active_today)}건")
for b in active_today:
    print(f"  - {b.approval_status}: ₩{b.amount:,}")

print(f"\n활성 청부 총합: {len(all_active)}건")
print(f"  - pending: {len([b for b in all_active if b.approval_status == 'pending'])}건")
print(f"  - approved: {len([b for b in all_active if b.approval_status == 'approved'])}건")
print(f"  - submitted_to_nhis: {len([b for b in all_active if b.approval_status == 'submitted_to_nhis'])}건")
print(f"  - rejected: {len([b for b in all_active if b.approval_status == 'rejected'])}건")

# 요양사 기준 청부액 (submitted_to_nhis 제외)
caregiver_billing_amount = sum(b.amount for b in all_active if b.approval_status != 'submitted_to_nhis')
print(f"\n청부액 (submitted_to_nhis 제외): ₩{caregiver_billing_amount:,}")

# 3. 데이터 일치성 검증
print("\n\n✅ 3️⃣ 데이터 일치성 검증")
print("-" * 90)

print(f"voice_record (오늘): ₩{voice_today_amount:,}")
print(f"caregiver_billing: ₩{caregiver_billing_amount:,}")

if voice_today_amount == caregiver_billing_amount:
    print("\n✅ ✅ ✅ 완벽 일치! ✅ ✅ ✅")
else:
    print(f"\n❌ 불일치! 차이: ₩{abs(voice_today_amount - caregiver_billing_amount):,}")
    print("\n불일치 원인 분석:")
    print(f"  1. voice_record는 오늘 기록과 연결된 청부만 계산")
    print(f"  2. caregiver_billing은 모든 활성 청부를 계산")
    print(f"  3. caregiver_billing이 submitted_to_nhis를 제외하는지 확인 필요")

# 4. 청부 상세 분석
print("\n\n📋 4️⃣ 청부 상세 분석")
print("-" * 90)

print("오늘 청부 (recorded_date = 오늘):")
for b in active_today:
    daily = db.query(DailyRecord).filter(DailyRecord.id == b.daily_record_id).first() if b.daily_record_id else None
    print(f"  - ID{b.id}: {b.approval_status:20} ₩{b.amount:10} daily_record_id={b.daily_record_id} {daily.notes if daily else 'N/A'}")

print("\n모든 활성 청부:")
total_amount = 0
for b in all_active:
    total_amount += b.amount
    print(f"  - ID{b.id}: {b.approval_status:20} ₩{b.amount:10} recorded_date={b.recorded_date.strftime('%Y-%m-%d')}")
print(f"  합계: ₩{total_amount:,}")

# 5. 최종 검증
print("\n\n🎯 5️⃣ 최종 검증 체크리스트")
print("-" * 90)

checks = [
    ("음성 기록이 있는가", len(today_records) > 0),
    ("음성 기록과 청부가 연결되었는가", len([b for b in active_today if b.daily_record_id]) > 0),
    ("caregiver_billing과 voice_record가 일치하는가", voice_today_amount == caregiver_billing_amount),
    ("모든 활성 청부가 표시되는가", len(all_active) > 0),
]

for check_name, result in checks:
    status = "✅" if result else "❌"
    print(f"{status} {check_name}")

print("\n" + "="*90)
print("✅ 감사 완료")
print("="*90 + "\n")

db.close()
