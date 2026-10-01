#!/usr/bin/env python3
"""API 응답 직접 시뮬레이션"""

from app.database import SessionLocal
from app.models import BillingRecord, User, DailyRecord
from datetime import date, datetime, time

db = SessionLocal()

# voice_record.html에서 사용하는 caregiver_id 확인
# 콘솔 로그를 보면 요양사가 로그인한 것으로 보임

print("\n" + "="*80)
print("📱 /records/today API 응답 시뮬레이션")
print("="*80)

# 모든 요양사 확인
caregivers = db.query(User).filter(User.role == 'caregiver').all()
print(f"\n모든 요양사:")
for c in caregivers:
    print(f"  - ID{c.id}: {c.email}")

# 각 요양사별로 시뮬레이션
for caregiver in caregivers:
    caregiver_id = caregiver.id
    today = date.today()
    today_start = datetime.combine(today, time.min)
    today_end = datetime.combine(today, time.max)

    print(f"\n\n👤 요양사 ID{caregiver_id} ({caregiver.email}):")

    # 오늘 청부
    billings = db.query(BillingRecord).filter(
        BillingRecord.recorded_date >= today_start,
        BillingRecord.recorded_date <= today_end,
        BillingRecord.caregiver_id == caregiver_id
    ).all()

    print(f"  청부: {len(billings)}건")

    if billings:
        # 초기 합계
        billing_total = sum(b.amount for b in billings if b.daily_record_id and b.amount)
        print(f"  initial billing_total: ₩{billing_total:,}")

        # 필터링
        if caregiver.role == 'caregiver':
            billing_total_filtered = sum(b.amount for b in billings if b.approval_status != 'submitted_to_nhis')
            print(f"  filtered billing_total: ₩{billing_total_filtered:,}")
            print(f"  ✅ 차이: ₩{billing_total - billing_total_filtered:,}")

db.close()
print("\n" + "="*80 + "\n")
