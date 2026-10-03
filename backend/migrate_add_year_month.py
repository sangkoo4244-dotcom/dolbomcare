#!/usr/bin/env python3
"""
마이그레이션: BillingRecord에 year_month 필드 추가
PostgreSQL의 기존 billing_records 테이블에 year_month 컬럼을 추가합니다.
"""

from app.database import SessionLocal
from app.models import BillingRecord
from datetime import datetime
import sys

def migrate():
    db = SessionLocal()

    try:
        print("🔄 마이그레이션 시작: year_month 필드 추가")
        print("=" * 60)

        # 기존 BillingRecord 조회
        records = db.query(BillingRecord).filter(
            BillingRecord.year_month == None
        ).all()

        if not records:
            print("✅ year_month이 없는 기록이 없습니다.")
            print("   모든 기록이 이미 year_month를 가지고 있습니다.")
            db.close()
            return

        print(f"📋 총 {len(records)}개 기록을 업데이트합니다.")

        # 각 기록의 recorded_date로부터 year_month 설정
        for idx, record in enumerate(records, 1):
            if record.recorded_date:
                year_month = record.recorded_date.strftime("%Y-%m")
                record.year_month = year_month

                if idx % 50 == 0:
                    print(f"  진행 중... {idx}/{len(records)}")

        # 커밋
        db.commit()

        print(f"\n✅ 마이그레이션 완료!")
        print("=" * 60)
        print(f"✅ {len(records)}개 기록이 업데이트되었습니다.")

        # 검증
        updated_count = db.query(BillingRecord).filter(
            BillingRecord.year_month != None
        ).count()

        print(f"✅ 검증: {updated_count}개 기록이 year_month를 가지고 있습니다.")

    except Exception as e:
        db.rollback()
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
