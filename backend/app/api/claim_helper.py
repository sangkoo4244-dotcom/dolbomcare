"""공단 청구 입력 도우미 - 센터장이 공단 장기요양정보시스템의 [급여내용 자료관리]에 옮겨 적을 방문요양 자료를
이용자별·일자별로 공단 화면 순서(급여제공일·요양요원·시작/종료·총시간·서비스·제공내용)에 맞춰 보여 준다.

공단에 전송하지 않는다. 공단 화면에서 청구서 생성·전송은 기관이 직접 한다(공단 청구 업무 바로알기, 2021.12).
"""
from calendar import monthrange
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.guardian import CARE_ITEM_LABELS
from app.auth import require_manager
from app.billing_rules import REVENUE_STATUSES
from app.database import get_db
from app.models import BillingRecord, DailyRecord, Resident, Schedule, User

router = APIRouter()

TIME_GAP_MINUTES = 30  # 공단 안내: 계약 시간과 전송 시간이 30분 이상 차이 나면 기록지를 수기로 작성
LONG_VISIT_MINUTES = {3: 210, 4: 210}  # 특정내역 '270분 이상 연속 제공(3-4등급은 210분 이상)'
LONG_VISIT_DEFAULT = 270

FLAG_LABELS = {
    "no_arrival": "도착·퇴실 기록 없음 - 시작·종료 시각을 직접 입력해야 합니다",
    "time_gap": "도착~퇴실 시간과 제공 시간이 30분 이상 차이",
    "overlap_resident": "같은 이용자의 방문 시간이 겹칩니다 (2인 제공 사유 또는 중복 확인)",
    "overlap_caregiver": "같은 요양보호사의 다른 방문과 시간이 겹칩니다 (공단에서 불능 처리될 수 있음)",
    "long_visit": "연속 제공 시간이 깁니다 (공단 특정내역 '270분 이상 연속 제공사유', 3-4등급은 210분 이상)",
    "grade5": "5등급 이용자입니다 (인지활동형이 아닌 일반 방문요양이면 공단 특정내역 '5등급 일반요양제공사유' 입력)",
    "recognition_expired": "방문일이 인정 유효기간 밖입니다 (공단에 수급자가 보이지 않을 수 있음)",
}


def _month_range(year_month: str):
    try:
        year, month = (int(x) for x in year_month.split("-"))
        start = datetime(year, month, 1)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="월은 YYYY-MM 형식이어야 합니다")
    return start, start + timedelta(days=monthrange(year, month)[1])


def _overlaps(a, b):
    return a["_start"] < b["_end"] and b["_start"] < a["_end"]


