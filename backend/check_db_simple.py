from app.database import SessionLocal
from app.models import BillingRecord, VoiceRecord

db = SessionLocal()

print("=" * 60)
print("📊 데이터베이스 확인")
print("=" * 60)
print()

# 음성 기록 확인
print("🎤 음성 기록:")
records = db.query(VoiceRecord).order_by(VoiceRecord.id.desc()).limit(5).all()
total_voice = db.query(VoiceRecord).count()
print(f"총 음성 기록: {total_voice}개")
for record in records:
    print(f"  - ID: {record.id}, 요양사: {record.caregiver_id}, 이용자: {record.resident_id}")
print()

# 청부 기록 확인
print("💳 청부 기록:")
billings = db.query(BillingRecord).order_by(BillingRecord.id.desc()).limit(5).all()
total_billing = db.query(BillingRecord).count()
print(f"총 청부 기록: {total_billing}개")
for billing in billings:
    print(f"  - ID: {billing.id}, 요양사: {billing.caregiver_id}, 금액: ₩{billing.amount:,}, 상태: {billing.status}")
print()

db.close()
