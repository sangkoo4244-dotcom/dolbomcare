"""사고·응급상황 보고 - 요양보호사 또는 센터장이 보고하고, 센터장이 보호자 통보와 재발방지 대책을 기록한다.

평가에서 사고 대응이 확인되도록 다음을 점검한다.
- 사고 당일 또는 다음 날까지 보호자에게 알렸는지
- 재발방지 대책이 적혀 있는지
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.notifications import notify
from app.auth import get_current_user, require_manager
from app.database import get_db
from app.models import IncidentReport, Resident, User

router = APIRouter()

TYPES = {"fall": "낙상", "pressure_sore": "욕창", "medication": "투약 사고", "emergency": "응급 이송", "other": "기타"}
MIN_TEXT_LEN = 10
GUARDIAN_NOTICE_DAYS = 1


class IncidentBody(BaseModel):
    resident_id: int
    occurred_date: date
    incident_type: str
    description: str
    action_taken: str


class ProgressBody(BaseModel):
    guardian_notified_date: Optional[date] = None
    prevention: Optional[str] = None


def _issues(r: IncidentReport) -> list:
    issues = []
    if not r.guardian_notified_date:
        issues.append("보호자에게 알린 날짜가 기록되지 않았습니다")
    elif r.guardian_notified_date > r.occurred_date + timedelta(days=GUARDIAN_NOTICE_DAYS):
        issues.append(f"보호자 통보({r.guardian_notified_date})가 사고 다음 날보다 늦었습니다")
    if not (r.prevention or "").strip():
        issues.append("재발방지 대책이 기록되지 않았습니다")
    return issues


def _to_dict(r: IncidentReport, names: dict) -> dict:
    return {
        "id": r.id, "resident_id": r.resident_id, "resident_name": names.get(("r", r.resident_id)),
        "reporter_name": names.get(("u", r.reporter_id)),
        "occurred_date": r.occurred_date.isoformat(), "incident_type": r.incident_type,
        "incident_type_label": TYPES.get(r.incident_type, r.incident_type),
        "description": r.description, "action_taken": r.action_taken,
        "guardian_notified_date": r.guardian_notified_date.isoformat() if r.guardian_notified_date else None,
        "prevention": r.prevention, "issues": _issues(r),
    }


def _names(db: Session, rows: list) -> dict:
    names = {}
    if not rows:
        return names
    for r in db.query(Resident).filter(Resident.id.in_({x.resident_id for x in rows})).all():
        names[("r", r.id)] = r.name
    for u in db.query(User).filter(User.id.in_({x.reporter_id for x in rows})).all():
        names[("u", u.id)] = u.full_name
    return names


@router.get("/residents")
def residents(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role not in ("center_manager", "caregiver"):
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    rows = db.query(Resident).filter(Resident.center_id == actor.center_id).order_by(Resident.name).all()
    return {"residents": [{"id": r.id, "name": r.name} for r in rows]}


@router.get("")
def list_reports(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """센터장·사회복지사는 센터 전체를 본다(사회복지사는 열람만), 요양보호사는 본인이 보고한 건만 본다."""
    if actor.role not in ("center_manager", "caregiver", "social_worker"):
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    q = db.query(IncidentReport).filter(IncidentReport.center_id == actor.center_id)
    if actor.role == "caregiver":
        q = q.filter(IncidentReport.reporter_id == actor.id)
    rows = q.order_by(IncidentReport.occurred_date.desc(), IncidentReport.id.desc()).limit(200).all()
    names = _names(db, rows)
    reports = [_to_dict(r, names) for r in rows]
    return {"reports": reports, "with_issues": sum(1 for r in reports if r["issues"])}


@router.post("")
def create_report(body: IncidentBody, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role not in ("center_manager", "caregiver"):
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    resident = db.query(Resident).filter(Resident.id == body.resident_id, Resident.center_id == actor.center_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    if body.incident_type not in TYPES:
        raise HTTPException(status_code=400, detail="사고 유형을 선택해 주세요")
    if body.occurred_date > date.today():
        raise HTTPException(status_code=400, detail="발생일이 오늘보다 늦을 수 없습니다")
    if len(body.description.strip()) < MIN_TEXT_LEN or len(body.action_taken.strip()) < MIN_TEXT_LEN:
        raise HTTPException(status_code=400, detail=f"경과와 조치 내용을 {MIN_TEXT_LEN}자 이상 구체적으로 적어 주세요")
    report = IncidentReport(center_id=actor.center_id, resident_id=resident.id, reporter_id=actor.id,
                            occurred_date=body.occurred_date, incident_type=body.incident_type,
                            description=body.description.strip(), action_taken=body.action_taken.strip())
    db.add(report)
    if actor.role == "caregiver":
        for manager in db.query(User).filter(User.center_id == actor.center_id, User.role == "center_manager").all():
            notify(db, manager.id, "incident_reported",
                   f"{resident.name} 어르신 {TYPES[body.incident_type]} 사고가 보고되었습니다. 보호자 통보와 재발방지 대책을 기록해 주세요.")
    db.commit()
    return {"status": "success", "data": _to_dict(report, _names(db, [report]))}


@router.put("/{report_id}/progress")
def update_progress(report_id: int, body: ProgressBody, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    report = db.query(IncidentReport).filter(IncidentReport.id == report_id, IncidentReport.center_id == actor.center_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="보고를 찾을 수 없습니다")
    if body.guardian_notified_date:
        if body.guardian_notified_date < report.occurred_date:
            raise HTTPException(status_code=400, detail="보호자 통보일이 사고 발생일보다 빠를 수 없습니다")
        report.guardian_notified_date = body.guardian_notified_date
    if body.prevention is not None:
        report.prevention = body.prevention.strip() or None
    db.commit()
    return {"status": "success", "data": _to_dict(report, _names(db, [report]))}
