#!/usr/bin/env python3
"""최종 검증 - 모든 메뉴의 데이터 일치 확인"""

from app.database import SessionLocal
from app.models import User, DailyRecord, BillingRecord, Center
from datetime import date, datetime, time

db = SessionLocal()

print("\n" + "="*100)
print("🎯 최종 검증 - 모든 메뉴의 청부 데이터 일치 확인")
print("="*100)

# 기본 데이터
caregiver = db.query(User).filter(User.role == 'caregiver').first()
manager = db.query(User).filter(User.role == 'center_manager').first()
caregiver_id = caregiver.id if caregiver else None
manager_id = manager.id if manager else None
center_id = caregiver.center_id if caregiver else None

print(f"\n👤 요양사: {caregiver.email}")
print(f"👨‍💼 센터장: {manager.email}")
center = db.query(Center).filter(Center.id == center_id).first()
print(f"🏢 센터: {center.name if center else 'N/A'}")

# 오늘 데이터
today = date.today()
today_start = datetime.combine(today, time.min)
today_end = datetime.combine(today, time.max)

# === 1. voice_record.html (최근기록) ===
print(f"\n\n📱 1️⃣ voice_record.html (최근기록) /records/today")
print("-" * 100)

today_records = db.query(DailyRecord).filter(
    DailyRecord.caregiver_id == caregiver_id,
    DailyRecord.recorded_date >= today_start,
    DailyRecord.recorded_date <= today_end
).all()

billing_ids = [r.id for r in today_records]
today_billings = db.query(BillingRecord).filter(
    BillingRecord.daily_record_id.in_(billing_ids),
    BillingRecord.is_archived == False
).all()

voice_amount = sum(b.amount for b in today_billings if b.approval_status != 'submitted_to_nhis')

print(f"📝 음성 기록: {len(today_records)}건")
print(f"💳 청부: {len(today_billings)}건")
print(f"📊 표시 금액: ₩{voice_amount:,} (submitted_to_nhis 제외)")

# === 2. caregiver_billing.html (나의 청부 현황) ===
print(f"\n\n💰 2️⃣ caregiver_billing.html (나의 청부 현황) /billing")
print("-" * 100)

all_billings = db.query(BillingRecord).filter(
    BillingRecord.caregiver_id == caregiver_id,
    BillingRecord.is_archived == False
).all()

cb_amount = sum(b.amount for b in all_billings if b.approval_status != 'submitted_to_nhis')

print(f"💳 활성 청부: {len(all_billings)}건")
for status in ['pending', 'approved', 'rejected']:
    count = len([b for b in all_billings if b.approval_status == status])
    total = sum(b.amount for b in all_billings if b.approval_status == status)
    if count > 0:
        print(f"  - {status}: {count}건 ₩{total:,}")

submitted = [b for b in all_billings if b.approval_status == 'submitted_to_nhis']
if submitted:
    print(f"  - submitted_to_nhis: {len(submitted)}건 ₩{sum(b.amount for b in submitted):,} (제외)")

print(f"📊 표시 금액: ₩{cb_amount:,} (submitted_to_nhis 제외)")

# === 3. billing_management.html (청부 관리) - 센터장 ===
print(f"\n\n📋 3️⃣ billing_management.html (청부 관리) /billing/?center_id={center_id}")
print("-" * 100)

center_all_billings = db.query(BillingRecord).filter(
    BillingRecord.center_id == center_id,
    BillingRecord.is_archived == False
).all()

print(f"센터 전체 청부: {len(center_all_billings)}건")
for status in ['pending', 'approved', 'submitted_to_nhis', 'rejected']:
    count = len([b for b in center_all_billings if b.approval_status == status])
    total = sum(b.amount for b in center_all_billings if b.approval_status == status)
    if count > 0:
        print(f"  - {status}: {count}건 ₩{total:,}")

# === 최종 비교 ===
print(f"\n\n✅ 최종 비교")
print("-" * 100)

print(f"voice_record (오늘):        ₩{voice_amount:,}")
print(f"caregiver_billing:          ₩{cb_amount:,}")

if voice_amount == cb_amount:
    print(f"\n✅ ✅ ✅ 모두 일치! ✅ ✅ ✅")
else:
    print(f"\n❌ 불일치! 차이: ₩{abs(voice_amount - cb_amount):,}")

# === 상태별 분석 ===
print(f"\n\n📊 상태별 분석")
print("-" * 100)

print(f"활성 청부 (is_archived=False): {len(all_billings)}건")
print(f"  - pending + approved + rejected: {sum(b.amount for b in all_billings if b.approval_status in ['pending', 'approved', 'rejected']):,}")
print(f"  - submitted_to_nhis: {sum(b.amount for b in all_billings if b.approval_status == 'submitted_to_nhis'):,} (제외됨)")

archived = db.query(BillingRecord).filter(
    BillingRecord.caregiver_id == caregiver_id,
    BillingRecord.is_archived == True
).all()

print(f"\n아카이브 청부 (is_archived=True): {len(archived)}건")
for b in archived:
    print(f"  - {b.approval_status}: ₩{b.amount:,} recorded_date={b.recorded_date.strftime('%Y-%m-%d')}")

print("\n" + "="*100)
print("✅ 최종 검증 완료")
print("="*100 + "\n")

db.close()
