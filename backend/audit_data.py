#!/usr/bin/env python3
"""시스템 감사 스크립트 - 수치 검증"""

from app.database import SessionLocal
from app.models import BillingRecord, User, Resident, Center
from datetime import datetime

db = SessionLocal()

print("\n" + "="*70)
print("🔍 돌봄케어 청부관리 시스템 전체 감사")
print("="*70)

# 1. 기본 통계
print("\n📊 1️⃣ 기본 통계")
print("-" * 70)

centers = db.query(Center).all()
users = db.query(User).all()
residents = db.query(Resident).all()
billings = db.query(BillingRecord).all()

print(f"센터: {len(centers)}개")
for c in centers:
    print(f"  - {c.name} (ID: {c.id})")

print(f"\n사용자: {len(users)}명")
for u in users:
    print(f"  - {u.full_name} ({u.role}) - {u.email}")

print(f"\n이용자: {len(residents)}명")
for r in residents:
    print(f"  - {r.name} ({r.care_grade}등급, {r.client_type}) - 센터 {r.center_id}")

print(f"\n청부 기록: {len(billings)}개")

# 2. 상태별 분석
print("\n📈 2️⃣ 상태별 분석")
print("-" * 70)

status_counts = {}
status_details = {}

for b in billings:
    status = b.approval_status
    is_archived = b.is_archived

    if status not in status_counts:
        status_counts[status] = {"total": 0, "active": 0, "archived": 0}
        status_details[status] = []

    status_counts[status]["total"] += 1
    if is_archived:
        status_counts[status]["archived"] += 1
    else:
        status_counts[status]["active"] += 1

    status_details[status].append({
        "id": b.id,
        "resident_id": b.resident_id,
        "amount": b.amount,
        "is_archived": b.is_archived,
        "archived_at": b.archived_at
    })

for status in sorted(status_counts.keys()):
    counts = status_counts[status]
    print(f"\n{status.upper()}: {counts['total']}개")
    print(f"  - 활성: {counts['active']}개")
    print(f"  - 아카이브: {counts['archived']}개")
    for detail in status_details[status]:
        archive_label = " 🗄️ (아카이브됨)" if detail["is_archived"] else ""
        print(f"    • ID{detail['id']} - {detail['amount']:,}원{archive_label}")

# 3. 활성 vs 아카이브
print("\n📦 3️⃣ 활성 / 아카이브 현황")
print("-" * 70)

active_billings = [b for b in billings if not b.is_archived]
archived_billings = [b for b in billings if b.is_archived]

print(f"활성 청부: {len(active_billings)}개")
for b in active_billings:
    print(f"  - ID{b.id}: {b.approval_status} (₩{b.amount:,})")

print(f"\n아카이브된 청부: {len(archived_billings)}개")
for b in archived_billings:
    print(f"  - ID{b.id}: {b.approval_status} (₩{b.amount:,}) - 아카이브: {b.archived_at}")

# 4. 금액 계산
print("\n💰 4️⃣ 금액 현황")
print("-" * 70)

total_amount = sum(b.amount for b in billings)
active_amount = sum(b.amount for b in active_billings)
archived_amount = sum(b.amount for b in archived_billings)

print(f"총 청부액: ₩{total_amount:,}")
print(f"  - 활성: ₩{active_amount:,}")
print(f"  - 아카이브: ₩{archived_amount:,}")

# 상태별 금액
print("\n상태별 금액:")
for status in sorted(status_counts.keys()):
    amount = sum(d['amount'] for d in status_details[status])
    count = len(status_details[status])
    avg = amount // count if count > 0 else 0
    print(f"  {status}: ₩{amount:,} ({count}개, 평균: ₩{avg:,})")

# 5. 버그 검사
print("\n🐛 5️⃣ 잠재적 버그 검사")
print("-" * 70)

issues = []

# 아카이브 검사
for b in billings:
    if b.is_archived and b.approval_status != "reimbursed":
        issues.append(f"⚠️ ID{b.id}: 아카이브되었지만 상태가 {b.approval_status} (reimbursed여야 함)")

    if b.is_archived and not b.archived_at:
        issues.append(f"⚠️ ID{b.id}: 아카이브되었지만 archived_at이 없음")

    if b.approval_status == "reimbursed" and not b.is_archived:
        issues.append(f"⚠️ ID{b.id}: reimbursed 상태이지만 아카이브되지 않음 (자동 아카이브 실패?)")

# 승인 정보 검사
for b in billings:
    if b.approval_status in ["approved", "submitted_to_nhis", "reimbursed", "rejected"]:
        if not b.approved_by:
            issues.append(f"⚠️ ID{b.id}: {b.approval_status} 상태이지만 approved_by가 없음")
        if not b.approved_at:
            issues.append(f"⚠️ ID{b.id}: {b.approval_status} 상태이지만 approved_at이 없음")

if issues:
    for issue in issues:
        print(issue)
else:
    print("✅ 버그 없음")

# 6. API 응답 필드 검사
print("\n🔗 6️⃣ API 필드 검사")
print("-" * 70)

sample_billing = billings[0] if billings else None
if sample_billing:
    print(f"샘플 청부 (ID{sample_billing.id})의 필드:")
    fields = {
        "id": sample_billing.id,
        "resident_id": sample_billing.resident_id,
        "caregiver_id": sample_billing.caregiver_id,
        "center_id": sample_billing.center_id,
        "service_type": sample_billing.service_type,
        "amount": sample_billing.amount,
        "status": sample_billing.status,
        "approval_status": sample_billing.approval_status,
        "rejection_reason": sample_billing.rejection_reason,
        "is_archived": sample_billing.is_archived,
        "recorded_date": sample_billing.recorded_date,
        "submitted_date": sample_billing.submitted_date,
        "archived_at": sample_billing.archived_at,
        "created_at": sample_billing.created_at,
        "approved_by": sample_billing.approved_by,
        "approved_at": sample_billing.approved_at,
    }
    for field, value in fields.items():
        status = "✓" if value is not None else "✗"
        print(f"  {status} {field}: {value}")

print("\n" + "="*70)
print("✅ 감사 완료")
print("="*70 + "\n")

db.close()
