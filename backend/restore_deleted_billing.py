#!/usr/bin/env python3
"""삭제된 청부 기록 복구"""

from app.database import SessionLocal
from app.models import BillingRecord
from datetime import datetime

db = SessionLocal()

try:
    # 1,400,000원 청부 기록 복구 (caregiver_id=2, resident_id=1)
    print("🔄 삭제된 청부 기록 복구 중...")

    # 중복 확인
    existing = db.query(BillingRecord).filter(
        BillingRecord.caregiver_id == 2,
        BillingRecord.resident_id == 1,
        BillingRecord.amount == 1400000
    ).first()

    if existing:
        print("✅ 이미 존재함")
    else:
        # 복구할 청부 생성
        billing = BillingRecord(
            caregiver_id=2,
            resident_id=1,
            center_id=1,
            service_type="기본 요양",
            amount=1400000,
            approval_status="pending",
            status="draft",
            recorded_date=datetime.now()
        )
        db.add(billing)
        db.commit()
        print(f"✅ 청부 복구 완료: ID {billing.id}, amount: 1,400,000원")

except Exception as e:
    print(f"❌ 오류: {e}")
    db.rollback()

finally:
    db.close()
