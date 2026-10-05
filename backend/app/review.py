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
    return next((s for s in candidates if record_fits_schedule(s, when)), None)


def review_flags(db, billing, record=None):
    schedule = None
    if record is not None and record.schedule_id:
        schedule = db.query(Schedule).filter(Schedule.id == record.schedule_id).first()
    if schedule is None:
        schedule = find_schedule(db, billing.caregiver_id, billing.resident_id, billing.recorded_date)

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
