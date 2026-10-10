"""
가입 없이 체험할 수 있는 데모 계정을 만든다 (login.html의 "데모로 체험하기" 버튼이 사용).

재실행하면 기존 데모 데이터를 전부 지우고 새로 만든다 - 즉, 이 스크립트를 다시 실행하는 것이
데모 데이터 초기화(reset) 방법이다. 실제 센터/이용자 데이터는 건드리지 않는다
(데모 전용 이메일 접두사 demo_로 식별되는 행만 삭제한다).

실행:
    cd backend && venv/Scripts/python.exe scripts/seed_demo.py
"""
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import SessionLocal
from app.models import User, Center, Resident, DailyRecord, BillingRecord, Notification, ResidentMessage
from app.api.users import get_password_hash
from app.api.notifications import notify
from app.api.records import guardian_visit_summary, get_year_month
from app.billing_rules import split_visit

DEMO_PASSWORD = "demo1234!"
DEMO_CENTER_NAME = "데모 체험 센터"
DEMO_MANAGER_EMAIL = "demo_center_manager@dolbomcare.app"
DEMO_CAREGIVER_EMAIL = "demo_caregiver@dolbomcare.app"
DEMO_GUARDIAN_EMAIL = "demo_guardian@dolbomcare.app"

db = SessionLocal()

try:
    # 1) 기존 데모 데이터 정리 (재실행 = 초기화)
    old_center = db.query(Center).filter(Center.name == DEMO_CENTER_NAME).first()
    if old_center:
        old_residents = db.query(Resident).filter(Resident.center_id == old_center.id).all()
        old_resident_ids = [r.id for r in old_residents]
        old_user_ids = [u.id for u in db.query(User).filter(User.email.like("demo_%@dolbomcare.app")).all()]

        db.query(Notification).filter(Notification.user_id.in_(old_user_ids)).delete(synchronize_session=False)
        db.query(ResidentMessage).filter(ResidentMessage.center_id == old_center.id).delete(synchronize_session=False)
        db.query(BillingRecord).filter(BillingRecord.resident_id.in_(old_resident_ids)).delete(synchronize_session=False)
        db.query(DailyRecord).filter(DailyRecord.resident_id.in_(old_resident_ids)).delete(synchronize_session=False)
        for r in old_residents:
            db.delete(r)
        for u in db.query(User).filter(User.id.in_(old_user_ids)).all():
            db.delete(u)
        db.delete(old_center)
        db.commit()
        print("[0] 기존 데모 데이터 삭제 완료 (초기화)")

    # 2) 센터 + 계정
    center = Center(name=DEMO_CENTER_NAME, address="서울시 데모구 체험로 1", phone="02-0000-0000")
    db.add(center); db.flush()

    manager = User(email=DEMO_MANAGER_EMAIL, hashed_password=get_password_hash(DEMO_PASSWORD),
                    full_name="데모 센터장", role="center_manager", center_id=center.id,
                    phone="01000000001", position="센터장", is_active=True)
    caregiver = User(email=DEMO_CAREGIVER_EMAIL, hashed_password=get_password_hash(DEMO_PASSWORD),
                      full_name="데모 요양사", role="caregiver", center_id=center.id,
                      phone="01000000002", position="요양보호사", is_active=True)
    guardian = User(email=DEMO_GUARDIAN_EMAIL, hashed_password=get_password_hash(DEMO_PASSWORD),
                     full_name="데모 보호자", role="guardian", phone="01000000003", is_active=True)
    db.add_all([manager, caregiver, guardian]); db.flush()
    center.manager_id = manager.id
    db.commit()
    print(f"[1] 데모 계정 생성 완료 (center_manager={manager.email}, caregiver={caregiver.email}, guardian={guardian.email})")

    # 3) 이용자 3명 (그중 1명은 데모 보호자와 연결)
    residents_spec = [
        dict(name="김복동", age=84, care_grade=2, client_type="일반", guardian_id=None),
        dict(name="이순자", age=79, care_grade=3, client_type="차상위계층", guardian_id=guardian.id),
        dict(name="박만수", age=88, care_grade=1, client_type="일반", guardian_id=None),
    ]
    residents = []
    for spec in residents_spec:
        r = Resident(center_id=center.id, name=spec["name"], age=spec["age"],
                      admission_date=datetime.now() - timedelta(days=200),
                      health_status="stable", guardian_id=spec["guardian_id"],
                      care_grade=spec["care_grade"], client_type=spec["client_type"], gender="여")
        db.add(r)
        residents.append(r)
    db.flush()
    db.commit()
    print(f"[2] 데모 이용자 {len(residents)}명 생성 완료")

    # 4) 최근 5일치 방문 기록 + 청구 (승인 완료 상태로 넣어야 대시보드·정산 화면에 숫자가 보인다)
    service_types = ["basic_care", "meal_service", "medical_care"]
    count = 0
    for day_offset in range(5, 0, -1):
        visit_date = datetime.now() - timedelta(days=day_offset)
        for i, resident in enumerate(residents):
            service_type = service_types[(day_offset + i) % len(service_types)]
            duration = [60, 90, 60][(day_offset + i) % 3]
            total_cost, _, amount = split_visit(duration, resident.client_type)

            daily = DailyRecord(resident_id=resident.id, caregiver_id=caregiver.id, recorded_date=visit_date,
                                 service_type=service_type, condition="good", notes="데모 데이터: 특이사항 없음",
                                 duration_minutes=duration)
            db.add(daily); db.flush()

            billing = BillingRecord(daily_record_id=daily.id, caregiver_id=caregiver.id, resident_id=resident.id,
                                     center_id=center.id, resident_name=resident.name, care_grade=resident.care_grade,
                                     client_type=resident.client_type, service_category="재가급여",
                                     service_type=service_type, amount=amount, total_cost=total_cost,
                                     recorded_date=visit_date, year_month=get_year_month(visit_date),
                                     status="approved", approval_status="approved",
                                     approved_by=manager.id, approved_at=visit_date)
            db.add(billing)
            count += 1

            if resident.guardian_id:
                summary = guardian_visit_summary(resident.name, service_type, duration, "good")
                notify(db, resident.guardian_id, "visit_completed", summary)
    db.commit()
    print(f"[3] 방문 기록 + 청구 {count}건 생성 완료 (승인 상태 - 대시보드/정산에 즉시 반영됨)")

    # 5) 보호자 소통 데모 메시지 (한 번씩 주고받은 형태)
    linked = next(r for r in residents if r.guardian_id)
    db.add(ResidentMessage(center_id=center.id, resident_id=linked.id, sender_id=manager.id,
                            sender_role="center_manager", body="안녕하세요, 어머님 오늘 식사와 컨디션 모두 양호하십니다."))
    db.add(ResidentMessage(center_id=center.id, resident_id=linked.id, sender_id=guardian.id,
                            sender_role="guardian", body="항상 신경 써주셔서 감사합니다!"))
    db.commit()
    notify(db, manager.id, "message_received", f"{linked.name} 보호자 메시지: 항상 신경 써주셔서 감사합니다!")
    db.commit()
    print("[4] 보호자 소통 데모 메시지 생성 완료")

    print("\n=== 데모 계정 정보 (login.html 버튼이 이 값을 그대로 사용) ===")
    print(f"센터장: {DEMO_MANAGER_EMAIL} / {DEMO_PASSWORD}")
    print(f"보호자: {DEMO_GUARDIAN_EMAIL} / {DEMO_PASSWORD}")

finally:
    db.close()
