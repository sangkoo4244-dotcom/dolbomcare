#!/usr/bin/env python3
"""데이터 일치도 검증 스크립트"""

from app.database import SessionLocal
from app.models import DailyRecord, BillingRecord, User, Resident

db = SessionLocal()

caregiver = db.query(User).filter(User.role == 'caregiver').first()
manager = db.query(User).filter(User.role == 'center_manager').first()

print('=' * 60)
print('데이터 일치도 검증')
print('=' * 60)

# 요양사 데이터
print(f'\n[요양사 (ID {caregiver.id})]')
caregiver_records = db.query(DailyRecord).filter(DailyRecord.caregiver_id == caregiver.id).all()
caregiver_billings = db.query(BillingRecord).filter(BillingRecord.caregiver_id == caregiver.id).all()
print(f'  음성 기록: {len(caregiver_records)}건')
print(f'  청부 기록: {len(caregiver_billings)}건')

# 센터장이 보는 데이터 (센터ID 기반)
print(f'\n[센터장 (ID {manager.id}) - 센터ID {manager.center_id}]')
center_records = db.query(DailyRecord).join(
    Resident, DailyRecord.resident_id == Resident.id
).filter(Resident.center_id == manager.center_id).all()
center_billings = db.query(BillingRecord).filter(BillingRecord.center_id == manager.center_id).all()
print(f'  음성 기록: {len(center_records)}건')
print(f'  청부 기록: {len(center_billings)}건')

# 상세 검증
print(f'\n' + '=' * 60)
print(f'음성기록 <-> 청부기록 매핑 검증')
print('=' * 60)

all_match = True
for record in sorted(caregiver_records, key=lambda x: x.id):
    billing = db.query(BillingRecord).filter(BillingRecord.daily_record_id == record.id).first()
    if billing:
        status = f"청부 ID {billing.id} ({billing.approval_status})"
        print(f'✓ 음성기록 ID {record.id}: {status:35s} ← {record.notes}')
    else:
        print(f'✗ 음성기록 ID {record.id}: 청부 없음!')
        all_match = False

print(f'\n' + '=' * 60)
print(f'최종 검증')
print('=' * 60)

caregiver_match = len(caregiver_records) == len(caregiver_billings)
center_match = len(center_records) == len(center_billings)
records_equal = sorted([r.id for r in caregiver_records]) == sorted([r.id for r in center_records])
billings_equal = sorted([b.id for b in caregiver_billings]) == sorted([b.id for b in center_billings])

print(f'\n요양사 음성기록: {len(caregiver_records)}건')
print(f'요양사 청부기록: {len(caregiver_billings)}건')
print(f'  일치: {"YES" if caregiver_match else "NO"}')

print(f'\n센터장 음성기록: {len(center_records)}건')
print(f'센터장 청부기록: {len(center_billings)}건')
print(f'  일치: {"YES" if center_match else "NO"}')

print(f'\n요양사 ↔ 센터장 음성기록 동일: {"YES" if records_equal else "NO"}')
print(f'요양사 ↔ 센터장 청부기록 동일: {"YES" if billings_equal else "NO"}')
print(f'모든 음성기록 청부 연결: {"YES" if all_match else "NO"}')

print(f'\n' + '=' * 60)
if caregiver_match and center_match and records_equal and billings_equal and all_match:
    print('결론: 완벽하게 일치합니다! ✓✓✓')
else:
    print('결론: 불일치가 있습니다.')
print('=' * 60)

db.close()
