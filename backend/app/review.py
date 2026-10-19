from datetime import datetime, timedelta

from app.models import Schedule

TIME_TOLERANCE_MINUTES = 5


EARLY_MINUTES = 60
LATE_MINUTES = 180


def record_fits_schedule(schedule, recorded_at: datetime) -> bool:
    """기록은 계획 날짜의 방문 시간대(시작 60분 전 ~ 종료 3시간 후) 안에 저장된 것만 계획과 연결한다."""
    if recorded_at is None or recorded_at.date() != schedule.scheduled_date.date():
        return False
    start = schedule.scheduled_date - timedelta(minutes=EARLY_MINUTES)
    visit_end = schedule.left_at or (schedule.scheduled_date + timedelta(minutes=schedule.duration_minutes or 60))
    return start <= recorded_at <= visit_end + timedelta(minutes=LATE_MINUTES)


def find_schedule(db, caregiver_id, resident_id, when: datetime):
    day_start = datetime(when.year, when.month, when.day)
    candidates = db.query(Schedule).filter(
        Schedule.caregiver_id == caregiver_id,
        Schedule.resident_id == resident_id,
        Schedule.status == "scheduled",
        Schedule.scheduled_date >= day_start,
        Schedule.scheduled_date < day_start + timedelta(days=1),
    ).order_by(Schedule.scheduled_date).all()
    fits = [s for s in candidates if record_fits_schedule(s, when)]
    # 같은 날 방문이 여러 개면, 기록 시각에 가장 가까운 방문에 연결한다.
    # 먼저 끝난 아침 방문의 퇴실 시각에 늦은 시간 여유를 더해 오후 기록이 붙는 것을 막는다.
    return min(fits, key=lambda s: abs((when - s.scheduled_date).total_seconds()), default=None)


def review_flags(db, billing, record=None):
    schedule = None
    if record is not None and record.schedule_id:
        schedule = db.query(Schedule).filter(Schedule.id == record.schedule_id).first()
    if schedule is None:
        schedule = find_schedule(db, billing.caregiver_id, billing.resident_id, billing.recorded_date)

    if getattr(billing, "benefit_type", None) == "day_night":
        return []  # 주·야간보호는 방문 계획·도착 기록으로 확인하는 급여가 아니다
    if schedule is None:
        return ["계획 외"]

    flags = []
    if schedule.arrived_at is None:
        flags.append("도착 미기록")
    elif schedule.left_at is not None and record is not None and record.duration_minutes:
        on_site = (schedule.left_at - schedule.arrived_at).total_seconds() / 60
        if record.duration_minutes > on_site + TIME_TOLERANCE_MINUTES:
            flags.append("제공 시간 초과")
    return flags


def gate_reason_for(schedule, requested_date, now):
    """센터장 확인이 필요한 기록의 사유. 오늘 일정과 연결되지 않은 기록과 오늘이 아닌 날짜의 소급 기록만 해당한다."""
    reasons = []
    if schedule is None:
        reasons.append("계획 외 기록")
    elif schedule.arrived_at is None:
        reasons.append("도착 미기록")
    elif getattr(schedule, "arrive_check", None) in ("far", "no_location"):
        reasons.append("위치 확인 필요")
    if requested_date is not None and requested_date.date() != now.date():
        reasons.append("소급 기록")
    return " · ".join(reasons) or None

