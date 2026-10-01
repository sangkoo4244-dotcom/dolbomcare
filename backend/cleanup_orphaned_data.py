#!/usr/bin/env python3
"""orphaned 데이터 정리 스크립트"""

from app.database import SessionLocal
from app.models import BillingRecord

db = SessionLocal()

try:
    # caregiver_id=3의 모든 청부 기록 찾기
    orphaned = db.query(BillingRecord).filter(BillingRecord.caregiver_id == 3).all()

    print(f"🗑️ caregiver_id=3의 orphaned 레코드 발견: {len(orphaned)}건")

    for record in orphaned:
        print(f"  - ID {record.id}: status={record.approval_status}, amount={record.amount}")
        db.delete(record)

    if orphaned:
        db.commit()
        print(f"✅ {len(orphaned)}건 삭제 완료")
    else:
        print("✅ orphaned 데이터 없음")

except Exception as e:
    print(f"❌ 오류: {e}")
    db.rollback()

finally:
    db.close()
