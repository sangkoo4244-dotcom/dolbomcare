from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_manager
from app.database import get_db
from app.models import (CarePlan, CaseConference, Counseling, CopayInvoice, DailyRecord, IncidentReport, NeedsAssessment, Resident,
                        ResidentNotice, RiskAssessment, ServiceEvaluation, TrainingSession, User)
from app.api.needs_assessments import _to_dict as needs_to_dict
from app.api.risk_assessments import ASSESSMENT_TYPES, _to_dict as risk_to_dict
from app.api.care_plans import _to_dict as plan_to_dict
from app.api.counseling import _names as counsel_names, _to_dict as counseling_to_dict
from app.api.service_reviews import _conf_dict, _ev_dict
from app.api.trainings import _notice_dict, _session_dict
from app.api.incidents import _names as incident_names, _to_dict as incident_to_dict

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

    s_date, e_date = start_dt.date(), (end_dt - timedelta(days=1)).date()
    today = datetime.now().date()
    names = counsel_names(db, actor.center_id)
    plans = db.query(CarePlan).filter(CarePlan.resident_id == resident_id, CarePlan.written_date >= s_date, CarePlan.written_date <= e_date).order_by(CarePlan.written_date).all()
    evals = db.query(ServiceEvaluation).filter(ServiceEvaluation.resident_id == resident_id, ServiceEvaluation.evaluated_date >= s_date, ServiceEvaluation.evaluated_date <= e_date).order_by(ServiceEvaluation.evaluated_date).all()
    counsels = db.query(Counseling).filter(Counseling.resident_id == resident_id, Counseling.counsel_date >= s_date, Counseling.counsel_date <= e_date).order_by(Counseling.counsel_date).all()
    notices = db.query(ResidentNotice).filter(ResidentNotice.resident_id == resident_id, ResidentNotice.notice_date >= s_date, ResidentNotice.notice_date <= e_date).order_by(ResidentNotice.notice_date).all()
    conferences = db.query(CaseConference).filter(CaseConference.resident_id == resident_id, CaseConference.conference_date >= s_date, CaseConference.conference_date <= e_date).order_by(CaseConference.conference_date).all()

    return {
        "care_plans": [plan_to_dict(p, db, assessors.get(p.author_id)) for p in plans],
        "service_evaluations": [_ev_dict(e, db, names, today) for e in evals],
        "counselings": [counseling_to_dict(c, names) for c in counsels],
        "notices": [_notice_dict(n, {resident.id: resident.name}) for n in notices],
        "conferences": [_conf_dict(c, names, today) for c in conferences],
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


@router.get("/center")
def get_center_audit_packet(start: str, end: str, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    """센터 공통 증빙(직원 교육·직원 상담·사례관리 회의)을 기간별로 모은다."""
    try:
        s_date = datetime.fromisoformat(start).date()
        e_date = datetime.fromisoformat(end).date()
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식이 올바르지 않습니다 (YYYY-MM-DD)")
    names = counsel_names(db, actor.center_id)
    staff_names = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}
    sessions = db.query(TrainingSession).filter(TrainingSession.center_id == actor.center_id, TrainingSession.session_date >= s_date, TrainingSession.session_date <= e_date).order_by(TrainingSession.session_date).all()
    staff_counsels = db.query(Counseling).filter(Counseling.center_id == actor.center_id, Counseling.kind == "staff", Counseling.counsel_date >= s_date, Counseling.counsel_date <= e_date).order_by(Counseling.counsel_date).all()
    conferences = db.query(CaseConference).filter(CaseConference.center_id == actor.center_id, CaseConference.conference_date >= s_date, CaseConference.conference_date <= e_date).order_by(CaseConference.conference_date).all()
    incidents = db.query(IncidentReport).filter(IncidentReport.center_id == actor.center_id, IncidentReport.occurred_date >= s_date, IncidentReport.occurred_date <= e_date).order_by(IncidentReport.occurred_date).all()
    incident_name_map = incident_names(db, incidents)
    today = datetime.now().date()
    return {
        "period": {"start": start, "end": end},
        "trainings": [_session_dict(x, staff_names) for x in sessions],
        "staff_counselings": [counseling_to_dict(c, names) for c in staff_counsels],
        "conferences": [_conf_dict(c, names, today) for c in conferences],
        "incidents": [incident_to_dict(i, incident_name_map) for i in incidents],
    }
