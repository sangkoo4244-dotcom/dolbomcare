"""이번 달 성과: 돌봄케어가 이번 달 센터를 위해 실제로 한 일을 측정 가능한 숫자로만 보여 준다.
(시간 절약 같은 추정치는 넣지 않는다. 모든 숫자는 센터의 기록·청구·알림에서 바로 센다.)"""
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import benefits
from app.api.claim_helper import FLAG_LABELS, _month_range, claim_helper
from app.auth import require_manager
from app.billing_rules import VISIT_FEES
from app.database import get_db
from app.models import BillingRecord, Notification, Resident, User

router = APIRouter()

# 청구 전에 사람이 확인해야 하는 표시. 'surcharge'는 가산이 붙었다는 안내일 뿐 확인할 문제가 아니라서 뺀다.
ACTIONABLE_FLAGS = (
    "no_arrival", "time_gap", "overlap_resident", "overlap_caregiver", "long_visit", "grade5", "recognition_expired",
    "bath_no_partner", "nursing_no_order", "bath_reduced", "bath_too_short", "bath_weekly_over", "holiday_check", "holiday_table_missing",
)


def _time_surcharge(visit: dict) -> int:
    """이 방문에 돌봄케어가 더해 계산한 야간·일요일·공휴일 가산금액."""
    if "surcharge" not in visit["flags"]:
        return 0
    try:
        start = datetime.strptime(f"{visit['date']} {visit['start']}", "%Y-%m-%d %H:%M")
    except (KeyError, ValueError):
        return 0
    if visit["benefit_type"] == "home_nursing":
        try:
            base = benefits.home_nursing_fee(visit["minutes"])
        except ValueError:
            return 0
    else:
        base = VISIT_FEES.get(visit["minutes"], 0)
    return benefits.visit_surcharge(base, start, visit["minutes"])


@router.get("")
def value_report(year_month: str = Query(None, description="YYYY-MM, 비우면 이번 달"), db: Session = Depends(get_db),
                 manager: User = Depends(require_manager)):
    year_month = year_month or datetime.now().strftime("%Y-%m")
    start, end = _month_range(year_month)
    helper = claim_helper(year_month=year_month, db=db, manager=manager)
    visits = [v for r in helper["residents"] for v in r["visits"]]

    flag_counts = {k: 0 for k in ACTIONABLE_FLAGS}
    flagged = 0
    for v in visits:
        hit = [f for f in v["flags"] if f in flag_counts]
        flagged += 1 if hit else 0
        for f in hit:
            flag_counts[f] += 1
    top_flags = sorted(({"key": k, "label": FLAG_LABELS[k], "count": n} for k, n in flag_counts.items() if n), key=lambda x: -x["count"])

    arrived = sum(1 for v in visits if "no_arrival" not in v["flags"])
    time_surcharge = sum(_time_surcharge(v) for v in visits)
    bills = db.query(BillingRecord).filter(BillingRecord.center_id == manager.center_id, BillingRecord.recorded_date >= start,
                                           BillingRecord.recorded_date < end, BillingRecord.is_archived == False).all()  # noqa: E712
    live = [b for b in bills if b.approval_status != "rejected"]
    severe = sum(b.extra_amount or 0 for b in live if (b.benefit_type or "home_care") in ("home_care", "home_bath"))
    day_night_extra = sum(b.extra_amount or 0 for b in live if b.benefit_type == "day_night")

    guardian_ids = {r.guardian_id for r in db.query(Resident).filter(Resident.center_id == manager.center_id).all() if r.guardian_id}
    guardian_updates = db.query(Notification).filter(
        Notification.user_id.in_(guardian_ids), Notification.kind == "visit_completed",
        Notification.created_at >= start, Notification.created_at < end).count() if guardian_ids else 0

    return {
        "year_month": year_month,
        "visits": len(visits),
        "auto_bills": len(bills),
        "claim_amount": sum(b.amount or 0 for b in live),
        "total_cost": sum(b.total_cost or 0 for b in live),
        "review": {"flagged_visits": flagged, "clean_visits": len(visits) - flagged, "top_flags": top_flags[:5]},
        "arrival": {"with_arrival": arrived, "total": len(visits), "rate": round(arrived / len(visits) * 100) if visits else None},
        "calculated_extras": {"time_surcharge": time_surcharge, "severe_bonus": severe, "day_night_extra": day_night_extra,
                              "total": time_surcharge + severe + day_night_extra},
        "guardian_updates": guardian_updates,
        "approval": {
            "approved": sum(1 for b in bills if b.approval_status in ("approved", "submitted_to_nhis", "reimbursed")),
            "pending": sum(1 for b in bills if b.approval_status == "pending"),
            "draft": sum(1 for b in bills if b.approval_status == "draft"),
            "rejected": sum(1 for b in bills if b.approval_status == "rejected"),
        },
    }
