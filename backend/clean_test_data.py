from app.database import SessionLocal
from app.models import DailyRecord, BillingRecord

db = SessionLocal()

print("=" * 70)
print("🗑️  이전 테스트 데이터 삭제")
print("=" * 70)
print()

# 현재 데이터 확인
print("삭제 전:")
daily_count = db.query(DailyRecord).count()
billing_count = db.query(BillingRecord).count()
print(f"  음성 기록: {daily_count}개")
print(f"  청부 기록: {billing_count}개")
print()

# 요양사 1의 기록 삭제 (caregiver_id=1)
print("요양사 ID=1의 데이터 삭제 중...")
deleted_daily = db.query(DailyRecord).filter(DailyRecord.caregiver_id == 1).delete()
deleted_billing = db.query(BillingRecord).filter(BillingRecord.caregiver_id == 1).delete()
db.commit()

print(f"  ✅ 삭제된 음성 기록: {deleted_daily}개")
print(f"  ✅ 삭제된 청부 기록: {deleted_billing}개")
print()

# 남은 데이터 확인
daily_count = db.query(DailyRecord).count()
billing_count = db.query(BillingRecord).count()
print("삭제 후:")
print(f"  음성 기록: {daily_count}개 (요양사 2만)")
print(f"  청부 기록: {billing_count}개")
print()

# 남은 데이터 상세
print("남은 데이터:")
for r in db.query(DailyRecord).all():
    print(f"  - 음성기록 ID={r.id}, 요양사={r.caregiver_id}, 이용자={r.resident_id}")
for b in db.query(BillingRecord).all():
    print(f"  - 청부 ID={b.id}, 요양사={b.caregiver_id}, 금액=₩{b.amount:,}")

db.close()
print()
print("=" * 70)
print("✅ 정리 완료! 이제 요양사 2의 데이터만 있습니다")
print("=" * 70)
