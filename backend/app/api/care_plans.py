"""급여제공계획서 - 작성, 변경 이력, 보호자 확인서명·공단 통보일 기록, 이용자별 점검.

근거: 공단 2026년 재가급여(방문요양) 평가매뉴얼 방문요양 16(급여제공계획 수립 및 제공)·17(급여제공계획 변경).
- 연 1회 이상 작성(회계연도 기준), 신규수급자는 급여개시일까지
- 기관이 실시한 욕구사정·낙상평가·욕창평가·인지기능평가를 반영 - 계획 작성 전에 실시한 평가만 인정
- 수급자(보호자)에게 설명하고 확인서명을 받아 급여제공 시작일까지 공단에 통보
- 변경 계획서는 변경 사유를 기록하고, 변경 계획도 설명·서명·통보
공단 통보 자체는 장기요양정보시스템에서 센터가 직접 하므로 여기서는 통보한 날짜만 기록한다.
"""
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.notifications import notify
from app.auth import get_current_user, require_manager, require_social_or_manager
from app.database import get_db
from app.care_plan_entry import entry_sheet
from app.models import CarePlan, CarePlanAck, Center, NeedsAssessment, Resident, RiskAssessment, User

router = APIRouter()

PLAN_TYPES = {"regular": "신규·정기", "change": "변경"}
ASSESSMENT_LOOKBACK_DAYS = 400  # 계획 작성 전 이만큼 안에 실시한 평가를 반영 대상으로 찾는다


class PlanBody(BaseModel):
    resident_id: int
    plan_type: str = "regular"
    change_reason: Optional[str] = None
    written_date: date
    service_start_date: Optional[date] = None
    service_type: str = "방문요양"
    goals: str
    needs: str
    details: str
    frequency: str
    duration_minutes: Optional[int] = None
    opinion: str


class ProgressBody(BaseModel):
    guardian_signed_date: Optional[date] = None
    guardian_signer: Optional[str] = None
    nhis_notified_date: Optional[date] = None


def _latest_assessments(db: Session, resident_id: int, on_or_before: date) -> dict:
    """계획 작성일 이전에 실시한 가장 최근 평가 4종 (없으면 None)."""
    since = on_or_before - timedelta(days=ASSESSMENT_LOOKBACK_DAYS)

    def risk(kind):
        return db.query(RiskAssessment).filter(
            RiskAssessment.resident_id == resident_id, RiskAssessment.assessment_type == kind,
        ).order_by(RiskAssessment.assessed_date.desc()).all()

    def pick(rows):
        for r in rows:
            d = r.assessed_date.date() if hasattr(r.assessed_date, "date") else r.assessed_date
            if d and since <= d <= on_or_before:
                return r
        return None

    needs = db.query(NeedsAssessment).filter(NeedsAssessment.resident_id == resident_id).order_by(NeedsAssessment.assessed_date.desc()).all()
    return {
        "needs": pick(needs), "fall": pick(risk("fall_risk")),
        "pressure": pick(risk("pressure_sore_risk")), "cognitive": pick(risk("cognitive_function")),
    }


MISSING_LABEL = {"needs": "욕구사정", "fall": "낙상위험도 평가", "pressure": "욕창위험도 평가", "cognitive": "인지기능 평가"}


def _plan_issues(plan: CarePlan, db: Session) -> list:
    issues = []
    for key, col in (("needs", plan.needs_assessment_id), ("fall", plan.fall_assessment_id),
                     ("pressure", plan.pressure_assessment_id), ("cognitive", plan.cognitive_assessment_id)):
        if not col:
            issues.append(f"{MISSING_LABEL[key]}를 계획 작성일 이전에 실시한 기록이 없습니다 (계획에 반영된 평가만 인정)")
    if not plan.guardian_signed_date:
        issues.append("수급자(보호자) 설명·확인서명 기록이 없습니다")
    if not plan.nhis_notified_date:
        issues.append("공단 통보일이 기록되지 않았습니다")
    elif plan.service_start_date and plan.nhis_notified_date > plan.service_start_date:
        issues.append(f"공단 통보({plan.nhis_notified_date})가 급여제공 시작일({plan.service_start_date})보다 늦었습니다")
    if plan.guardian_signed_date and plan.service_start_date and plan.guardian_signed_date > plan.service_start_date:
        issues.append(f"확인서명({plan.guardian_signed_date})이 급여제공 시작일({plan.service_start_date})보다 늦었습니다")
    resident = db.query(Resident).filter(Resident.id == plan.resident_id).first()
    if resident and resident.primary_caregiver_id and not db.query(CarePlanAck).filter(
            CarePlanAck.plan_id == plan.id, CarePlanAck.caregiver_id == resident.primary_caregiver_id).first():
        issues.append("담당 요양보호사가 이 계획서를 아직 확인하지 않았습니다 (요양보호사는 서비스 제공 전에 계획 내용을 숙지해야 합니다)")
    return issues


