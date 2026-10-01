#!/usr/bin/env python3
"""통계 검증 - 화면에 표시되는 수치가 올바른지 확인"""

from app.database import SessionLocal
from app.models import BillingRecord

db = SessionLocal()

print("\n" + "="*70)
print("📊 청부 관리 통계 검증")
print("="*70)

billings = db.query(BillingRecord).all()

print("\n📋 1️⃣ 현재 청부 (활성, 아카이브 제외)")
print("-" * 70)

active_billings = [b for b in billings if not b.is_archived]
print(f"총 개수: {len(active_billings)}개\n")

# 상태별 통계
status_map = {
    'pending': '⏳ 대기 중',
    'approved': '✅ 승인',
    'submitted_to_nhis': '📤 건보청구',
    'reimbursed': '💰 환급완료',
    'rejected': '❌ 거절'
}

stats = {}
for status in status_map.keys():
    count = len([b for b in active_billings if b.approval_status == status])
    amount = sum(b.amount for b in active_billings if b.approval_status == status)
    stats[status] = {'count': count, 'amount': amount}

for status, count in sorted([(s, stats[s]['count']) for s in status_map.keys()], key=lambda x: -x[1]):
    amount = stats[status]['amount']
    label = status_map[status]
    print(f"{label}: {stats[status]['count']}개 (₩{amount:,})")

total_active = len(active_billings)
total_active_amount = sum(b.amount for b in active_billings)
print(f"\n{'전체': <10}: {total_active}개 (₩{total_active_amount:,})")

# 상태별 상세
print("\n\n📈 2️⃣ 상태별 상세")
print("-" * 70)

for status in ['pending', 'approved', 'submitted_to_nhis', 'rejected', 'reimbursed']:
    records = [b for b in active_billings if b.approval_status == status]
    if records:
        print(f"\n{status.upper()} ({status_map.get(status, status)}):")
        for r in records:
            print(f"  - ID{r.id}: ₩{r.amount:,}")
        total = sum(r.amount for r in records)
        avg = total // len(records)
        print(f"  합계: ₩{total:,} (평균: ₩{avg:,})")

print("\n\n📦 3️⃣ 아카이브된 청부")
print("-" * 70)

archived_billings = [b for b in billings if b.is_archived]
print(f"총 개수: {len(archived_billings)}개\n")

for b in archived_billings:
    status = status_map.get(b.approval_status, b.approval_status)
    print(f"ID{b.id}: {status} (₩{b.amount:,}) - 아카이브: {b.archived_at}")

archived_amount = sum(b.amount for b in archived_billings)
print(f"\n합계: ₩{archived_amount:,}")

# 전체 금액 검증
print("\n\n💰 4️⃣ 금액 검증")
print("-" * 70)

total_amount = sum(b.amount for b in billings)
print(f"활성 청부: ₩{total_active_amount:,}")
print(f"아카이브: ₩{archived_amount:,}")
print(f"─────────────────")
print(f"총액: ₩{total_amount:,}")
print(f"검증: {total_active_amount} + {archived_amount} = {total_amount} {'✓' if total_active_amount + archived_amount == total_amount else '✗'}")

# Frontend 통계 카드 검증
print("\n\n📊 5️⃣ Frontend 통계 카드 (예상값)")
print("-" * 70)

# 아카이브 탭이 "현재 청부"일 때 표시되어야 할 값
print("\n[현재 청부] 탭:")
print(f"  전체: {total_active}개")
print(f"  대기 중: {stats['pending']['count']}개")
print(f"  승인: {stats['approved']['count']}개")
print(f"  건보청구: {stats['submitted_to_nhis']['count']}개")
print(f"  환급완료: {stats['reimbursed']['count']}개")
print(f"  거절: {stats['rejected']['count']}개")

# 아카이브 탭이 "아카이브된 청부"일 때 표시되어야 할 값
print("\n[아카이브된 청부] 탭:")
archived_stats = {}
for status in status_map.keys():
    count = len([b for b in archived_billings if b.approval_status == status])
    archived_stats[status] = count

print(f"  총개수: {len(archived_billings)}개")
for status, count in [(s, archived_stats[s]) for s in status_map.keys()]:
    if count > 0:
        print(f"  {status_map[status]}: {count}개")

# 체크리스트
print("\n\n✅ 6️⃣ 검증 결과")
print("-" * 70)

checks = [
    ("활성 청부 개수", total_active == 4),
    ("아카이브 청부 개수", len(archived_billings) == 1),
    ("총액 일치", total_amount == 6390000),
    ("활성 금액 합계", total_active_amount == 4990000),
    ("아카이브 금액 합계", archived_amount == 1400000),
    ("모든 reimbursed는 아카이브", all(b.is_archived for b in billings if b.approval_status == 'reimbursed')),
]

all_pass = True
for check_name, result in checks:
    status = "✅" if result else "❌"
    print(f"{status} {check_name}")
    if not result:
        all_pass = False

if all_pass:
    print("\n✅ 모든 통계가 정상입니다!")
else:
    print("\n⚠️ 일부 통계에 문제가 있습니다!")

print("\n" + "="*70)
print("✅ 통계 검증 완료")
print("="*70 + "\n")

db.close()
