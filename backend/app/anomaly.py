"""이상 패턴 찾기: 허위 기록이 만들어질 때 남는 흔적을 센터장에게 보여 준다. 판정은 하지 않고 확인할 건만 모은다."""
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import DailyRecord, LeaveRequest, Resident, Schedule, User

UNPLANNED_THRESHOLD = 3
NO_ARRIVAL_THRESHOLD = 3


def find_anomalies(db: Session, center_id: int, now: datetime, days: int = 14) -> list:
    since = now - timedelta(days=days)
    records = db.query(DailyRecord).join(Resident, DailyRecord.resident_id == Resident.id).filter(
        Resident.center_id == center_id, DailyRecord.recorded_date >= since).all()
    names = {u.id: u.full_name for u in db.query(User).filter(User.center_id == center_id).all()}
    schedules = {s.id: s for s in db.query(Schedule).filter(Schedule.center_id == center_id).all()}
    leave_days = {(l.staff_id, l.leave_date) for l in db.query(LeaveRequest).filter(
        LeaveRequest.center_id == center_id, LeaveRequest.status == "approved",
        LeaveRequest.leave_date >= since.date()).all()}

    by_caregiver = defaultdict(list)
    for r in records:
        by_caregiver[r.caregiver_id].append(r)

    findings = []

    def add(kind, label, caregiver_id, count, detail):
        findings.append({"kind": kind, "label": label, "caregiver_id": caregiver_id,
                         "caregiver_name": names.get(caregiver_id, "-"), "count": count, "detail": detail})

    for caregiver_id, rows in by_caregiver.items():
        rows.sort(key=lambda r: r.recorded_date)

        # 같은 시간에 다른 이용자 기록이 겹침 (한 사람이 두 곳에서 동시에 일할 수 없다)
        overlaps = []
        for i, a in enumerate(rows):
            a_end = a.recorded_date + timedelta(minutes=a.duration_minutes or 0)
            for b in rows[i + 1:]:
                if b.recorded_date >= a_end:
                    break
                if b.resident_id != a.resident_id:
                    overlaps.append(b.recorded_date.strftime("%m/%d %H:%M"))
        if overlaps:
            add("overlap", "같은 시간에 여러 이용자 기록", caregiver_id, len(overlaps),
                f"겹치는 시각: {', '.join(sorted(set(overlaps))[:5])}")

        # 승인된 연차 날짜에 기록이 있음
        on_leave = sorted({r.recorded_date.strftime("%m/%d") for r in rows
                           if (caregiver_id, r.recorded_date.date()) in leave_days})
        if on_leave:
            add("leave_day", "연차로 승인된 날 기록", caregiver_id, len(on_leave), f"날짜: {', '.join(on_leave[:5])}")

        # 방문 계획과 연결되지 않은 기록이 반복됨
        unplanned = [r for r in rows if r.schedule_id is None]
        if len(unplanned) >= UNPLANNED_THRESHOLD:
            add("unplanned", "방문 계획 없이 기록이 반복됨", caregiver_id, len(unplanned),
                f"최근 {days}일 중 계획과 연결되지 않은 기록 {len(unplanned)}건")

        # 계획은 있는데 도착 기록이 없음
        no_arrival = [r for r in rows if r.schedule_id in schedules and schedules[r.schedule_id].arrived_at is None]
        if len(no_arrival) >= NO_ARRIVAL_THRESHOLD:
            add("no_arrival", "도착 기록 없이 방문 기록이 반복됨", caregiver_id, len(no_arrival),
                f"최근 {days}일 중 도착 없이 기록된 방문 {len(no_arrival)}건")

    return sorted(findings, key=lambda f: (-f["count"], f["caregiver_name"]))