def _to_dict(plan: CarePlan, db: Session, author_name: Optional[str] = None) -> dict:
    return {
        "id": plan.id, "resident_id": plan.resident_id, "plan_type": plan.plan_type,
        "plan_type_label": PLAN_TYPES.get(plan.plan_type, plan.plan_type), "parent_id": plan.parent_id,
        "change_reason": plan.change_reason, "service_type": plan.service_type,
        "written_date": plan.written_date.isoformat() if plan.written_date else None,
        "author_name": author_name,
        "service_start_date": plan.service_start_date.isoformat() if plan.service_start_date else None,
        "goals": plan.goals, "needs": plan.needs, "details": plan.details, "frequency": plan.frequency,
        "duration_minutes": plan.duration_minutes, "opinion": plan.opinion,
        "assessments": {"needs": plan.needs_assessment_id, "fall": plan.fall_assessment_id,
                        "pressure": plan.pressure_assessment_id, "cognitive": plan.cognitive_assessment_id},
        "guardian_signed_date": plan.guardian_signed_date.isoformat() if plan.guardian_signed_date else None,
        "guardian_signer": plan.guardian_signer,
        "nhis_notified_date": plan.nhis_notified_date.isoformat() if plan.nhis_notified_date else None,
        "shared_at": plan.shared_at.isoformat() if plan.shared_at else None,
        "signed_via": plan.signed_via,
        "has_signature": bool(plan.guardian_signature),
        "caregiver_ack": _ack_info(plan, db),
        "issues": _plan_issues(plan, db),
    }


def _ack_info(plan: CarePlan, db: Session) -> Optional[dict]:
    resident = db.query(Resident).filter(Resident.id == plan.resident_id).first()
    if not resident or not resident.primary_caregiver_id:
        return None
    caregiver = db.query(User).filter(User.id == resident.primary_caregiver_id).first()
    ack = db.query(CarePlanAck).filter(CarePlanAck.plan_id == plan.id, CarePlanAck.caregiver_id == resident.primary_caregiver_id).first()
    return {"caregiver_name": caregiver.full_name if caregiver else None,
            "acknowledged_at": ack.acknowledged_at.isoformat() if ack else None}


@router.post("")
def create_plan(body: PlanBody, db: Session = Depends(get_db), actor: User = Depends(require_social_or_manager)):
    if body.plan_type not in PLAN_TYPES:
        raise HTTPException(status_code=400, detail="계획서 종류가 올바르지 않습니다")
    resident = db.query(Resident).filter(Resident.id == body.resident_id).first()
    if not resident or resident.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    for label, value in (("장기요양 세부목표", body.goals), ("장기요양 필요내용", body.needs), ("세부제공내용", body.details),
                         ("횟수", body.frequency), ("종합의견", body.opinion)):
        if not (value or "").strip():
            raise HTTPException(status_code=400, detail=f"{label}을(를) 입력해 주세요")
    if body.plan_type == "change" and not (body.change_reason or "").strip():
        raise HTTPException(status_code=400, detail="변경 계획서는 변경 사유(기능상태 변화, 수급자 욕구, 보호자 요구 등)를 기록해야 합니다")

    previous = db.query(CarePlan).filter(CarePlan.resident_id == body.resident_id).order_by(CarePlan.written_date.desc(), CarePlan.id.desc()).first()
    if body.plan_type == "change" and not previous:
        raise HTTPException(status_code=400, detail="변경할 기존 계획서가 없습니다. 신규·정기 계획서를 먼저 작성해 주세요")

    found = _latest_assessments(db, body.resident_id, body.written_date)
    plan = CarePlan(
        center_id=actor.center_id, resident_id=body.resident_id, plan_type=body.plan_type,
        parent_id=previous.id if (body.plan_type == "change" and previous) else None,
        change_reason=(body.change_reason or "").strip() or None, service_type=body.service_type,
        written_date=body.written_date, author_id=actor.id, service_start_date=body.service_start_date,
        goals=body.goals.strip(), needs=body.needs.strip(), details=body.details.strip(), frequency=body.frequency.strip(),
        duration_minutes=body.duration_minutes, opinion=body.opinion.strip(),
        needs_assessment_id=found["needs"].id if found["needs"] else None,
        fall_assessment_id=found["fall"].id if found["fall"] else None,
        pressure_assessment_id=found["pressure"].id if found["pressure"] else None,
        cognitive_assessment_id=found["cognitive"].id if found["cognitive"] else None,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return {"status": "success", "data": _to_dict(plan, db, actor.full_name)}


@router.get("")
def list_plans(resident_id: int, db: Session = Depends(get_db), actor: User = Depends(require_social_or_manager)):
    resident = db.query(Resident).filter(Resident.id == resident_id).first()
    if not resident or resident.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    plans = db.query(CarePlan).filter(CarePlan.resident_id == resident_id).order_by(CarePlan.written_date.desc(), CarePlan.id.desc()).all()
    authors = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}
    return {"plans": [_to_dict(p, db, authors.get(p.author_id)) for p in plans]}


