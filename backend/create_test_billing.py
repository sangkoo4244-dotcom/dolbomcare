"""
테스트 청구 기록 생성 스크립트
이 스크립트는 대시보드 테스트를 위한 청구 데이터를 생성합니다.
"""
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app.database import SessionLocal
from app.models import BillingRecord, User, Resident, Center

def create_test_billing_records():
    """테스트 청구 기록 생성"""
    db = SessionLocal()

    try:
        # 기존 센터, 이용자, 사용자 확인
        center = db.query(Center).first()
        if not center:
            print("❌ 센터가 없습니다. 먼저 센터를 생성하세요.")
            return

        caregiver = db.query(User).filter(User.role == "caregiver").first()
        if not caregiver:
            print("❌ 요양사가 없습니다.")
            return

        residents = db.query(Resident).limit(3).all()
        if not residents:
            print("❌ 이용자가 없습니다. 먼저 이용자를 생성하세요.")
            return

        # 이번 달 청구 기록 생성
        current_month = datetime.utcnow()
        service_types = ["basic_care", "meal_service", "medical_care"]
        amounts = [30000, 10000, 50000]

        billing_records = []

        # 매일 3건씩 생성 (한 달치)
        for day in range(1, 28):
            for idx, (service_type, amount) in enumerate(zip(service_types, amounts)):
                recorded_date = datetime(
                    current_month.year,
                    current_month.month,
                    day,
                    10 + idx,  # 10시, 11시, 12시
                    0
                )

                record = BillingRecord(
                    caregiver_id=caregiver.id,
                    resident_id=residents[idx % len(residents)].id,
                    center_id=center.id,
                    service_type=service_type,
                    amount=amount,
                    recorded_date=recorded_date,
                    status="pending" if day < 15 else "submitted"
                )
                billing_records.append(record)

        # 일괄 저장
        db.bulk_save_objects(billing_records)
        db.commit()

        # 통계 출력
        total_records = len(billing_records)
        total_amount = sum(r.amount for r in billing_records)
        submitted = len([r for r in billing_records if r.status == "submitted"])

        print(f"""
✅ 테스트 청구 기록 생성 완료!

📊 통계:
- 총 기록: {total_records}건
- 총 청구액: {total_amount:,}원
- 공단 제출: {submitted}건
- 미제출: {total_records - submitted}건
- 예상 단축율: 70% ↓

🎯 대시보드에서 실제 데이터 확인:
http://localhost:3000/dashboard.html
        """)

    except Exception as e:
        print(f"❌ 오류: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_test_billing_records()
