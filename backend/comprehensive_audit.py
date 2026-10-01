#!/usr/bin/env python3
"""전체 데이터 감사 - 모든 화면의 수치가 일치하는지 검증"""

from app.database import SessionLocal
from app.models import BillingRecord, User, DailyRecord, Resident
from datetime import date, datetime, timedelta

db = SessionLocal()

print("\n" + "="*80)
print("🔍 전체 데이터 감사 보고서")
print("="*80)

# 1. 기본 데이터 현황
print("\n📊 1️⃣ 데이터베이스 현황")
print("-" * 80)

total_billings = db.query(BillingRecord).all()
total_daily_records = db.query(DailyRecord).all()
total_users = db.query(User).all()
total_residents = db.query(Resident).all()

print(f"사용자: {len(total_users)}명")
print(f"이용자: {len(total_residents)}명")
print(f"음성 기록(DailyRecord): {len(total_daily_records)}건")
print(f"청부 기록(BillingRecord): {len(total_billings)}건")

# 2. 오늘 데이터
print("\n\n📅 2️⃣ 오늘 데이터 검증")
print("-" * 80)

today = date.today()
today_start = datetime.combine(today, datetime.min.time())
today_end = datetime.combine(today, datetime.max.time())

today_daily_records = [r for r in total_daily_records
                       if r.recorded_date >= today_start and r.recorded_date <= today_end]
today_billings = [b for b in total_billings
                  if b.recorded_date >= today_start and b.recorded_date <= today_end]

print(f"오늘 음성 기록: {len(today_daily_records)}건")
for r in today_daily_records:
    print(f"  - ID{r.id}: 이용자{r.resident_id}, 요양사{r.caregiver_id}")

print(f"\n오늘 청부: {len(today_billings)}건")
for b in today_billings:
    print(f"  - ID{b.id}: 이용자{b.resident_id}, 요양사{b.caregiver_id}, {b.approval_status}, ₩{b.amount}")

# 3. DailyRecord와 BillingRecord 연결 검증
print("\n\n🔗 3️⃣ DailyRecord ↔ BillingRecord 연결 검증")
print("-" * 80)

linked_billings = [b for b in total_billings if b.daily_record_id]
unlinked_billings = [b for b in total_billings if not b.daily_record_id]

print(f"연결된 청부: {len(linked_billings)}건")
for b in linked_billings:
    daily = next((r for r in total_daily_records if r.id == b.daily_record_id), None)
    print(f"  - 청부ID{b.id} → DailyID{b.daily_record_id} ({daily.resident_id if daily else '없음'})")

print(f"\n미연결 청부: {len(unlinked_billings)}건")
for b in unlinked_billings:
    print(f"  - 청부ID{b.id}: {b.approval_status}, ₩{b.amount}, recorded_date={b.recorded_date.strftime('%Y-%m-%d')}")

# 4. 요양사별 데이터
print("\n\n👨‍⚕️ 4️⃣ 요양사별 청부 현황")
print("-" * 80)

caregiver = next((u for u in total_users if u.role == 'caregiver'), None)
if caregiver:
    caregiver_billings = [b for b in total_billings if b.caregiver_id == caregiver.id]
    active_billings = [b for b in caregiver_billings if not b.is_archived]

    print(f"요양사(ID{caregiver.id}): {caregiver.email}")
    print(f"  - 전체 청부: {len(caregiver_billings)}건")
    print(f"  - 활성 청부: {len(active_billings)}건")
    print(f"  - 아카이브: {len(caregiver_billings) - len(active_billings)}건")

    # 상태별
    for status in ['pending', 'approved', 'submitted_to_nhis', 'rejected', 'reimbursed']:
        count = len([b for b in active_billings if b.approval_status == status])
        if count > 0:
            total = sum(b.amount for b in active_billings if b.approval_status == status)
            print(f"  - {status}: {count}건, ₩{total:,}")

# 5. voice_record 기준 검증
print("\n\n🎤 5️⃣ voice_record.html 기준 검증")
print("-" * 80)

caregiver_id = caregiver.id if caregiver else None

