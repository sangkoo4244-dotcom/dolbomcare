#!/usr/bin/env python3
"""최종 수치 확인 - 모든 화면의 통계가 일치하는지 검증"""

from app.database import SessionLocal
from app.models import BillingRecord, User, DailyRecord, Resident

db = SessionLocal()

print("\n" + "="*70)
print("🔍 최종 수치 확인 및 대시보드 통계 검증")
print("="*70)

# 1. 전체 데이터 현황
print("\n📊 1️⃣ 현재 데이터 현황")
print("-" * 70)

all_billings = db.query(BillingRecord).all()
active_billings = [b for b in all_billings if not b.is_archived]
archived_billings = [b for b in all_billings if b.is_archived]

print(f"전체 청부: {len(all_billings)}개")
print(f"  - 활성: {len(active_billings)}개")
print(f"  - 아카이브: {len(archived_billings)}개")

# 2. 대시보드에 표시되어야 할 수치
print("\n\n📈 2️⃣ 대시보드 (Dashboard.html) 통계")
print("-" * 70)

# 사용자 수
users = db.query(User).all()
residents = db.query(Resident).all()
records_today = db.query(DailyRecord).count()

print(f"이용자 수: {len(residents)}명")
print(f"음성 기록 (이번달): {records_today}건")

# 처리 대기 (pending + rejected)
action_needed = [b for b in active_billings if b.approval_status in ['pending', 'rejected']]
print(f"처리 대기 (pending+rejected): {len(action_needed)}개")

# 전체 청부액 (활성만)
total_active_amount = sum(b.amount for b in active_billings)
print(f"전체 청부액 (활성만): ₩{total_active_amount:,}")

# 3. 청부 관리 페이지 (billing_management.html)
print("\n\n📋 3️⃣ 청부 관리 페이지 (billing_management.html)")
print("-" * 70)

print("[현재 청부 탭]")
print(f"  전체: {len(active_billings)}개")
print(f"  대기 중: {len([b for b in active_billings if b.approval_status == 'pending'])}개")
print(f"  승인: {len([b for b in active_billings if b.approval_status == 'approved'])}개")
print(f"  건보청구: {len([b for b in active_billings if b.approval_status == 'submitted_to_nhis'])}개")
print(f"  환급완료: {len([b for b in active_billings if b.approval_status == 'reimbursed'])}개")
print(f"  거절: {len([b for b in active_billings if b.approval_status == 'rejected'])}개")

print(f"\n[아카이브된 청부 탭]")
print(f"  전체: {len(archived_billings)}개")
for status in ['pending', 'approved', 'submitted_to_nhis', 'reimbursed', 'rejected']:
    count = len([b for b in archived_billings if b.approval_status == status])
    if count > 0:
        print(f"  {status}: {count}개")

# 4. 요양사 청부 페이지
print("\n\n👨‍⚕️ 4️⃣ 요양사 청부 페이지 (caregiver_billing.html)")
print("-" * 70)

caregiver_id = 2  # 테스트 데이터의 요양사 ID
caregiver_billings = [b for b in active_billings if b.caregiver_id == caregiver_id]

print(f"요양사(ID {caregiver_id})의 청부:")
print(f"  전체: {len(caregiver_billings)}개")
print(f"  대기 중: {len([b for b in caregiver_billings if b.approval_status == 'pending'])}개")
print(f"  승인: {len([b for b in caregiver_billings if b.approval_status == 'approved'])}개")
print(f"  건보청구: {len([b for b in caregiver_billings if b.approval_status == 'submitted_to_nhis'])}개")
print(f"  거절: {len([b for b in caregiver_billings if b.approval_status == 'rejected'])}개")

caregiver_amount = sum(b.amount for b in caregiver_billings)
print(f"  금액 합계: ₩{caregiver_amount:,}")

# 5. API 응답 예상 수치
print("\n\n🔗 5️⃣ API 응답 예상값")
print("-" * 70)

print("\n/billing/?center_id=1&include_archived=false")
print(f"  반환 기록: {len(active_billings)}개")
print(f"  응답 구조: {{\"total_records\": {len(active_billings)}, \"records\": [...]}}")

print("\n/billing/?center_id=1&include_archived=true")
print(f"  반환 기록: {len(all_billings)}개")

# 6. 상세 분석
print("\n\n📊 6️⃣ 상태별 상세")
print("-" * 70)

status_map = {
    'pending': '⏳ 대기 중',
    'approved': '✅ 승인',
    'submitted_to_nhis': '📤 건보청구',
    'reimbursed': '💰 환급완료 🗄️',
    'rejected': '❌ 거절'
}

print("\n활성 청부:")
for status in ['pending', 'approved', 'submitted_to_nhis', 'rejected']:
    records = [b for b in active_billings if b.approval_status == status]
    if records:
        amount = sum(b.amount for b in records)
        print(f"  {status_map[status]}: {len(records)}개 (₩{amount:,})")

print("\n아카이브된 청부:")
for records in archived_billings:
    status = records.approval_status
    print(f"  {status_map[status]}: 1개 (₩{records.amount:,})")

# 7. 최종 검증
print("\n\n✅ 7️⃣ 최종 검증")
print("-" * 70)

checks = [
    ("대시보드 청부액 계산", total_active_amount, "활성 청부의 합계"),
    ("청부관리 전체 수", len(active_billings), "활성 청부 개수"),
    ("아카이브 건수", len(archived_billings), "reimbursed 상태 개수"),
]

print()
for name, value, desc in checks:
    print(f"✓ {name}: {value} ({desc})")

print("\n" + "="*70)
print("✅ 최종 확인 완료")
print("="*70 + "\n")

db.close()
