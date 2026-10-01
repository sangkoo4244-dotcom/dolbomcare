#!/usr/bin/env python3
"""submitted_to_nhis 필터링 테스트"""

from app.database import SessionLocal
from app.models import BillingRecord, User, DailyRecord
from datetime import date, datetime, time

db = SessionLocal()

today = date.today()
today_start = datetime.combine(today, time.min)
today_end = datetime.combine(today, time.max)
caregiver_id = 2

print("\n" + "="*80)
print("🔍 submitted_to_nhis 필터링 테스트")
print("="*80)

# Caregiver 확인
caregiver = db.query(User).filter(User.id == caregiver_id).first()
print(f"\n👤 요양사: {caregiver.email}")
print(f"   role: {caregiver.role}")

# Billings 조회
billings = db.query(BillingRecord).filter(
    BillingRecord.recorded_date >= today_start,
    BillingRecord.recorded_date <= today_end,
    BillingRecord.caregiver_id == caregiver_id
).all()

print(f"\n💳 오늘 청부: {len(billings)}건")
for b in billings:
    daily = db.query(DailyRecord).filter(DailyRecord.id == b.daily_record_id).first() if b.daily_record_id else None
    daily_info = f"ID{b.daily_record_id}" if b.daily_record_id else "None"
    print(f"  - ID{b.id}: {b.approval_status:20} ₩{b.amount:>10} daily_record_id={daily_info}")

# 필터링 테스트
print(f"\n🧪 필터링 로직 테스트:")

# 1. daily_record_id가 있는 청부만
connected = sum(b.amount for b in billings if b.daily_record_id and b.amount)
print(f"  1. daily_record_id가 있는 청부: ₩{connected:,}")

# 2. submitted_to_nhis 제외 (모든 청부)
excluded = sum(b.amount for b in billings if b.approval_status != 'submitted_to_nhis')
print(f"  2. submitted_to_nhis 제외 (모두): ₩{excluded:,}")

# 3. 둘 다 적용
both = sum(b.amount for b in billings if b.daily_record_id and b.approval_status != 'submitted_to_nhis' and b.amount)
print(f"  3. 둘 다 (connected + excluded): ₩{both:,}")

# 4. IF 로직 시뮬레이션
billing_total = sum(b.amount for b in billings if b.daily_record_id and b.amount)
print(f"\n📊 현재 /records/today 로직:")
print(f"  billing_total (초기): ₩{billing_total:,}")

if caregiver and caregiver.role == 'caregiver':
    billing_total = sum(b.amount for b in billings if b.approval_status != 'submitted_to_nhis')
    print(f"  billing_total (제외 후): ₩{billing_total:,} ✅")
else:
    print(f"  조건 미충족 (role이 {caregiver.role})")

db.close()
print("\n" + "="*80 + "\n")
