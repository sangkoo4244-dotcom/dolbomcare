#!/usr/bin/env python3
"""전체 메뉴별 데이터 일치성 종합 감사"""

from app.database import SessionLocal
from app.models import BillingRecord, User, DailyRecord, Resident, Center
from datetime import date, datetime, time, timedelta

db = SessionLocal()

print("\n" + "="*100)
print("🎯 음성기록 최근기록 기준 - 전체 메뉴별 데이터 일치성 종합 감사")
print("="*100)

# 기본 데이터
caregiver = db.query(User).filter(User.role == 'caregiver').first()
manager = db.query(User).filter(User.role == 'center_manager').first()
center = db.query(Center).filter(Center.id == caregiver.center_id).first()
caregiver_id = caregiver.id
manager_id = manager.id
center_id = center.id

today = date.today()
today_start = datetime.combine(today, time.min)
today_end = datetime.combine(today, time.max)
seven_days_ago = today - timedelta(days=7)
seven_days_start = datetime.combine(seven_days_ago, time.min)

print(f"\n📋 기본 정보:")
print(f"  요양사: {caregiver.email} (ID{caregiver_id})")
print(f"  센터장: {manager.email} (ID{manager_id})")
print(f"  센터: {center.name} (ID{center_id})")

# === VOICE_RECORD 기준 데이터 (음성기록 최근기록) ===
print(f"\n\n🎤 1️⃣ voice_record.html (음성기록 - 최근기록 기준)")
print("-" * 100)

voice_records_today = db.query(DailyRecord).filter(
    DailyRecord.caregiver_id == caregiver_id,
    DailyRecord.recorded_date >= today_start,
    DailyRecord.recorded_date <= today_end
).all()

voice_records_7days = db.query(DailyRecord).filter(
    DailyRecord.caregiver_id == caregiver_id,
    DailyRecord.recorded_date >= seven_days_start,
    DailyRecord.recorded_date <= today_end
).all()

voice_records_all = db.query(DailyRecord).filter(
    DailyRecord.caregiver_id == caregiver_id
).all()

# voice_record는 submitted_to_nhis를 제외한 billing_amount 계산
voice_today = 0
voice_7days = 0
voice_all = 0

for r in voice_records_today:
    billing = db.query(BillingRecord).filter(BillingRecord.daily_record_id == r.id).first()
    if billing and billing.approval_status != 'submitted_to_nhis':
        voice_today += billing.amount

for r in voice_records_7days:
    billing = db.query(BillingRecord).filter(BillingRecord.daily_record_id == r.id).first()
    if billing and billing.approval_status != 'submitted_to_nhis':
        voice_7days += billing.amount

for r in voice_records_all:
    billing = db.query(BillingRecord).filter(BillingRecord.daily_record_id == r.id).first()
    if billing and billing.approval_status != 'submitted_to_nhis':
        voice_all += billing.amount

print(f"  오늘: {len(voice_records_today)}건 → ₩{voice_today:,}")
print(f"  7일: {len(voice_records_7days)}건 → ₩{voice_7days:,}")
print(f"  전체: {len(voice_records_all)}건 → ₩{voice_all:,}")

# === CAREGIVER_BILLING 메뉴 ===
print(f"\n\n💰 2️⃣ caregiver_billing.html (나의 청부 현황)")
print("-" * 100)

cb_billings = db.query(BillingRecord).filter(
    BillingRecord.caregiver_id == caregiver_id,
    BillingRecord.is_archived == False
).all()

cb_total = sum(b.amount for b in cb_billings if b.approval_status != 'submitted_to_nhis')
print(f"  활성 청부: {len(cb_billings)}건")
print(f"  submitted_to_nhis 제외 합계: ₩{cb_total:,}")

# === BILLING_MANAGEMENT 메뉴 ===
print(f"\n\n📋 3️⃣ billing_management.html (청부 관리 - 센터장)")
print("-" * 100)

bm_billings = db.query(BillingRecord).filter(
    BillingRecord.center_id == center_id,
    BillingRecord.is_archived == False
).all()

print(f"  센터 전체 활성 청부: {len(bm_billings)}건")
for status in ['pending', 'approved', 'submitted_to_nhis', 'rejected']:
    count = len([b for b in bm_billings if b.approval_status == status])
    total = sum(b.amount for b in bm_billings if b.approval_status == status)
    if count > 0:
        print(f"    - {status}: {count}건 ₩{total:,}")

# === 종합 비교 ===
print(f"\n\n✅ 4️⃣ 전체 메뉴 데이터 일치성 검증")
print("-" * 100)

print(f"\n📊 오늘 (today):")
print(f"  voice_record (최근기록): ₩{voice_today:,}")
print(f"  caregiver_billing: ₩{cb_total:,} (같은 기준)")
print(f"  → 일치도: {'✅ 완벽' if voice_today == cb_total else '❌ 불일치'}")

print(f"\n📊 7일 (recent):")
print(f"  voice_record (7일 기준): ₩{voice_7days:,}")
print(f"  → 예상: caregiver_billing과 같아야 함 (전체 활성 청부, submitted_to_nhis 제외)")

print(f"\n📊 전체 (all):")
print(f"  voice_record (전체 기준): ₩{voice_all:,}")
print(f"  → 예상: caregiver_billing과 같아야 함 (전체 활성 청부, submitted_to_nhis 제외)")

# === 연결성 검증 ===
print(f"\n\n🔗 5️⃣ DailyRecord ↔ BillingRecord 연결성 검증")
print("-" * 100)

unlinked_daily = [r for r in voice_records_all if not db.query(BillingRecord).filter(BillingRecord.daily_record_id == r.id).first()]
unlinked_billing = db.query(BillingRecord).filter(
    BillingRecord.caregiver_id == caregiver_id,
    BillingRecord.is_archived == False,
    BillingRecord.daily_record_id == None
).all()

print(f"  DailyRecord (연결 안 됨): {len(unlinked_daily)}건")
for r in unlinked_daily:
    print(f"    - ID{r.id}: {r.notes}")

print(f"\n  BillingRecord (연결 안 됨): {len(unlinked_billing)}건")
for b in unlinked_billing:
    print(f"    - ID{b.id}: {b.approval_status} ₩{b.amount:,}")

# === 최종 체크리스트 ===
print(f"\n\n📋 6️⃣ 최종 체크리스트")
print("-" * 100)

checks = [
    ("voice_record 오늘 데이터 있음", len(voice_records_today) > 0),
    ("voice_record 7일 데이터 있음", len(voice_records_7days) > 0),
    ("voice_record 전체 데이터 있음", len(voice_records_all) > 0),
    ("caregiver_billing 데이터 있음", len(cb_billings) > 0),
    ("billing_management 데이터 있음", len(bm_billings) > 0),
    ("오늘 voice_record와 caregiver_billing 일치", voice_today == cb_total),
    ("모든 DailyRecord가 연결됨", len(unlinked_daily) == 0),
    ("모든 BillingRecord가 연결됨", len(unlinked_billing) == 0),
]

for check_name, result in checks:
    status = "✅" if result else "❌"
    print(f"{status} {check_name}")

db.close()
print("\n" + "="*100 + "\n")
