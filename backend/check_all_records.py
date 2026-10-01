#!/usr/bin/env python3
"""모든 기록 확인"""

from app.database import SessionLocal
from app.models import DailyRecord, BillingRecord

db = SessionLocal()

print('\n' + '='*80)
print('📋 데이터베이스 상태 확인')
print('='*80)

print('\n📝 모든 DailyRecord:')
records = db.query(DailyRecord).all()
for r in records:
    print(f'  ID{r.id}: {r.recorded_date.strftime("%Y-%m-%d")} 이용자{r.resident_id}')

print(f'\n💳 모든 활성 BillingRecord (is_archived=False):')
billings = db.query(BillingRecord).filter(BillingRecord.is_archived == False).all()
for b in billings:
    print(f'  ID{b.id}: {b.approval_status:20} ₩{b.amount:>10} {b.recorded_date.strftime("%Y-%m-%d")}')

print(f'\n📊 집계:')
all_total = sum(b.amount for b in billings)
submitted = sum(b.amount for b in billings if b.approval_status == 'submitted_to_nhis')
without_submitted = all_total - submitted

print(f'  모든 청부: ₩{all_total:,}')
print(f'  submitted_to_nhis: ₩{submitted:,}')
print(f'  제외 후: ₩{without_submitted:,}')

print(f'\n⚠️ API가 반환한 값: 1,590,000')
print(f'✅ 예상 값: ₩{without_submitted:,}')

db.close()
print('\n' + '='*80 + '\n')