@router.put("/{plan_id}/progress")
def update_progress(plan_id: int, body: ProgressBody, db: Session = Depends(get_db), actor: User = Depends(require_social_or_manager)):
    """보호자 설명·확인서명일과 공단 통보일을 기록한다."""
    plan = db.query(CarePlan).filter(CarePlan.id == plan_id, CarePlan.center_id == actor.center_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="계획서를 찾을 수 없습니다")
    if body.guardian_signed_date is not None:
        plan.guardian_signed_date = body.guardian_signed_date
        plan.guardian_signer = (body.guardian_signer or "").strip() or None
    if body.nhis_notified_date is not None:
        plan.nhis_notified_date = body.nhis_notified_date
    db.commit()
    return {"status": "success", "data": _to_dict(plan, db)}


@router.get("/{plan_id}/entry-sheet")
def plan_entry_sheet(plan_id: int, db: Session = Depends(get_db), actor: User = Depends(require_social_or_manager)):
    """공단 급여제공계획서 전산 등록 화면 순서대로 옮겨 적을 내용 (엑셀 업로드 대신 쓰는 입력 보조, 시스템에 전송하지 않음)."""
    plan = db.query(CarePlan).filter(CarePlan.id == plan_id, CarePlan.center_id == actor.center_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="계획서를 찾을 수 없습니다")
    resident = db.query(Resident).filter(Resident.id == plan.resident_id).first()
    return {"status": "success", "data": {"resident_name": resident.name if resident else "", **entry_sheet(plan, resident)}}


@router.get("/{plan_id}/form")
def plan_form(plan_id: int, db: Session = Depends(get_db), actor: User = Depends(require_social_or_manager)):
    """장기요양급여 제공 계획서(별지 제11호의3서식) 출력용 값. 시스템에 없는 칸(계약일·계약기간·이용계획서 번호·전화번호 등)은 비워 둔다."""
    plan = db.query(CarePlan).filter(CarePlan.id == plan_id, CarePlan.center_id == actor.center_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="계획서를 찾을 수 없습니다")
    resident = db.query(Resident).filter(Resident.id == plan.resident_id).first()
    center = db.query(Center).filter(Center.id == actor.center_id).first()
    author = db.query(User).filter(User.id == plan.author_id).first() if plan.author_id else None
    return {"status": "success", "data": {
        "center_name": center.name if center else "",
        "resident": {
            "name": resident.name if resident else "",
            "birth_date": resident.birth_date.isoformat() if resident and resident.birth_date else "",
            "guardian_phone": resident.guardian_phone if resident else "",
            "care_grade": resident.care_grade if resident else None,
            "recognition_number": resident.recognition_number if resident else "",
            "recognition_start": resident.recognition_start.isoformat() if resident and resident.recognition_start else "",
            "recognition_end": resident.recognition_end.isoformat() if resident and resident.recognition_end else "",
        },
        "plan": {
            "plan_type": plan.plan_type, "change_reason": plan.change_reason, "service_type": plan.service_type or "방문요양",
            "written_date": plan.written_date.isoformat() if plan.written_date else "",
            "service_start_date": plan.service_start_date.isoformat() if plan.service_start_date else "",
            "nhis_notified_date": plan.nhis_notified_date.isoformat() if plan.nhis_notified_date else "",
            "goals": plan.goals or "", "needs": plan.needs or "", "details": plan.details or "",
            "frequency": plan.frequency or "",
            "duration_minutes": plan.duration_minutes,
            "opinion": plan.opinion or "",
            "author_name": author.full_name if author else "",
            "guardian_signer": plan.guardian_signer or "",
            "guardian_signed_date": plan.guardian_signed_date.isoformat() if plan.guardian_signed_date else "",
        },
    }}


