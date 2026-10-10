from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_manager
from app.database import get_db
from app.models import CopayInvoice, DailyRecord, NeedsAssessment, Resident, RiskAssessment, User
from app.api.needs_assessments import _to_dict as needs_to_dict
from app.api.risk_assessments import ASSESSMENT_TYPES, _to_dict as risk_to_dict

router = APIRouter()

# 공단 기관평가 때 보통 요구하는 증빙들을 한 번에 모아서 보여준다.
# 평가 항목 번호·공식 문구는 기관/회차마다 조금씩 달라질 수 있어 여기서 특정 평가번호에
# 못박아 매핑하지 않는다 - 우리가 이미 갖고 있는 기록(방문기록·서명·평가·수납)을
# 날짜 범위로 모아 보여주는 선에서 그친다. 센터가 실제 평가표와 대조해서 쓰면 된다.


@router.get("/resident/{resident_id}")
def get_resident_audit_packet(
    resident_id: int,
    start: str,
    end: str,
    db: Session = Depends(get_db),
    actor: User = Depends(require_manager),
):
    """한 이용자의 기간 내 평가 준비 자료 (방문기록·기초평가·위험도평가·본인부담금)를 한 번에 모은다."""
    resident = db.query(Resident).filter(Resident.id == resident_id).first()
    if not resident or resident.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")

    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end) + timedelta(days=1)  # end 날짜 전체를 포함
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다 (YYYY-MM-DD)")

    assessors = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}

    visits = (
        db.query(DailyRecord)
        .filter(
            DailyRecord.resident_id == resident_id,
            DailyRecord.recorded_date >= start_dt,
            DailyRecord.recorded_date < end_dt,
        )
        .order_by(DailyRecord.recorded_date)
        .all()
    )
    visit_list = [{
        "date": v.recorded_date.isoformat() if v.recorded_date else None,
        "caregiver_name": assessors.get(v.caregiver_id, "-"),
        "service_type": v.service_type,
        "duration_minutes": v.duration_minutes,
        "has_signature": bool(v.signature),
    } for v in visits]

    needs_rows = (
        db.query(NeedsAssessment)
        .filter(
            NeedsAssessment.resident_id == resident_id,
            NeedsAssessment.assessed_date >= start_dt,
            NeedsAssessment.assessed_date < end_dt,
        )
        .order_by(NeedsAssessment.assessed_date)
        .all()
    )

    risk_rows = (
        db.query(RiskAssessment)
        .filter(
            RiskAssessment.resident_id == resident_id,
            RiskAssessment.assessed_date >= start_dt,
            RiskAssessment.assessed_date < end_dt,
        )
        .order_by(RiskAssessment.assessed_date)
        .all()
    )
    risk_by_type = {code: [] for code in ASSESSMENT_TYPES}
    for r in risk_rows:
        if r.assessment_type in risk_by_type:
            risk_by_type[r.assessment_type].append(risk_to_dict(r, assessors.get(r.assessed_by)))

    copay_rows = (
        db.query(CopayInvoice)
        .filter(CopayInvoice.resident_id == resident_id)
        .order_by(CopayInvoice.year_month)
        .all()
    )
    copay_in_range = [c for c in copay_rows if start[:7] <= c.year_month <= end[:7]]

    return {
        "resident": {
            "name": resident.name,
            "care_grade": resident.care_grade,
            "recognition_number": resident.recognition_number,
            "client_type": resident.client_type,
        },
        "period": {"start": start, "end": end},
        "visits": {
            "count": len(visit_list),
            "signed_count": sum(1 for v in visit_list if v["has_signature"]),
            "records": visit_list,
        },
        "needs_assessments": [needs_to_dict(a, assessors.get(a.assessed_by)) for a in needs_rows],
        "risk_assessments": {
            code: {"type_label": label, "records": risk_by_type[code]}
            for code, label in ASSESSMENT_TYPES.items()
        },
        "copay": [{
            "year_month": c.year_month,
            "total_amount": c.total_amount,
            "paid_amount": c.paid_amount,
            "status": c.status,
        } for c in copay_in_range],
    }
