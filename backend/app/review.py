from datetime import datetime, timedelta

from app.models import Schedule

TIME_TOLERANCE_MINUTES = 5


def find_schedule(db, caregiver_id, resident_id, when: datetime):
    day_start = datetime(when.year, when.month, when.day)
    return db.query(Schedule).filter(
        Schedule.caregiver_id == caregiver_id,
        Schedule.resident_id == resident_id,
        Schedule.status != "cancelled",
        Schedule.scheduled_date >= day_start,
        Schedule.scheduled_date < day_start + timedelta(days=1),
    ).order_by(Schedule.scheduled_date).first()


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
