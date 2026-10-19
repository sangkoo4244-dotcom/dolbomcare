"""이상 패턴 찾기: 허위 기록이 만들어질 때 남는 흔적을 센터장에게 보여 준다. 판정은 하지 않고 확인할 건만 모은다.

직접 기록(DailyRecord)과 음성 기록(VoiceRecord)을 모두 본다. 음성 기록은 승인 때 남긴 확인 사유(gate_reason)로
계획 외·도착 미기록을 알아본다. 음성 기록에는 제공 시간이 없어서 겹침 검사는 직접 기록만 한다.
"""
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import BillingRecord, DailyRecord, LeaveRequest, Resident, Schedule, User, VoiceRecord

UNPLANNED_THRESHOLD = 3
NO_ARRIVAL_THRESHOLD = 3


def find_anomalies(db: Session, center_id: int, now: datetime, days: int = 14) -> list:
    since = now - timedelta(days=days)
    names = {u.id: u.full_name for u in db.query(User).filter(User.center_id == center_id).all()}
    schedules = {s.id: s for s in db.query(Schedule).filter(Schedule.center_id == center_id).all()}
    leave_days = {(l.staff_id, l.leave_date) for l in db.query(LeaveRequest).filter(
        LeaveRequest.center_id == center_id, LeaveRequest.status == "approved",
        LeaveRequest.leave_date >= since.date()).all()}

    # 사람별 기록 목록: 시작 시각, 이용자, 제공 시간(직접 기록만), 계획 외·도착 미기록 여부
    by_caregiver = defaultdict(list)

    daily = db.query(DailyRecord).join(Resident, DailyRecord.resident_id == Resident.id).filter(
        Resident.center_id == center_id, DailyRecord.recorded_date >= since).all()
    for r in daily:
        schedule = schedules.get(r.schedule_id) if r.schedule_id else None
        by_caregiver[r.caregiver_id].append({
            "start": r.recorded_date, "minutes": r.duration_minutes or 0, "resident_id": r.resident_id,
            "unplanned": r.schedule_id is None,
            "no_arrival": schedule is not None and schedule.arrived_at is None,
        })

    voices = db.query(VoiceRecord).filter(VoiceRecord.center_id == center_id,
                                          VoiceRecord.recorded_date >= since).all()
    for v in voices:
        billing = db.query(BillingRecord).filter(BillingRecord.id == v.billing_record_id).first() \
            if v.billing_record_id else None
        reason = (billing.gate_reason or "") if billing else ""
        by_caregiver[v.caregiver_id].append({
            "start": v.recorded_date, "minutes": 0, "resident_id": v.resident_id,
            "unplanned": "계획 외" in reason, "no_arrival": "도착 미기록" in reason,
        })

    findings = []

    def add(kind, label, caregiver_id, count, detail):
        findings.append({"kind": kind, "label": label, "caregiver_id": caregiver_id,
                         "caregiver_name": names.get(caregiver_id, "-"), "count": count, "detail": detail})

    for caregiver_id, rows in by_caregiver.items():
        rows.sort(key=lambda r: r["start"])

        # 같은 시간에 다른 이용자 기록이 겹침 (직접 기록끼리만 비교한다)
        overlaps = []
        timed = [r for r in rows if r["minutes"]]
        for i, a in enumerate(timed):
            a_end = a["start"] + timedelta(minutes=a["minutes"])
            for b in timed[i + 1:]:
                if b["start"] >= a_end:
                    break
                if b["resident_id"] != a["resident_id"]:
                    overlaps.append(b["start"].strftime("%m/%d %H:%M"))
        if overlaps:
            add("overlap", "같은 시간에 여러 이용자 기록", caregiver_id, len(overlaps),
                f"겹치는 시각: {', '.join(sorted(set(overlaps))[:5])}")

        # 승인된 연차 날짜에 기록이 있음
        on_leave = sorted({r["start"].strftime("%m/%d") for r in rows
                           if (caregiver_id, r["start"].date()) in leave_days})
        if on_leave:
            add("leave_day", "연차로 승인된 날 기록", caregiver_id, len(on_leave), f"날짜: {', '.join(on_leave[:5])}")

        unplanned = [r for r in rows if r["unplanned"]]
        if len(unplanned) >= UNPLANNED_THRESHOLD:
            add("unplanned", "방문 계획 없이 기록이 반복됨", caregiver_id, len(unplanned),
                f"최근 {days}일 중 계획과 연결되지 않은 기록 {len(unplanned)}건")

        no_arrival = [r for r in rows if r["no_arrival"]]
        if len(no_arrival) >= NO_ARRIVAL_THRESHOLD:
            add("no_arrival", "도착 기록 없이 방문 기록이 반복됨", caregiver_id, len(no_arrival),
                f"최근 {days}일 중 도착 없이 기록된 방문 {len(no_arrival)}건")

    return sorted(findings, key=lambda f: (-f["count"], f["caregiver_name"]))
