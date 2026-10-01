#!/usr/bin/env python3
"""submitted_to_nhis 상태의 청부 기록 삭제"""

from app.database import SessionLocal
from app.models import BillingRecord

db = SessionLocal()

try:
    # submitted_to_nhis 상태의 청부 찾기
    submitted = db.query(BillingRecord).filter(
        BillingRecord.approval_status == 'submitted_to_nhis',
        BillingRecord.center_id == 1
    ).all()

    print(f"🗑️ submitted_to_nhis 상태의 청부 발견: {len(submitted)}건")

    for record in submitted:
        print(f"  - ID {record.id}: caregiver_id={record.caregiver_id}, amount={record.amount}, status={record.approval_status}")
        db.delete(record)

    if submitted:
        db.commit()
        print(f"✅ {len(submitted)}건 삭제 완료")
    else:
        print("✅ submitted_to_nhis 청부 없음")

except Exception as e:
    print(f"❌ 오류: {e}")
    db.rollback()

finally:
    db.close()
