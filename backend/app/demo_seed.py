"""가입 없이 체험할 수 있는 데모 센터·계정·방문 데이터를 만든다 (로그인 화면의 "둘러보기" 버튼이 사용).

다시 실행하면 기존 데모 데이터를 지우고 새로 만든다 - 이것이 데모 초기화 방법이다.
실제 센터/이용자 데이터는 건드리지 않는다 (데모 센터 이름과 demo_로 시작하는 데모 전용 이메일만 지운다).
운영자 콘솔(POST /api/v1/admin/demo/reset)과 scripts/seed_demo.py가 같이 쓴다.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.api.notifications import notify
from app.api.records import get_year_month, guardian_visit_summary
from app.api.users import get_password_hash
from app.billing_rules import split_visit
from app.models import BillingRecord, Center, DailyRecord, Notification, Resident, ResidentMessage, Schedule, User

DEMO_PASSWORD = "demo1234!"
DEMO_CENTER_NAME = "데모 체험 센터"
DEMO_MANAGER_EMAIL = "demo_center_manager@dolbomcare.app"
DEMO_CAREGIVER_EMAIL = "demo_caregiver@dolbomcare.app"
DEMO_GUARDIAN_EMAIL = "demo_guardian@dolbomcare.app"
DEMO_SOCIAL_EMAIL = "demo_social_worker@dolbomcare.app"


def _clear_old_demo(db: Session) -> bool:
    old_center = db.query(Center).filter(Center.name == DEMO_CENTER_NAME).first()
    old_users = db.query(User).filter(User.email.like("demo_%@dolbomcare.app")).all()
    if not old_center and not old_users:
        return False
    old_user_ids = [u.id for u in old_users]
    if old_center:
        old_residents = db.query(Resident).filter(Resident.center_id == old_center.id).all()
        old_resident_ids = [r.id for r in old_residents]
        db.query(ResidentMessage).filter(ResidentMessage.center_id == old_center.id).delete(synchronize_session=False)
        db.query(Schedule).filter(Schedule.center_id == old_center.id).delete(synchronize_session=False)
        db.query(BillingRecord).filter(BillingRecord.resident_id.in_(old_resident_ids)).delete(synchronize_session=False)
        db.query(DailyRecord).filter(DailyRecord.resident_id.in_(old_resident_ids)).delete(synchronize_session=False)
        for r in old_residents:
            db.delete(r)
    if old_user_ids:
        db.query(Notification).filter(Notification.user_id.in_(old_user_ids)).delete(synchronize_session=False)
    for u in old_users:
        db.delete(u)
    if old_center:
        db.delete(old_center)
    db.commit()
    return True


def seed_demo(db: Session) -> dict:
    """데모 데이터를 (다시) 만들고 만든 내용을 요약해 돌려준다."""
    reset = _clear_old_demo(db)

    center = Center(name=DEMO_CENTER_NAME, address="서울시 데모구 체험로 1", phone="02-0000-0000")
    db.add(center)
    db.flush()
    manager = User(email=DEMO_MANAGER_EMAIL, hashed_password=get_password_hash(DEMO_PASSWORD), full_name="데모 센터장",
                   role="center_manager", center_id=center.id, phone="01000000001", position="센터장", is_active=True)
    caregiver = User(email=DEMO_CAREGIVER_EMAIL, hashed_password=get_password_hash(DEMO_PASSWORD), full_name="데모 요양사",
                     role="caregiver", center_id=center.id, phone="01000000002", position="요양보호사", is_active=True)
    social_worker = User(email=DEMO_SOCIAL_EMAIL, hashed_password=get_password_hash(DEMO_PASSWORD), full_name="데모 사회복지사",
                         role="social_worker", center_id=center.id, phone="01000000004", position="사회복지사", is_active=True)
    guardian = User(email=DEMO_GUARDIAN_EMAIL, hashed_password=get_password_hash(DEMO_PASSWORD), full_name="데모 보호자",
                    role="guardian", phone="01000000003", is_active=True)
    db.add_all([manager, caregiver, social_worker, guardian])
    db.flush()
    center.manager_id = manager.id
    db.commit()

    # 이용자 3명 (그중 1명은 데모 보호자와 연결)
    residents_spec = [
        dict(name="김복동", age=84, care_grade=2, client_type="일반", guardian_id=None),
        dict(name="이순자", age=79, care_grade=3, client_type="차상위계층", guardian_id=guardian.id),
        dict(name="박만수", age=88, care_grade=1, client_type="일반", guardian_id=None),
    ]
    residents = []
    for spec in residents_spec:
        r = Resident(center_id=center.id, name=spec["name"], age=spec["age"], admission_date=datetime.now() - timedelta(days=200),
                     health_status="stable", guardian_id=spec["guardian_id"], care_grade=spec["care_grade"],
                     client_type=spec["client_type"], gender="여")
        db.add(r)
        residents.append(r)
    db.flush()
    db.commit()

    # 최근 5일치 방문 기록 + 청구 (승인 완료 상태로 넣어야 대시보드·정산 화면에 숫자가 보인다)
    service_types = ["basic_care", "meal_service", "medical_care"]
    bill_count = 0
    for day_offset in range(5, 0, -1):
        visit_date = datetime.now() - timedelta(days=day_offset)
        for i, resident in enumerate(residents):
            service_type = service_types[(day_offset + i) % len(service_types)]
            duration = [60, 90, 60][(day_offset + i) % 3]
            total_cost, _, amount = split_visit(duration, resident.client_type)
            daily = DailyRecord(resident_id=resident.id, caregiver_id=caregiver.id, recorded_date=visit_date, service_type=service_type,
                                condition="good", notes="데모 데이터: 특이사항 없음", duration_minutes=duration)
            db.add(daily)
            db.flush()
            db.add(BillingRecord(daily_record_id=daily.id, caregiver_id=caregiver.id, resident_id=resident.id, center_id=center.id,
                                 resident_name=resident.name, care_grade=resident.care_grade, client_type=resident.client_type,
                                 service_category="재가급여", service_type=service_type, amount=amount, total_cost=total_cost,
                                 recorded_date=visit_date, year_month=get_year_month(visit_date), status="approved",
                                 approval_status="approved", approved_by=manager.id, approved_at=visit_date))
            bill_count += 1
            if resident.guardian_id:
                notify(db, resident.guardian_id, "visit_completed", guardian_visit_summary(resident.name, service_type, duration, "good"))
    db.commit()

    # 앞으로 3일치 예정 방문 일정 - 나의 일정에서 일정 변경 요청 등을 체험할 수 있게 한다
    schedule_count = 0
    for day_offset in (1, 2, 3):
        for i, resident in enumerate(residents):
            when = (datetime.now() + timedelta(days=day_offset)).replace(hour=9 + i * 2, minute=0, second=0, microsecond=0)
            db.add(Schedule(caregiver_id=caregiver.id, resident_id=resident.id, center_id=center.id, scheduled_date=when, duration_minutes=60,
                            planned_items="meal_assist,mobility", service_type="basic_care", status="scheduled"))
            schedule_count += 1
    db.commit()

    # 보호자 소통 데모 메시지 (한 번씩 주고받은 형태)
    linked = next(r for r in residents if r.guardian_id)
    db.add(ResidentMessage(center_id=center.id, resident_id=linked.id, sender_id=manager.id, sender_role="center_manager",
                           body="안녕하세요, 어머님 오늘 식사와 컨디션 모두 양호하십니다."))
    db.add(ResidentMessage(center_id=center.id, resident_id=linked.id, sender_id=guardian.id, sender_role="guardian",
                           body="항상 신경 써주셔서 감사합니다!"))
    db.commit()
    notify(db, manager.id, "message_received", f"{linked.name} 보호자 메시지: 항상 신경 써주셔서 감사합니다!")
    db.commit()

    return {
        "reset": reset, "center_id": center.id, "residents": len(residents), "bills": bill_count, "schedules": schedule_count,
        "accounts": [DEMO_MANAGER_EMAIL, DEMO_CAREGIVER_EMAIL, DEMO_SOCIAL_EMAIL, DEMO_GUARDIAN_EMAIL],
    }
