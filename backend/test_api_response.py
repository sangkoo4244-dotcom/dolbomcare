#!/usr/bin/env python3
"""API 응답 검증 - 실제 API가 반환하는 데이터 확인"""

from app.database import SessionLocal
from app.models import User, DailyRecord, BillingRecord
from datetime import date, datetime, time
from sqlalchemy import and_

db = SessionLocal()

try:
    # 요양사 데이터
    caregiver = db.query(User).filter(User.role == 'caregiver').first()
    caregiver_id = caregiver.id if caregiver else None

    print(f"\n📋 요양사: {caregiver.email}")

    # /records/today 로직 재현
    today = date.today()
    today_start = datetime.combine(today, time.min)
    today_end = datetime.combine(today, time.max)

    print(f"📅 기준 날짜: {today.isoformat()}")

    # DailyRecord 조회
    records = db.query(DailyRecord).filter(
        DailyRecord.caregiver_id == caregiver_id,
        DailyRecord.recorded_date >= today_start,
        DailyRecord.recorded_date <= today_end
    ).all()

    print(f"\n📝 DailyRecord: {len(records)}건")

    # BillingRecord 조회 (연결된 것만)
    billing_ids = [r.id for r in records]
    billings = db.query(BillingRecord).filter(
        BillingRecord.daily_record_id.in_(billing_ids),
        BillingRecord.is_archived == False
    ).all()

    print(f"💳 BillingRecord: {len(billings)}건")
    for b in billings:
        print(f"  - {b.approval_status:20} ₩{b.amount:,}")

    # 요양사 기준: submitted_to_nhis 제외 (API 로직)
    billing_total = sum(b.amount for b in billings if b.approval_status != 'submitted_to_nhis')

    print(f"\n✅ API가 반환할 total_billing_amount: ₩{billing_total:,}")
    print(f"   (submitted_to_nhis 제외됨)")

    # caregiver_billing.html 기준
    all_billings = db.query(BillingRecord).filter(
        BillingRecord.caregiver_id == caregiver_id,
        BillingRecord.is_archived == False
    ).all()

    cb_total = sum(b.amount for b in all_billings if b.approval_status != 'submitted_to_nhis')

    print(f"\n📊 caregiver_billing.html가 표시할 금액: ₩{cb_total:,}")

    # 비교
    if billing_total == cb_total:
        print(f"\n✅ ✅ ✅ 완벽 일치! ✅ ✅ ✅")
    else:
        print(f"\n❌ 불일치! 차이: ₩{abs(billing_total - cb_total):,}")

except Exception as e:
    print(f"❌ 오류: {e}")
    import traceback
    traceback.print_exc()
finally:
    db.close()
