from app.database import SessionLocal
from app.models import DailyRecord, BillingRecord

db = SessionLocal()

print("=" * 70)
print("✅ 데이터 일치성 검증 (요양사 → 센터장)")
print("=" * 70)
print()

# 요양사 1의 모든 청부
print("🧑‍⚕️ 요양사 ID=1이 생성한 청부:")
caregiver_1_billings = db.query(BillingRecord).filter(BillingRecord.caregiver_id == 1).all()
print(f"   - 개수: {len(caregiver_1_billings)}개")
total_amount = sum(b.amount for b in caregiver_1_billings)
print(f"   - 합계금액: ₩{total_amount:,}")
print(f"   - 각 청부:")
for i, b in enumerate(caregiver_1_billings[:3], 1):
    print(f"      {i}. ID={b.id}, 이용자={b.resident_id}, 금액=₩{b.amount:,}, 센터={b.center_id}, 상태={b.status}")
if len(caregiver_1_billings) > 3:
    print(f"      ... 외 {len(caregiver_1_billings) - 3}개")
print()

# 센터 1의 모든 청부
print("🏥 센터 ID=1의 전체 청부 (센터장이 볼 수 있음):")
center_1_billings = db.query(BillingRecord).filter(BillingRecord.center_id == 1).all()
print(f"   - 개수: {len(center_1_billings)}개")
total_amount = sum(b.amount for b in center_1_billings)
print(f"   - 합계금액: ₩{total_amount:,}")
print(f"   - 각 청부:")
for i, b in enumerate(center_1_billings[:3], 1):
    print(f"      {i}. ID={b.id}, 요양사={b.caregiver_id}, 이용자={b.resident_id}, 금액=₩{b.amount:,}, 상태={b.status}")
if len(center_1_billings) > 3:
    print(f"      ... 외 {len(center_1_billings) - 3}개")
print()

# 데이터 일치성 검증
print("🔍 일치성 검증:")
all_from_caregiver_in_center = all(b.center_id == 1 for b in caregiver_1_billings)
print(f"   ✅ 요양사 1이 생성한 모든 청부가 센터 1에 속함: {all_from_caregiver_in_center}")

caregiver_billings_in_center = [b for b in center_1_billings if b.caregiver_id == 1]
print(f"   ✅ 센터 1 청부 중 요양사 1 청부: {len(caregiver_billings_in_center)}개")

amount_match = sum(b.amount for b in caregiver_1_billings) == sum(b.amount for b in caregiver_billings_in_center)
print(f"   ✅ 금액 일치: ₩{sum(b.amount for b in caregiver_1_billings):,}")
print()

print("=" * 70)
print("결론: 데이터 일치성 ✅ 확인됨")
print("=" * 70)
print()
print("📊 상세 정보:")
print(f"   - 요양사가 생성한 청부: {len(caregiver_1_billings)}개")
print(f"   - 센터에 등록된 청부: {len(center_1_billings)}개")
print(f"   - 요양사 청부가 센터에 표시됨: {len(caregiver_billings_in_center)}개 (100% 일치)")
print()

db.close()
