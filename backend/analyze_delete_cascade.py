#!/usr/bin/env python3
"""삭제 시 다른 청부까지 삭제되는 버그 분석"""

from app.database import SessionLocal
from app.models import DailyRecord, BillingRecord
from datetime import date, datetime

db = SessionLocal()

print("\n" + "="*100)
print("🚨 삭제 버그 심화 분석: submitted_to_nhis는 어디로 갔나?")
print("="*100)

# 모든 청부를 조회 (아카이브 포함)
all_billings = db.query(BillingRecord).all()
today = date.today()

print(f"\n📋 모든 청부 (삭제 및 아카이브 포함): {len(all_billings)}건")
for b in all_billings:
    dr_id = str(b.daily_record_id) if b.daily_record_id else "None"
    print(f"  - ID{b.id}: {b.approval_status:20} ₩{b.amount:>10} daily_record_id={dr_id:>4} is_archived={b.is_archived} recorded_date={b.recorded_date.strftime('%Y-%m-%d')}")

# 삭제된 청부 찾기
print(f"\n\n❌ 삭제된 청부 (NULL로 표시될 수 있음):")
# SQLAlchemy에서 삭제된 항목은 쿼리에 나타나지 않으므로 위의 all_billings가 전부입니다

print(f"\n\n🔍 현재 상황 분석:")
print("-" * 100)

submitted = [b for b in all_billings if b.approval_status == 'submitted_to_nhis']
print(f"submitted_to_nhis 청부: {len(submitted)}건")
for b in submitted:
    print(f"  - ID{b.id}: ₩{b.amount:,} daily_record_id={b.daily_record_id}")

if len(submitted) == 0:
    print("  ❌ submitted_to_nhis가 완전히 삭제되었습니다!")
    print("\n원인 추론:")
    print("  1. submitted_to_nhis는 원래 ID3 DailyRecord와 연결되어야 함")
    print("  2. ID3(최영희, 0원짜리)를 삭제할 때 submitted_to_nhis도 함께 삭제됨")
    print("  3. 이것은 여전히 삭제 로직에 버그가 있다는 증거!")

# 역추적: ID3와 관련된 모든 데이터
print(f"\n\n🔎 ID3 DailyRecord와의 관계:")
print("-" * 100)

dr3 = db.query(DailyRecord).filter(DailyRecord.id == 3).first()
if dr3:
    print(f"ID3 DailyRecord: 존재함 - 최영희")
    billings_of_dr3 = db.query(BillingRecord).filter(BillingRecord.daily_record_id == 3).all()
    print(f"  - ID3과 연결된 청부: {len(billings_of_dr3)}건")
else:
    print(f"ID3 DailyRecord: 삭제됨 또는 없음")

# 최영희 이용자 관련 청부 찾기
print(f"\n최영희(Resident 2) 관련 청부:")
yeoyoung_billings = [b for b in all_billings if b.resident_id == 2]  # 최영희는 resident_id 2
print(f"  - 총 {len(yeoyoung_billings)}건")
for b in yeoyoung_billings:
    print(f"    - ID{b.id}: {b.approval_status:20} ₩{b.amount:,} daily_record_id={b.daily_record_id}")

if len(yeoyoung_billings) < 2:
    print(f"\n⚠️ 최영희는 원래 2개 청부(ID3: submitted_to_nhis, ID4: rejected)를 가져야 함!")
    print(f"   현재 {len(yeoyoung_billings)}개만 있습니다!")

db.close()
print("\n" + "="*100 + "\n")
