"""사회복지사 업무: 업무수행일지(방문상담)와 월 방문 확인 기록. 사회복지사·센터장이 쓰고, 같은 센터 이용자만 보인다."""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.needs_assessments import _to_dict as assessment_to_dict
from app.auth import require_social_or_manager
from app.database import get_db
from app.models import MonthlyMonitoring, NeedsAssessment, Resident, SocialVisitPlan, SocialWorkLog, User

router = APIRouter()


class LogBody(BaseModel):
    resident_id: int
    visited_at: datetime
    counseling_target: Optional[str] = Field(None, max_length=100)  # 상담대상자명(관계)
    counseling_result: Optional[str] = Field(None, max_length=2000)  # 상담결과 (필수)
    content: Optional[str] = Field(None, max_length=4000)
    monitoring_checked: bool = False


class MonitoringBody(BaseModel):
    resident_id: int
    year_month: str = Field(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    visit_date: datetime
    service_checked: bool = True
    note: Optional[str] = Field(None, max_length=1000)


def _resident(db: Session, resident_id: int, center_id: Optional[int]) -> Resident:
    r = db.query(Resident).filter(Resident.id == resident_id, Resident.center_id == center_id).first() if center_id else None
    if not r:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    return r


def _log_dict(log: SocialWorkLog, names: dict) -> dict:
    return {"id": log.id, "resident_id": log.resident_id, "visited_at": log.visited_at.strftime("%Y-%m-%d %H:%M"),
            "author_name": names.get(log.author_id, ""), "counseling_target": log.counseling_target,
            "counseling_result": log.counseling_result, "content": log.content, "monitoring_checked": log.monitoring_checked}


@router.post("/logs")
def create_log(body: LogBody, db: Session = Depends(get_db), actor: User = Depends(require_social_or_manager)):
    _resident(db, body.resident_id, actor.center_id)
    if not (body.counseling_target or "").strip():
        raise HTTPException(status_code=400, detail="상담대상자명(관계)을 적어 주세요 (예: 김영희(딸))")
    if not (body.counseling_result or "").strip():
        raise HTTPException(status_code=400, detail="상담결과를 적어 주세요 (2026 평가 필수 항목)")
    log = SocialWorkLog(center_id=actor.center_id, resident_id=body.resident_id, author_id=actor.id, visited_at=body.visited_at,
                        counseling_target=body.counseling_target.strip(), counseling_result=body.counseling_result.strip(),
                        content=(body.content or "").strip() or None, monitoring_checked=body.monitoring_checked)
    db.add(log)
    db.commit()
    return {"status": "success", "data": _log_dict(log, {actor.id: actor.full_name})}


@router.get("/logs")
def list_logs(resident_id: int = Query(...), db: Session = Depends(get_db), actor: User = Depends(require_social_or_manager)):
    _resident(db, resident_id, actor.center_id)
    rows = db.query(SocialWorkLog).filter(SocialWorkLog.resident_id == resident_id, SocialWorkLog.center_id == actor.center_id) \
        .order_by(SocialWorkLog.visited_at.desc()).all()
    names = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}
    return {"status": "success", "data": [_log_dict(r, names) for r in rows]}


@router.get("/logs/{log_id}/form")
def log_form(log_id: int, db: Session = Depends(get_db), actor: User = Depends(require_social_or_manager)):
    """업무수행일지 출력(별지 제24호 1쪽)에 필요한 값. 시스템에 없는 칸은 돌려주지 않고 출력 화면에서 빈칸으로 둔다."""
    log = db.query(SocialWorkLog).filter(SocialWorkLog.id == log_id, SocialWorkLog.center_id == actor.center_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="업무수행일지를 찾을 수 없습니다")
    resident = _resident(db, log.resident_id, actor.center_id)
    author = db.query(User).filter(User.id == log.author_id).first()
    latest = db.query(NeedsAssessment).filter(NeedsAssessment.resident_id == resident.id)         .order_by(NeedsAssessment.assessed_date.desc(), NeedsAssessment.id.desc()).first()
    return {"status": "success", "data": {
        "resident_name": resident.name,
        "needs_assessment": assessment_to_dict(latest, None) if latest else None,
        "recognition_number": resident.recognition_number,
        "care_grade": resident.care_grade,
        "visited_at": log.visited_at.strftime("%Y-%m-%d %H:%M"),
        "author_name": author.full_name if author else "",
        "counseling_target": log.counseling_target,
        "counseling_result": log.counseling_result,
        "content": log.content,
    }}


