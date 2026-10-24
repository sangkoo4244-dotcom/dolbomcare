"""가입 없이 체험할 수 있는 데모 센터·계정·방문 데이터를 만든다 (로그인 화면의 "둘러보기" 버튼이 사용).

다시 실행하면 기존 데모 데이터를 지우고 새로 만든다 - 이것이 데모 초기화 방법이다.
실제 센터/이용자 데이터는 건드리지 않는다 (데모 센터 이름과 demo_로 시작하는 데모 전용 이메일만 지운다).
운영자 콘솔(POST /api/v1/admin/demo/reset)과 scripts/seed_demo.py가 같이 쓴다.
"""
from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.notifications import notify
from app.api.records import get_year_month, guardian_visit_summary
from app.api.users import get_password_hash
from app.billing_rules import split_visit
from app.database import Base
from app.plans import PLAN_TRIAL
from app.models import (BillingRecord, CarePlan, Center, DailyRecord, HandoverNote, IncidentReport, LeaveRequest, Notification,
                        Resident, ResidentMessage, Schedule, User)

DEMO_PASSWORD = "demo1234!"
DEMO_CENTER_NAME = "데모 체험 센터"
DEMO_MANAGER_EMAIL = "demo_center_manager@dolbomcare.app"
DEMO_CAREGIVER_EMAIL = "demo_caregiver@dolbomcare.app"
DEMO_GUARDIAN_EMAIL = "demo_guardian@dolbomcare.app"
DEMO_SOCIAL_EMAIL = "demo_social_worker@dolbomcare.app"
DEMO_TRIAL_DAYS = 15  # 데모는 15일 동안 모든 기능을 쓸 수 있고, 끝나면 읽기 전용이다 (초기화하면 다시 15일)


def _clear_old_demo(db: Session) -> bool:
    """데모 센터·데모 계정·데모 이용자를 참조하는 행을 모두 지운다.
    체험 계정으로 근태·점검·보호자 열람 기록이 생기면 참조가 늘어나므로, 표를 하나씩 고르지 않고 외래키로 찾는다.
    운영 PostgreSQL은 외래키를 강제하므로 참조가 남아 있으면 삭제가 실패한다. 실제 센터 자료는 참조하지 않으므로 건드리지 않는다."""
    old_center_ids = [c.id for c in db.query(Center).filter(Center.name == DEMO_CENTER_NAME).all()]
    old_user_ids = [u.id for u in db.query(User).filter(User.email.like("demo_%@dolbomcare.app")).all()]
    if not old_center_ids and not old_user_ids:
        return False
    old_resident_ids = [r.id for r in db.query(Resident).filter(Resident.center_id.in_(old_center_ids)).all()] if old_center_ids else []
    targets = {"centers": old_center_ids, "residents": old_resident_ids, "users": old_user_ids}

    if old_center_ids:  # 센터 ↔ 센터장 순환 참조를 먼저 끊는다
        db.query(Center).filter(Center.id.in_(old_center_ids)).update({Center.manager_id: None}, synchronize_session=False)
    # 자식 표부터 지운다 (참조하는 쪽이 먼저 사라져야 부모를 지울 수 있다)
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in targets:
            continue
        conditions = []
        for column in table.columns:
            for fk in column.foreign_keys:
                ids = targets.get(fk.column.table.name)
                if ids:
                    conditions.append(column.in_(ids))
        if conditions:
            db.execute(table.delete().where(or_(*conditions)))
    if old_resident_ids:
        db.query(Resident).filter(Resident.id.in_(old_resident_ids)).delete(synchronize_session=False)
    if old_user_ids:
        db.query(User).filter(User.id.in_(old_user_ids)).delete(synchronize_session=False)
    if old_center_ids:
        db.query(Center).filter(Center.id.in_(old_center_ids)).delete(synchronize_session=False)
        for stale in [o for o in db.identity_map.values() if isinstance(o, Center) and o.id in old_center_ids]:
            db.expunge(stale)
    db.commit()
    return True