# 오늘
today_records = db.query(DailyRecord).filter(
    DailyRecord.caregiver_id == caregiver_id,
    DailyRecord.recorded_date >= today_start,
    DailyRecord.recorded_date <= today_end
).all()

today_billing_ids = [b.id for b in total_billings
                     if b.recorded_date >= today_start and b.recorded_date <= today_end
                     and b.caregiver_id == caregiver_id]
today_total = sum(b.amount for b in total_billings
                  if b.recorded_date >= today_start and b.recorded_date <= today_end
                  and b.caregiver_id == caregiver_id)

print(f"📅 오늘 (/records/today):")
print(f"  - 기록: {len(today_records)}건")
print(f"  - 청부액 (total_billing_amount): ₩{today_total:,}")
print(f"  - 기록별 청부: ", end="")
for r in today_records:
    billing = next((b for b in total_billings if b.daily_record_id == r.id), None)
    amount = billing.amount if billing else 0
    print(f"ID{r.id}=₩{amount:,} ", end="")
print()

# 7일
seven_days_ago = today - timedelta(days=7)
seven_days_records = db.query(DailyRecord).filter(
    DailyRecord.caregiver_id == caregiver_id,
    DailyRecord.recorded_date >= datetime.combine(seven_days_ago, datetime.min.time()),
    DailyRecord.recorded_date <= today_end
).all()

seven_days_total = sum(b.amount for b in total_billings
                       if b.recorded_date >= datetime.combine(seven_days_ago, datetime.min.time())
                       and b.recorded_date <= today_end
                       and b.caregiver_id == caregiver_id
                       and b.daily_record_id)

print(f"\n📅 지난 7일 (/records/recent):")
print(f"  - 기록: {len(seven_days_records)}건")
print(f"  - 연결된 청부액: ₩{seven_days_total:,}")

# 전체
all_records = db.query(DailyRecord).filter(
    DailyRecord.caregiver_id == caregiver_id
).all()

all_total = sum(b.amount for b in total_billings
                if b.caregiver_id == caregiver_id and b.daily_record_id)

print(f"\n📅 전체 (/records/all):")
print(f"  - 기록: {len(all_records)}건")
print(f"  - 연결된 청부액: ₩{all_total:,}")

# 6. Dashboard 검증
print("\n\n📊 6️⃣ Dashboard 검증")
print("-" * 80)

dashboard_active = [b for b in caregiver_billings if not b.is_archived]
dashboard_excluded = [b for b in dashboard_active if b.approval_status == 'submitted_to_nhis']
dashboard_total = sum(b.amount for b in dashboard_active if b.approval_status != 'submitted_to_nhis')

print(f"대시보드 (요양사 기준):")
print(f"  - 활성 청부: {len(dashboard_active)}건")
print(f"  - 제외 (submitted_to_nhis): {len(dashboard_excluded)}건")
print(f"  - 표시되는 청부액: ₩{dashboard_total:,}")

# 7. 모든 화면의 청부액 비교
print("\n\n⚠️ 7️⃣ 모든 화면 청부액 비교")
print("-" * 80)

print(f"voice_record (오늘): ₩{today_total:,}")
print(f"voice_record (7일): ₩{seven_days_total:,}")
print(f"voice_record (전체): ₩{all_total:,}")
print(f"Dashboard: ₩{dashboard_total:,}")

# 8. 검증 체크리스트
print("\n\n✅ 8️⃣ 검증 체크리스트")
print("-" * 80)

checks = [
    ("오늘 기록이 있는가", len(today_records) > 0),
    ("오늘 청부가 있는가", len(today_billings) > 0),
    ("오늘 기록과 청부가 연결되었는가", len(linked_billings) > 0),
    ("voice_record 오늘과 Dashboard가 같은가", today_total == dashboard_total),
    ("DailyRecord 전체가 음성 기록 페이지에 표시되는가", len(all_records) > 0),
]

for check_name, result in checks:
    status = "✅" if result else "❌"
    print(f"{status} {check_name}")

print("\n" + "="*80)
print("✅ 감사 완료")
print("="*80 + "\n")

db.close()
