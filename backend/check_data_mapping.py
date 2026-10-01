#!/usr/bin/env python3
"""DailyRecord <-> BillingRecord 매핑 정확히 확인"""

from app.database import SessionLocal
from app.models import DailyRecord, BillingRecord, Resident

db = SessionLocal()

print("\n" + "="*100)
print("🔍 DailyRecord <-> BillingRecord <-> Resident 정확한 매핑")
print("="*100)

# 모든 DailyRecord 확인
daily_records = db.query(DailyRecord).all()
print(f"\n📝 모든 DailyRecord: {len(daily_records)}건")

for dr in daily_records:
    resident = db.query(Resident).filter(Resident.id == dr.resident_id).first()
    billing = db.query(BillingRecord).filter(BillingRecord.daily_record_id == dr.id).first()

    print(f"\n  DailyRecord {dr.id}:")
    print(f"    - Resident: {resident.name if resident else 'N/A'} (ID {dr.resident_id})")
    print(f"    - 연결된 청부: ", end="")
    if billing:
        print(f"ID{billing.id} ({billing.approval_status}) ₩{billing.amount:,}")
    else:
        print(f"없음 (0원)")

# 모든 BillingRecord 확인
print(f"\n\n💳 모든 BillingRecord: ")
print("-" * 100)

billings = db.query(BillingRecord).all()
for b in billings:
    resident = db.query(Resident).filter(Resident.id == b.resident_id).first()
    daily = db.query(DailyRecord).filter(DailyRecord.id == b.daily_record_id).first() if b.daily_record_id else None

    daily_resident = db.query(Resident).filter(Resident.id == daily.resident_id).first() if daily else None

    print(f"\nBillingRecord {b.id}: {b.approval_status:20} ₩{b.amount:>10}")
    print(f"  - Resident (billing.resident_id={b.resident_id}): {resident.name if resident else 'N/A'}")
    print(f"  - daily_record_id: {b.daily_record_id}", end="")
    if daily:
        print(f" → Resident {daily.resident_id}: {daily_resident.name if daily_resident else 'N/A'}")
    else:
        print()

    # 체크: BillingRecord의 resident_id와 DailyRecord의 resident_id가 같은가?
    if daily and resident and daily_resident:
        if b.resident_id != daily.resident_id:
            print(f"  ⚠️ 불일치! billing의 resident_id({b.resident_id}) != daily의 resident_id({daily.resident_id})")

db.close()
print("\n" + "="*100 + "\n")