def seed_demo(db: Session, trial_ends_at: datetime | None = None) -> dict:
    """데모 데이터를 (다시) 만들고 만든 내용을 요약해 돌려준다.
    trial_ends_at을 주면 그 체험 종료일을 이어 쓰고, 주지 않으면 지금부터 DEMO_TRIAL_DAYS일이다."""
    reset = _clear_old_demo(db)

    center = Center(name=DEMO_CENTER_NAME, address="서울시 데모구 체험로 1", phone="02-0000-0000",
                    plan=PLAN_TRIAL, trial_ends_at=trial_ends_at or datetime.utcnow() + timedelta(days=DEMO_TRIAL_DAYS))
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

    # 이용자 3명 (그중 1명은 데모 보호자와 연결, 2명은 데모 요양사가 담당 - 나머지 1명은 미배정으로 둔다)
    # 주소와 좌표는 서울 도심의 공개 장소를 쓴다 (실제 사람의 주소가 아님). 좌표를 미리 넣어 두어 방문 지도에 점이 바로 찍힌다.
    residents_spec = [
        dict(name="김복동", age=84, care_grade=2, client_type="일반", guardian_id=None, primary=caregiver.id,
             address="서울특별시 중구 세종대로 110", latitude=37.5663, longitude=126.9779),
        dict(name="이순자", age=79, care_grade=3, client_type="차상위계층", guardian_id=guardian.id, primary=caregiver.id,
             address="서울특별시 중구 태평로1가 31", latitude=37.5652, longitude=126.9768),
        dict(name="박만수", age=88, care_grade=1, client_type="일반", guardian_id=None, primary=None,
             address="서울특별시 중구 세종대로 99", latitude=37.5658, longitude=126.9751),
    ]
    residents = []
    for spec in residents_spec:
        r = Resident(center_id=center.id, name=spec["name"], age=spec["age"], admission_date=datetime.now() - timedelta(days=200),
                     health_status="stable", guardian_id=spec["guardian_id"], care_grade=spec["care_grade"],
                     client_type=spec["client_type"], gender="여", primary_caregiver_id=spec["primary"],
                     address=spec["address"], latitude=spec["latitude"], longitude=spec["longitude"])
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

    # 역할 간 업무 흐름 데모: 사회복지사가 쓴 급여제공계획, 요양보호사가 올린 사고 보고·인계 메모, 요양보호사의 승인 대기 연차
    today = datetime.now().date()
    db.add(CarePlan(center_id=center.id, resident_id=residents[0].id, plan_type="regular", service_type="방문요양",
                    written_date=today - timedelta(days=30), service_start_date=today - timedelta(days=30), author_id=social_worker.id,
                    goals="낙상 없이 일상생활 동작을 유지한다", needs="보행 시 보조가 필요함", details="보행 보조, 식사 준비 보조",
                    frequency="주 5회", duration_minutes=60, opinion="데모 데이터: 계획대로 제공 중", supervisor_name="데모 사회복지사"))
    db.add(IncidentReport(center_id=center.id, resident_id=residents[1].id, reporter_id=caregiver.id, occurred_date=today - timedelta(days=2),
                          incident_type="fall", description="데모 데이터: 화장실 앞에서 미끄러져 넘어짐 (외상 없음)",
                          action_taken="즉시 일으켜 세우고 활력징후 확인", guardian_notified_date=today - timedelta(days=2),
                          prevention="욕실 바닥 매트 설치, 화장실 동행"))
    db.add(HandoverNote(center_id=center.id, resident_id=residents[2].id, author_id=caregiver.id,
                        content="데모 데이터: 최근 식사량이 줄었음. 다음 방문 때 확인 부탁"))
    db.add(LeaveRequest(center_id=center.id, staff_id=caregiver.id, leave_date=today + timedelta(days=5), leave_type="annual",
                        reason="데모 데이터: 개인 사정", status="pending"))
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


DEMO_LOGIN_EMAILS = (DEMO_MANAGER_EMAIL, DEMO_CAREGIVER_EMAIL, DEMO_SOCIAL_EMAIL, DEMO_GUARDIAN_EMAIL)


def refresh_demo_if_stale(db: Session) -> bool:
    """데모 센터가 오늘 만들어진 것이 아니면 데모를 초기화한다 (하루에 한 번, 첫 체험 로그인 때).
    체험 종료일은 이어 쓴다. 그래야 초기화할 때마다 15일이 새로 붙지 않는다. 초기화했으면 True."""
    center = db.query(Center).filter(Center.name == DEMO_CENTER_NAME).first()
    if center and center.created_at and center.created_at.date() == datetime.now().date():
        return False
    keep_end = center.trial_ends_at if center and center.plan == PLAN_TRIAL else None
    seed_demo(db, trial_ends_at=keep_end)
    return True
