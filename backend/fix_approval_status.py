#!/usr/bin/env python3
"""잘못된 approval_status 수정"""

from app.database import SessionLocal
from app.models import BillingRecord

db = SessionLocal()

# approval_status가 "draft"인 기록 찾기
wrong_records = db.query(BillingRecord).filter(BillingRecord.approval_status == "draft").all()

print(f"수정 필요한 기록: {len(wrong_records)}건")

for record in wrong_records:
    print(f"  ID{record.id}: status={record.status} → approval_status를 'pending'으로 변경")
    record.approval_status = "pending"
    db.add(record)

db.commit()
print("✅ 수정 완료")

# 확인
updated = db.query(BillingRecord).filter(BillingRecord.id == 1).first()
print(f"\nID1 최종 상태: approval_status={updated.approval_status}")

db.close()
