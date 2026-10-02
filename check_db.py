import sys
sys.path.insert(0, 'backend')

from backend.app.database import SessionLocal
from backend.app.models import BillingRecord, VoiceRecord

db = SessionLocal()

print("=" * 60)
print("📊 데이터베이스 확인")
print("=" * 60)
print()

# 음성 기록 확인
print("🎤 음성 기록:")
records = db.query(VoiceRecord).order_by(VoiceRecord.id.desc()).limit(5).all()
print(f"총 음성 기록: {db.query(VoiceRecord).count()}개")
for record in records:
    print(f"  - ID: {record.id}, 요양사: {record.caregiver_id}, 이용자: {record.resident_id}, 생성: {record.created_at}")
print()

# 청부 기록 확인
print("💳 청부 기록:")
billings = db.query(BillingRecord).order_by(BillingRecord.id.desc()).limit(5).all()
print(f"총 청부 기록: {db.query(BillingRecord).count()}개")
for billing in billings:
    print(f"  - ID: {billing.id}, 요양사: {billing.caregiver_id}, 이용자: {billing.resident_id}, 금액: ₩{billing.amount:,}, 상태: {billing.status}, 생성: {billing.created_at}")
print()

# 최신 음성 기록과 청부 기록 비교
print("🔍 최신 레코드 상세:")
latest_voice = db.query(VoiceRecord).order_by(VoiceRecord.id.desc()).first()
latest_billing = db.query(BillingRecord).order_by(BillingRecord.id.desc()).first()

if latest_voice:
    print(f"최신 음성 기록 ID: {latest_voice.id}")
if latest_billing:
    print(f"최신 청부 기록 ID: {latest_billing.id}")
    print(f"  - 요양사 ID: {latest_billing.caregiver_id}")
    print(f"  - 이용자 ID: {latest_billing.resident_id}")
    print(f"  - 센터 ID: {latest_billing.center_id}")
    print(f"  - 금액: ₩{latest_billing.amount:,}")
    print(f"  - 상태: {latest_billing.status}")
    print(f"  - 생성일: {latest_billing.created_at}")
print()

db.close()
