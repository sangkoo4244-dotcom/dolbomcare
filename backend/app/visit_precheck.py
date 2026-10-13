"""공단 전송(전자태그) 사전점검 - 센터장이 청구·환수 위험을 미리 보게 한다.

규칙은 공단 "재가급여전자관리시스템(RFID) 전산 가이드북"(2023.12)의 오류코드·수정 기준에서 왔다:
- A1  수급자 인정유효기간·계약 확인 -> 인정유효기간 만료/임박
- 시작·종료 전송이 모두 있어야 자동 청구에 들어감 -> 일정은 지났는데 방문 기록이 없는 건, 도착만 있고 퇴실이 없는 건
- 급여계약 시간과 전송 시간이 30분 이상 차이나면 급여제공기록지를 수기로 작성
- S2  서비스 시간은 10시간까지만 인정
- (평가 지표 '직원변경') 담당 요양보호사가 바뀌면 14일 이내에 수급자(보호자)와 상담해야 함
- (평가 지표 '급여제공계획 수립') 수급자별 급여제공계획서를 연 1회 이상 작성

돌봄케어 안의 일정·기록만 보며 공단 시스템은 조회하지 않는다 (실제 공단 전송 상태와는 다를 수 있다).
"""
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import DailyRecord, Resident, Schedule
from app.review import record_fits_schedule

EXPIRING_DAYS = 30
GAP_MINUTES = 30
MAX_MINUTES = 600


def run_precheck(db: Session, center_id: int, days: int = 14, now: datetime = None) -> dict:
    now = now or datetime.now()
    since = now - timedelta(days=days)
    residents = {r.id: r for r in db.query(Resident).filter(Resident.center_id == center_id).all()}
    issues = []

    for r in residents.values():
        if not r.recognition_end:
            continue
        end = r.recognition_end if isinstance(r.recognition_end, date) else r.recognition_end.date()
        left = (end - now.date()).days
        if left < 0:
            issues.append({"type": "recognition_expired", "resident_id": r.id, "resident": r.name,
                           "detail": f"인정유효기간이 {end.isoformat()}에 끝났습니다 (오류코드 A1: 계약·인정기간 확인)"})
        elif left <= EXPIRING_DAYS:
            issues.append({"type": "recognition_expiring", "resident_id": r.id, "resident": r.name,
                           "detail": f"인정유효기간이 {left}일 뒤({end.isoformat()}) 끝납니다. 갱신 계약이 필요합니다"})

    schedules = db.query(Schedule).filter(
        Schedule.center_id == center_id,
        Schedule.scheduled_date >= since,
        Schedule.scheduled_date < now,
        Schedule.status == "scheduled",
    ).all()
    records = db.query(DailyRecord).filter(
        DailyRecord.recorded_date >= since - timedelta(days=1),
        DailyRecord.resident_id.in_(list(residents) or [0]),
    ).all()

    for s in schedules:
        name = residents[s.resident_id].name if s.resident_id in residents else "(알 수 없음)"
        when = s.scheduled_date.strftime("%m/%d %H:%M")
        has_record = any(r.resident_id == s.resident_id and r.caregiver_id == s.caregiver_id
                         and record_fits_schedule(s, r.recorded_date) for r in records)
        if not s.arrived_at and not has_record:
            issues.append({"type": "missing_record", "resident_id": s.resident_id, "resident": name, "schedule_id": s.id,
                           "detail": f"{when} 방문 일정에 도착·기록이 없습니다 (시작·종료가 모두 있어야 자동 청구에 포함)"})
            continue
        if s.arrived_at and not s.left_at:
            issues.append({"type": "missing_end", "resident_id": s.resident_id, "resident": name, "schedule_id": s.id,
                           "detail": f"{when} 방문은 도착만 있고 퇴실이 없습니다"})
            continue
        if s.arrived_at and s.left_at:
            actual = int((s.left_at - s.arrived_at).total_seconds() // 60)
            if actual > MAX_MINUTES:
                issues.append({"type": "over_10h", "resident_id": s.resident_id, "resident": name, "schedule_id": s.id,
                               "detail": f"{when} 방문 {actual}분: 서비스 시간은 10시간까지만 인정됩니다 (오류코드 S2)"})
            elif s.duration_minutes and abs(actual - s.duration_minutes) >= GAP_MINUTES:
                issues.append({"type": "time_gap", "resident_id": s.resident_id, "resident": name, "schedule_id": s.id,
                               "detail": f"{when} 계획 {s.duration_minutes}분, 실제 {actual}분: 30분 이상 차이나면 급여제공기록지를 직접 써야 합니다"})

    from app.api.counseling import detect_caregiver_changes
    for c in detect_caregiver_changes(db, center_id, now.date()):
        if c["status"] == "overdue":
            issues.append({"type": "caregiver_change_counsel", "resident_id": c["resident_id"], "resident": c["resident_name"],
                           "detail": f"담당 요양보호사가 {c['from_caregiver']}에서 {c['to_caregiver']}(으)로 바뀐 뒤({c['changed_on']}) "
                                     f"14일 이내 상담 기한({c['deadline']})이 지났습니다 (평가 지표: 직원변경)"})

    from app.api.care_plans import center_plan_status
    for r in center_plan_status(db, center_id, now.date())["residents"]:
        if not r["has_plan_this_year"]:
            issues.append({"type": "care_plan_missing", "resident_id": r["resident_id"], "resident": r["resident_name"],
                           "detail": f"{now.year}년 급여제공계획서가 없습니다 (평가 지표: 급여제공계획 수립, 연 1회 이상)"})

    counts = {}
    for i in issues:
        counts[i["type"]] = counts.get(i["type"], 0) + 1
    return {"days": days, "total": len(issues), "counts": counts, "issues": issues[:30]}