@router.get("")
def claim_helper(year_month: str = Query(..., description="급여제공월 YYYY-MM"),
                 db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    start, end = _month_range(year_month)
    center = manager.center_id
    records = db.query(DailyRecord).join(Resident, Resident.id == DailyRecord.resident_id).filter(
        Resident.center_id == center, DailyRecord.recorded_date >= start, DailyRecord.recorded_date < end,
    ).order_by(DailyRecord.recorded_date).all()
    if not records:
        return {"year_month": year_month, "residents": [], "flag_counts": {}, "flag_labels": FLAG_LABELS, "visit_count": 0}

    residents = {r.id: r for r in db.query(Resident).filter(Resident.id.in_({r.resident_id for r in records})).all()}
    names = {u.id: u.full_name for u in db.query(User).filter(User.center_id == center).all()}
    schedule_ids = {r.schedule_id for r in records if r.schedule_id}
    schedules = {s.id: s for s in db.query(Schedule).filter(Schedule.id.in_(schedule_ids)).all()} if schedule_ids else {}
    billings = {}
    for b in db.query(BillingRecord).filter(BillingRecord.daily_record_id.in_({r.id for r in records}), BillingRecord.is_archived == False).all():  # noqa: E712
        billings[b.daily_record_id] = b

    visits = []
    for r in records:
        sch = schedules.get(r.schedule_id)
        resident = residents[r.resident_id]
        has_arrival = bool(sch and sch.arrived_at)
        start_at = sch.arrived_at if has_arrival else (sch.scheduled_date if sch else r.recorded_date)
        left_at = sch.left_at if sch and sch.left_at else None
        minutes = r.duration_minutes or (sch.duration_minutes if sch else None) or 0
        end_at = left_at or start_at + timedelta(minutes=minutes)
        stay = int((left_at - start_at).total_seconds() // 60) if has_arrival and left_at else None
        bill = billings.get(r.id)
        items = [CARE_ITEM_LABELS.get(c, c) for c in (r.care_items or "").split(",") if c]
        visit = {
            "date": start_at.strftime("%Y-%m-%d"), "caregiver": names.get(r.caregiver_id, ""),
            "start": start_at.strftime("%H:%M"), "end": end_at.strftime("%H:%M"), "minutes": minutes,
            "stay_minutes": stay, "service": "방문요양", "items": items,
            "status": bill.approval_status if bill else None,
            "total_cost": bill.total_cost if bill and bill.total_cost is not None else (bill.amount if bill else None),
            "claim_amount": bill.amount if bill else None,
            "flags": [],
            "_resident_id": r.resident_id, "_caregiver_id": r.caregiver_id, "_start": start_at, "_end": end_at,
        }
        if not has_arrival:
            visit["flags"].append("no_arrival")
        if stay is not None and minutes and abs(stay - minutes) >= TIME_GAP_MINUTES:
            visit["flags"].append("time_gap")
        if minutes >= LONG_VISIT_MINUTES.get(resident.care_grade, LONG_VISIT_DEFAULT):
            visit["flags"].append("long_visit")
        if resident.care_grade == 5:
            visit["flags"].append("grade5")
        rec_day = start_at.date()
        if (resident.recognition_start and rec_day < resident.recognition_start) or (resident.recognition_end and rec_day > resident.recognition_end):
            visit["flags"].append("recognition_expired")
        visits.append(visit)

    by_day = {}
    for v in visits:
        by_day.setdefault(v["date"], []).append(v)
    for day_visits in by_day.values():
        for i, a in enumerate(day_visits):
            for b in day_visits[i + 1:]:
                if not _overlaps(a, b):
                    continue
                if a["_resident_id"] == b["_resident_id"]:
                    for v in (a, b):
                        if "overlap_resident" not in v["flags"]:
                            v["flags"].append("overlap_resident")
                if a["_caregiver_id"] == b["_caregiver_id"] and a["_resident_id"] != b["_resident_id"]:
                    for v in (a, b):
                        if "overlap_caregiver" not in v["flags"]:
                            v["flags"].append("overlap_caregiver")

    by_resident = {}
    for v in visits:
        by_resident.setdefault(v["_resident_id"], []).append(v)
    flag_counts = {}
    out = []
    for rid, vs in by_resident.items():
        resident = residents[rid]
        vs.sort(key=lambda v: (v["date"], v["start"]))
        counted = [v for v in vs if v["status"] in REVENUE_STATUSES]
        for v in vs:
            for f in v["flags"]:
                flag_counts[f] = flag_counts.get(f, 0) + 1
        out.append({
            "name": resident.name, "recognition_number": resident.recognition_number,
            "birth_date": resident.birth_date.isoformat() if resident.birth_date else None,
            "care_grade": resident.care_grade, "client_type": resident.client_type,
            "visits": [{k: v for k, v in x.items() if not k.startswith("_")} for x in vs],
            "totals": {"visits": len(vs), "minutes": sum(x["minutes"] for x in vs), "approved_visits": len(counted),
                       "total_cost": sum(x["total_cost"] or 0 for x in counted), "claim_amount": sum(x["claim_amount"] or 0 for x in counted),
                       "flagged": sum(1 for x in vs if x["flags"])},
        })
    out.sort(key=lambda r: r["name"])
    return {"year_month": year_month, "residents": out, "flag_counts": flag_counts, "flag_labels": FLAG_LABELS, "visit_count": len(visits)}
