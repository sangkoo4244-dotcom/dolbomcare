#!/usr/bin/env python3
"""삭제 버그 테스트"""

from app.database import SessionLocal
from app.models import DailyRecord, BillingRecord

db = SessionLocal()

print("\n" + "="*80)
print("🔍 삭제 버그 시뮬레이션 테스트")
print("="*80)

# 현재 데이터
today_records = db.query(DailyRecord).all()
today_billings = db.query(BillingRecord).filter(BillingRecord.is_archived == False).all()

print(f"\n📋 현재 DailyRecord: {len(today_records)}건")
print(f"💳 현재 활성 BillingRecord: {len(today_billings)}건")

for r in today_records[:5]:
    print(f"  - DailyRecord {r.id}: 이용자{r.resident_id}, 요양사{r.caregiver_id}, {r.recorded_date.strftime('%Y-%m-%d')}")

for b in today_billings[:5]:
    print(f"  - BillingRecord {b.id}: {b.approval_status}, daily_record_id={b.daily_record_id}, ₩{b.amount:,}")

# 삭제 전 청부액
voice_before = sum(b.amount for b in today_billings if b.approval_status != 'submitted_to_nhis')
print(f"\n💰 삭제 전 청부액: ₩{voice_before:,}")

# === 버그 시뮬레이션 ===
print(f"\n\n🧪 시나리오: DailyRecord 2 (이용자 1 #2) 삭제")
print("-" * 80)

record_to_delete = db.query(DailyRecord).filter(DailyRecord.id == 2).first()
if record_to_delete:
    print(f"삭제할 DailyRecord: {record_to_delete.id}")
    print(f"  - recorded_date: {record_to_delete.recorded_date.strftime('%Y-%m-%d')}")
    print(f"  - caregiver_id: {record_to_delete.caregiver_id}")
    print(f"  - resident_id: {record_to_delete.resident_id}")

    # 구버그: 같은 날짜/요양사/이용자의 모든 청부
    old_query_billings = db.query(BillingRecord).filter(
        BillingRecord.recorded_date == record_to_delete.recorded_date,
        BillingRecord.caregiver_id == record_to_delete.caregiver_id,
        BillingRecord.resident_id == record_to_delete.resident_id
    ).all()

    print(f"\n❌ [구버그] 같은 날짜/요양사/이용자의 모든 청부: {len(old_query_billings)}건")
    for b in old_query_billings:
        print(f"    - 삭제될 청부: {b.id} ({b.approval_status}) ₩{b.amount:,} daily_record_id={b.daily_record_id}")

    old_deletion_amount = sum(b.amount for b in old_query_billings)
    print(f"    - 함께 삭제될 청부액: ₩{old_deletion_amount:,}")

    # 신규버그 수정: daily_record_id 기반
    new_query_billings = db.query(BillingRecord).filter(
        BillingRecord.daily_record_id == record_to_delete.id
    ).all()

    print(f"\n✅ [수정됨] 이 DailyRecord와 연결된 청부만: {len(new_query_billings)}건")
    for b in new_query_billings:
        print(f"    - 삭제될 청부: {b.id} ({b.approval_status}) ₩{b.amount:,} daily_record_id={b.daily_record_id}")

    new_deletion_amount = sum(b.amount for b in new_query_billings)
    print(f"    - 함께 삭제될 청부액: ₩{new_deletion_amount:,}")

    # 결과 비교
    print(f"\n\n📊 삭제 후 청부액 예상:")
    print(f"  - 구버그 결과: ₩{voice_before - old_deletion_amount:,} ❌ (잘못됨)")
    print(f"  - 수정됨 결과: ₩{voice_before - new_deletion_amount:,} ✅ (올바름)")

    if old_deletion_amount != new_deletion_amount:
        print(f"\n🎯 차이: ₩{abs(old_deletion_amount - new_deletion_amount):,}")
        print(f"   (구버그가 추가로 ₩{abs(old_deletion_amount - new_deletion_amount):,} 삭제함)")

db.close()
print("\n" + "="*80 + "\n")
