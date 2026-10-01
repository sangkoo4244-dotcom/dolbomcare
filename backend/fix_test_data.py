#!/usr/bin/env python3
"""기존 테스트 데이터 수정"""

from app.database import SessionLocal
from app.models import BillingRecord
from datetime import datetime, timedelta

db = SessionLocal()

try:
    print("🔧 테스트 데이터 수정 중...")

    # reimbursed 상태인 청부를 과거 날짜로 변경하고 daily_record_id 제거
    reimbursed = db.query(BillingRecord).filter(
        BillingRecord.approval_status == 'reimbursed'
    ).first()

    if reimbursed:
        print(f"현재 reimbursed:")
        print(f"  - recorded_date: {reimbursed.recorded_date}")
        print(f"  - daily_record_id: {reimbursed.daily_record_id}")

        reimbursed.recorded_date = datetime.now() - timedelta(days=10)
        reimbursed.daily_record_id = None  # ← 아카이브된 청부는 daily_record와 연결 안 함
        db.commit()

        print(f"수정됨:")
        print(f"  - recorded_date: {reimbursed.recorded_date} (10일 전)")
        print(f"  - daily_record_id: {reimbursed.daily_record_id} (제거)")
    else:
        print("❌ reimbursed 청부를 찾을 수 없습니다")

except Exception as e:
    db.rollback()
    print(f"❌ 오류: {e}")
finally:
    db.close()