@router.delete("/{plan_id}")
def delete_plan(plan_id: int, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    plan = db.query(CarePlan).filter(CarePlan.id == plan_id, CarePlan.center_id == actor.center_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="계획서를 찾을 수 없습니다")
    if db.query(CarePlan).filter(CarePlan.parent_id == plan_id).first():
        raise HTTPException(status_code=400, detail="이 계획서를 기준으로 작성된 변경 계획서가 있어 삭제할 수 없습니다")
    db.delete(plan)
    db.commit()
    return {"status": "success"}


def center_plan_status(db: Session, center_id: int, today: date) -> dict:
    """이용자별로 올해 계획서가 있는지, 가장 최근 계획서에 빠진 것이 없는지 점검한다."""
    year_start = date(today.year, 1, 1)
    residents = db.query(Resident).filter(Resident.center_id == center_id).order_by(Resident.name).all()
    plans = db.query(CarePlan).filter(CarePlan.center_id == center_id).order_by(CarePlan.written_date.desc(), CarePlan.id.desc()).all()
    latest = {}
    this_year = set()
    for p in plans:
        latest.setdefault(p.resident_id, p)
        if p.written_date and p.written_date >= year_start:
            this_year.add(p.resident_id)
    rows = []
    for r in residents:
        p = latest.get(r.id)
        rows.append({
            "resident_id": r.id, "resident_name": r.name,
            "has_plan": p is not None, "has_plan_this_year": r.id in this_year,
            "latest_written_date": p.written_date.isoformat() if p and p.written_date else None,
            "latest_plan_type": PLAN_TYPES.get(p.plan_type) if p else None,
            "issues": _plan_issues(p, db) if p else [],
        })
    return {
        "year": today.year, "residents": rows,
        "no_plan_this_year": sum(1 for x in rows if not x["has_plan_this_year"]),
        "with_issues": sum(1 for x in rows if x["has_plan"] and x["issues"]),
    }


@router.get("/status")
def get_status(db: Session = Depends(get_db), actor: User = Depends(require_social_or_manager)):
    return center_plan_status(db, actor.center_id, date.today())


# ---------------- 보호자 확인·전자서명 / 요양보호사 확인 ----------------

class SignBody(BaseModel):
    signer_name: str
    relation: str
    signature: str  # PNG data URL


def _guardian_view(plan: CarePlan, resident: Resident) -> dict:
    """보호자·요양보호사에게는 계획 내용과 서명 상태만 보여준다 (센터 내부 점검 항목은 제외)."""
    return {
        "id": plan.id, "resident_id": plan.resident_id, "resident_name": resident.name,
        "plan_type_label": PLAN_TYPES.get(plan.plan_type, plan.plan_type), "change_reason": plan.change_reason,
        "service_type": plan.service_type, "written_date": plan.written_date.isoformat() if plan.written_date else None,
        "service_start_date": plan.service_start_date.isoformat() if plan.service_start_date else None,
        "goals": plan.goals, "needs": plan.needs, "details": plan.details, "frequency": plan.frequency,
        "duration_minutes": plan.duration_minutes, "opinion": plan.opinion,
        "shared_at": plan.shared_at.isoformat() if plan.shared_at else None,
        "signed": bool(plan.guardian_signed_date),
        "guardian_signed_date": plan.guardian_signed_date.isoformat() if plan.guardian_signed_date else None,
        "guardian_signer": plan.guardian_signer,
    }


@router.post("/{plan_id}/share")
def share_with_guardian(plan_id: int, db: Session = Depends(get_db), actor: User = Depends(require_social_or_manager)):
    """계획서를 설명한 뒤 보호자에게 확인·서명을 요청한다 (이때부터 보호자 화면에 보인다)."""
    plan = db.query(CarePlan).filter(CarePlan.id == plan_id, CarePlan.center_id == actor.center_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="계획서를 찾을 수 없습니다")
    resident = db.query(Resident).filter(Resident.id == plan.resident_id).first()
    if not resident or not resident.guardian_id:
        raise HTTPException(status_code=400, detail="이 이용자에게 연결된 보호자 계정이 없습니다. 보호자 초대 후 요청하거나 서명일을 직접 기록해 주세요")
    plan.shared_at = datetime.now()
    notify(db, resident.guardian_id, "care_plan_request",
           f"{resident.name} 어르신의 급여제공계획서가 도착했습니다. 내용을 확인하고 서명해 주세요.")
    db.commit()
    return {"status": "success", "data": _to_dict(plan, db)}


@router.get("/guardian")
def guardian_plans(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role != "guardian":
        raise HTTPException(status_code=403, detail="보호자만 이용할 수 있습니다")
    residents = {r.id: r for r in db.query(Resident).filter(Resident.guardian_id == actor.id).all()}
    if not residents:
        return {"plans": []}
    plans = db.query(CarePlan).filter(CarePlan.resident_id.in_(list(residents)), CarePlan.shared_at.isnot(None)).order_by(
        CarePlan.written_date.desc(), CarePlan.id.desc()).limit(30).all()
    return {"plans": [_guardian_view(p, residents[p.resident_id]) for p in plans]}


@router.post("/{plan_id}/sign")
def guardian_sign(plan_id: int, body: SignBody, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role != "guardian":
        raise HTTPException(status_code=403, detail="보호자만 서명할 수 있습니다")
    plan = db.query(CarePlan).filter(CarePlan.id == plan_id).first()
    resident = db.query(Resident).filter(Resident.id == plan.resident_id).first() if plan else None
    if not plan or not resident or resident.guardian_id != actor.id or not plan.shared_at:
        raise HTTPException(status_code=404, detail="서명할 계획서를 찾을 수 없습니다")
    if plan.guardian_signed_date:
        raise HTTPException(status_code=400, detail="이미 서명한 계획서입니다")
    if not body.signer_name.strip() or not body.relation.strip():
        raise HTTPException(status_code=400, detail="서명자 이름과 수급자와의 관계를 입력해 주세요")
    if not body.signature.startswith("data:image/png;base64,") or len(body.signature) < 400:
        raise HTTPException(status_code=400, detail="서명란에 직접 서명해 주세요")
    if len(body.signature) > 700_000:
        raise HTTPException(status_code=400, detail="서명 이미지가 너무 큽니다")
    plan.guardian_signed_date = date.today()
    plan.guardian_signer = f"{body.signer_name.strip()}({body.relation.strip()})"
    plan.guardian_signature = body.signature
    plan.signed_via = "app"
    for manager in db.query(User).filter(User.center_id == plan.center_id, User.role == "center_manager").all():
        notify(db, manager.id, "care_plan_signed",
               f"{resident.name} 어르신의 급여제공계획서에 {plan.guardian_signer}님이 서명했습니다. 공단 통보일을 기록해 주세요.")
    db.commit()
    return {"status": "success", "data": _guardian_view(plan, resident)}


@router.get("/mine")
def caregiver_plans(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """요양보호사: 내가 담당하는 이용자의 최신 급여제공계획과 내 확인 여부."""
    if actor.role != "caregiver":
        raise HTTPException(status_code=403, detail="요양보호사만 이용할 수 있습니다")
    out = []
    for r in db.query(Resident).filter(Resident.primary_caregiver_id == actor.id).all():
        plan = db.query(CarePlan).filter(CarePlan.resident_id == r.id).order_by(CarePlan.written_date.desc(), CarePlan.id.desc()).first()
        if not plan:
            continue
        ack = db.query(CarePlanAck).filter(CarePlanAck.plan_id == plan.id, CarePlanAck.caregiver_id == actor.id).first()
        item = _guardian_view(plan, r)
        item["acknowledged_at"] = ack.acknowledged_at.isoformat() if ack else None
        out.append(item)
    return {"plans": out}


@router.post("/{plan_id}/ack")
def caregiver_ack(plan_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role != "caregiver":
        raise HTTPException(status_code=403, detail="요양보호사만 확인할 수 있습니다")
    plan = db.query(CarePlan).filter(CarePlan.id == plan_id).first()
    resident = db.query(Resident).filter(Resident.id == plan.resident_id).first() if plan else None
    if not plan or not resident or resident.primary_caregiver_id != actor.id:
        raise HTTPException(status_code=404, detail="담당 이용자의 계획서만 확인할 수 있습니다")
    if not db.query(CarePlanAck).filter(CarePlanAck.plan_id == plan_id, CarePlanAck.caregiver_id == actor.id).first():
        db.add(CarePlanAck(plan_id=plan_id, caregiver_id=actor.id))
        db.commit()
    return {"status": "success"}


@router.get("/{plan_id}/signature")
def plan_signature(plan_id: int, db: Session = Depends(get_db), actor: User = Depends(require_social_or_manager)):
    """평가 준비·인쇄용: 보호자가 전자서명한 이미지를 센터장만 열람한다."""
    plan = db.query(CarePlan).filter(CarePlan.id == plan_id, CarePlan.center_id == actor.center_id).first()
    if not plan or not plan.guardian_signature:
        raise HTTPException(status_code=404, detail="전자서명이 없습니다")
    return {"signature": plan.guardian_signature, "signer": plan.guardian_signer, "signed_date": plan.guardian_signed_date.isoformat()}