@router.post("/monitoring")
def record_monitoring(body: MonitoringBody, db: Session = Depends(get_db), actor: User = Depends(require_social_or_manager)):
    _resident(db, body.resident_id, actor.center_id)
    if body.visit_date.strftime("%Y-%m") != body.year_month:
        raise HTTPException(status_code=400, detail="방문일이 기록 월(YYYY-MM)과 맞지 않습니다")
    exists = db.query(MonthlyMonitoring).filter(MonthlyMonitoring.resident_id == body.resident_id,
                                                MonthlyMonitoring.year_month == body.year_month).first()
    if exists:
        raise HTTPException(status_code=409, detail="이 달의 방문 확인 기록이 이미 있습니다")
    row = MonthlyMonitoring(center_id=actor.center_id, resident_id=body.resident_id, year_month=body.year_month,
                            visit_date=body.visit_date.date(), author_id=actor.id, service_checked=body.service_checked,
                            note=(body.note or "").strip() or None)
    db.add(row)
    db.commit()
    return {"status": "success", "data": {"id": row.id, "resident_id": row.resident_id, "year_month": row.year_month}}


@router.get("/monitoring/status")
def monitoring_status(year_month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), db: Session = Depends(get_db),
                      actor: User = Depends(require_social_or_manager)):
    """이번 달 방문 확인이 빠진 이용자 목록 (고시 제57조: 가산 대상 모든 수급자 매월 1회 이상)."""
    residents = db.query(Resident).filter(Resident.center_id == actor.center_id).all()
    done = {m.resident_id for m in db.query(MonthlyMonitoring).filter(MonthlyMonitoring.center_id == actor.center_id,
                                                                     MonthlyMonitoring.year_month == year_month).all()}
    return {"status": "success", "data": {
        "year_month": year_month,
        "done": [{"resident_id": r.id, "name": r.name} for r in residents if r.id in done],
        "missing": [{"resident_id": r.id, "name": r.name} for r in residents if r.id not in done],
    }}


class PlanBody(BaseModel):
    resident_id: int
    planned_date: date
    note: Optional[str] = Field(None, max_length=200)


@router.post("/visit-plans")
def add_plan(body: PlanBody, db: Session = Depends(get_db), actor: User = Depends(require_social_or_manager)):
    _resident(db, body.resident_id, actor.center_id)
    row = SocialVisitPlan(center_id=actor.center_id, resident_id=body.resident_id, author_id=actor.id,
                          planned_date=body.planned_date, note=(body.note or "").strip() or None)
    db.add(row)
    db.commit()
    return {"status": "success", "data": {"id": row.id}}


@router.get("/visit-plans")
def list_plans(from_date: date = Query(...), to_date: date = Query(...), db: Session = Depends(get_db),
               actor: User = Depends(require_social_or_manager)):
    rows = db.query(SocialVisitPlan).filter(SocialVisitPlan.center_id == actor.center_id,
                                            SocialVisitPlan.planned_date >= from_date, SocialVisitPlan.planned_date <= to_date)         .order_by(SocialVisitPlan.planned_date).all()
    names = {r.id: r.name for r in db.query(Resident).filter(Resident.center_id == actor.center_id).all()}
    return {"status": "success", "data": [
        {"id": r.id, "resident_id": r.resident_id, "resident_name": names.get(r.resident_id, ""),
         "planned_date": r.planned_date.isoformat(), "note": r.note, "done": bool(r.done)} for r in rows]}


class DoneBody(BaseModel):
    service_checked: bool = True
    note: Optional[str] = Field(None, max_length=500)


@router.post("/visit-plans/{plan_id}/done")
def mark_done(plan_id: int, body: Optional[DoneBody] = None, db: Session = Depends(get_db),
              actor: User = Depends(require_social_or_manager)):
    """방문 예정을 완료하면 같은 달 월 방문 확인 기록도 함께 남긴다. 이미 그 달 기록이 있으면 새로 만들지 않는다."""
    row = db.query(SocialVisitPlan).filter(SocialVisitPlan.id == plan_id, SocialVisitPlan.center_id == actor.center_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="방문 예정을 찾을 수 없습니다")
    body = body or DoneBody()
    row.done = True
    year_month = row.planned_date.strftime("%Y-%m")
    exists = db.query(MonthlyMonitoring).filter(MonthlyMonitoring.resident_id == row.resident_id,
                                                MonthlyMonitoring.year_month == year_month).first()
    created = exists is None
    if created:
        db.add(MonthlyMonitoring(center_id=actor.center_id, resident_id=row.resident_id, year_month=year_month,
                                 visit_date=row.planned_date, author_id=actor.id, service_checked=body.service_checked,
                                 note=(body.note or "").strip() or "방문 예정 완료에서 기록"))
    db.commit()
    return {"status": "success", "data": {"monitoring_created": created}}
