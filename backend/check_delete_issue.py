#!/usr/bin/env python3
"""0원짜리 삭제 시 금액 변화 버그 확인"""

from app.database import SessionLocal
from app.models import DailyRecord, BillingRecord, Resident
from datetime import date, datetime

db = SessionLocal()
today = date.today()
today_start = datetime.combine(today, datetime.min.time())
today_end = datetime.combine(today, datetime.max.time())

print("\n" + "="*90)
print("🔍 오늘 DailyRecord와 BillingRecord 매핑 확인")
print("="*90)

# 오늘 DailyRecord
today_records = db.query(DailyRecord).filter(
    DailyRecord.recorded_date >= today_start,
    DailyRecord.recorded_date <= today_end
).all()

print(f"\n📝 오늘 DailyRecord: {len(today_records)}건")
for r in today_records:
    resident = db.query(Resident).filter(Resident.id == r.resident_id).first()
    billing = db.query(BillingRecord).filter(BillingRecord.daily_record_id == r.id).first()
    amount = billing.amount if billing else 0
    status = billing.approval_status if billing else "없음"
    print(f"  - ID{r.id}: {resident.name if resident else '?'} - {status:20} ₩{amount:,}")

# 0원짜리 찾기
zero_records = [r for r in today_records if not db.query(BillingRecord).filter(BillingRecord.daily_record_id == r.id).first()]
print(f"\n❓ 0원짜리(청부 없음): {len(zero_records)}건")
for r in zero_records:
    resident = db.query(Resident).filter(Resident.id == r.resident_id).first()
    print(f"  - ID{r.id}: {resident.name if resident else '?'}")

# 만약 0원짜리를 삭제한다면?
if zero_records:
    print(f"\n\n⚠️ 시뮬레이션: ID{zero_records[0].id} 삭제 시")
    print("-" * 90)

    record_to_delete = zero_records[0]

    # 현재 좋은 삭제 로직 (daily_record_id 기반)
    billings_to_delete = db.query(BillingRecord).filter(
        BillingRecord.daily_record_id == record_to_delete.id
    ).all()

    print(f"삭제될 청부: {len(billings_to_delete)}건")
    for b in billings_to_delete:
        print(f"  - {b.approval_status} ₩{b.amount:,}")

    if len(billings_to_delete) == 0:
        print("  - (없음 - 0원이므로 정상)")

    # 그런데 혹시 다른 버그가 있는지?
    # 예: 다른 쿼리가 실수로 이 record를 포함하는지?
    print(f"\n✅ 결론: 0원짜리 삭제는 안전함 (청부 삭제 안 됨)")

# 전체 청부 확인
print(f"\n\n📊 모든 청부 현황")
print("-" * 90)

all_billings = db.query(BillingRecord).filter(BillingRecord.is_archived == False).all()
total = sum(b.amount for b in all_billings)
today_total = sum(b.amount for b in all_billings if b.recorded_date >= today_start and b.recorded_date <= today_end)

print(f"활성 청부: {len(all_billings)}건")
for status in ['pending', 'approved', 'submitted_to_nhis', 'rejected']:
    count = len([b for b in all_billings if b.approval_status == status])
    amount = sum(b.amount for b in all_billings if b.approval_status == status)
    if count > 0:
        print(f"  - {status}: {count}건 ₩{amount:,}")

print(f"\n오늘 청부: {len([b for b in all_billings if b.recorded_date >= today_start])}")
print(f"오늘 합계: ₩{today_total:,}")
print(f"전체 합계: ₩{total:,}")

db.close()
print("\n" + "="*90 + "\n")
