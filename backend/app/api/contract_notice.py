"""장기요양급여 계약통보서 초안(공단 별지 제11호, 방문요양·방문목욕·방문간호).

시스템에 있는 값(이용자·기관·보호자·월별 이용 일정과 수가)만 채우고, 계약일·급여개시일·계약기간·계약자 관계는
시스템에 없으므로 센터가 직접 적는다. 금액은 일정 기준 초안이라 실제 제공기록과 다를 수 있다."""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import require_social_or_manager
from app.billing_rules import split_benefit
from app.database import get_db
from app.models import Center, Resident, ResidentGuardian, Schedule, User

router = APIRouter()
BENEFIT_LABELS = {"home_care": "방문요양", "home_bath": "방문목욕", "home_nursing": "방문간호"}
TO_FILL = ["계약일", "급여개시일", "계약기간", "계약자 성명·수급자와의 관계", "담당자 전화번호", "요양보호사 자격·면허번호"]


def _month_range(ym: str):
    try:
        y, m = map(int, ym.split("-"))
        start = date(y, m, 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="월은 YYYY-MM 형식으로 적어 주세요")
    if not 1 <= m <= 12:
        raise HTTPException(status_code=400, detail="월은 YYYY-MM 형식으로 적어 주세요")
    end = date(y + (m == 12), (m % 12) + 1, 1)
    return datetime.combine(start, datetime.min.time()), datetime.combine(end, datetime.min.time())


@router.get("/draft")
def draft(
    resident_id: int = Query(...),
    benefit_type: str = Query(...),
    year_month: str = Query(...),
    db: Session = Depends(get_db),
    actor: User = Depends(require_social_or_manager),
):
    if benefit_type not in BENEFIT_LABELS:
        raise HTTPException(status_code=400, detail="급여 종류는 방문요양, 방문목욕, 방문간호 중에서 골라 주세요")
    start, end = _month_range(year_month)
    resident = db.query(Resident).filter(Resident.id == resident_id, Resident.center_id == actor.center_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    center = db.query(Center).filter(Center.id == actor.center_id).first()

    q = db.query(Schedule).filter(
        Schedule.resident_id == resident.id,
        Schedule.status != "cancelled",
        Schedule.scheduled_date >= start,
        Schedule.scheduled_date < end,
    )
    if benefit_type == "home_care":
        q = q.filter(or_(Schedule.benefit_type == "home_care", Schedule.benefit_type.is_(None)))
    else:
        q = q.filter(Schedule.benefit_type == benefit_type)
    schedules = q.order_by(Schedule.scheduled_date).all()

    names = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}
    visits, warnings = [], []
    for s in schedules:
        when = s.scheduled_date.strftime("%m/%d %H:%M")
        if not s.duration_minutes:
            warnings.append(f"{when}: 제공 시간이 없어 금액을 계산하지 못했습니다")
            continue
        try:
            total, _, _ = split_benefit(benefit_type, s.duration_minutes, resident.client_type, bath_mode=s.bath_mode, start=s.scheduled_date)
        except ValueError as e:
            warnings.append(f"{when}: {e}")
            continue
        visits.append({
            "date": s.scheduled_date.date().isoformat(),
            "start": s.scheduled_date.strftime("%H:%M"),
            "end": (s.scheduled_date + timedelta(minutes=s.duration_minutes)).strftime("%H:%M"),
            "minutes": s.duration_minutes,
            "caregiver": names.get(s.caregiver_id, ""),
            "amount": total,
        })

    return {"status": "success", "data": {
        "form": "장기요양급여 계약통보서 (노인장기요양보험법 시행규칙 별지 제11호)",
        "benefit_type": benefit_type,
        "benefit_label": BENEFIT_LABELS[benefit_type],
        "year_month": year_month,
        "center": {"name": center.name if center else "", "institution_code": center.institution_code if center else None},
        "resident": {"name": resident.name, "birth_date": resident.birth_date.isoformat() if resident.birth_date else None,
                     "care_grade": resident.care_grade, "recognition_number": resident.recognition_number,
                     "client_type": resident.client_type,
                     "service_start_date": resident.service_start_date.isoformat() if resident.service_start_date else None,
                     "billing_address": resident.billing_address or ""},
        "guardian": {"name": resident.guardian_name or "", "phone": resident.guardian_phone or ""},
        "additional_guardians": [
            {"name": g.name, "relation": g.relation or "", "phone": g.phone or ""}
            for g in db.query(ResidentGuardian).filter(ResidentGuardian.resident_id == resident.id).order_by(ResidentGuardian.id).all()
        ],
        "to_fill": TO_FILL,
        "visits": visits,
        "count": len(visits),
        "total": sum(v["amount"] for v in visits),
        "warnings": warnings,
        "note": "금액은 일정 기준 초안입니다. 1인 몸 씻기 예외 등 실제 제공 기록과 다를 수 있으니 제출 전에 제공기록과 맞춰 보세요.",
    }}
