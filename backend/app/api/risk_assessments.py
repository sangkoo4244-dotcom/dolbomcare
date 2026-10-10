from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import RiskAssessment, Resident, User

router = APIRouter()

# 공단이 반기(6개월)마다 요구하는 표준 위험도/기능평가 항목들.
# 구체적인 체크리스트 문항·배점표는 공식 서식을 확보하기 전까지는 반영하지 않고,
# 점수와 위험군만 센터가 직접 입력하는 틀만 제공한다 (문항은 나중에 추가 가능).
ASSESSMENT_TYPES = {
    "fall_risk": "낙상위험도",
    "pressure_sore_risk": "욕창위험도",
    "cognitive_function": "인지기능평가",
}
CADENCE_DAYS = 183  # 반기 1회


def _to_dict(a: RiskAssessment, assessor_name: Optional[str] = None) -> dict:
    return {
        "id": a.id,
        "resident_id": a.resident_id,
        "assessment_type": a.assessment_type,
        "assessed_by": a.assessed_by,
        "assessed_by_name": assessor_name,
        "assessed_date": a.assessed_date.isoformat() if a.assessed_date else None,
        "score": a.score,
        "risk_level": a.risk_level,
        "notes": a.notes,
    }


@router.get("/options")
def get_options():
    return {"assessment_types": ASSESSMENT_TYPES}


class RiskAssessmentCreate(BaseModel):
    resident_id: int
    assessment_type: str
    score: Optional[int] = None
    risk_level: Optional[str] = None  # 'low', 'high'
    notes: str = ""


@router.post("/")
def create_risk_assessment(
    body: RiskAssessmentCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """낙상위험도·욕창위험도·인지기능평가 기록 (요양사·센터장). 반기마다 쌓이는 이력이다."""
    if actor.role not in ("caregiver", "center_manager"):
        raise HTTPException(status_code=403, detail="요양사 또는 센터장만 작성할 수 있습니다")
    if body.assessment_type not in ASSESSMENT_TYPES:
        raise HTTPException(status_code=400, detail="평가 종류가 올바르지 않습니다")
    if body.risk_level and body.risk_level not in ("low", "high"):
        raise HTTPException(status_code=400, detail="위험군 값이 올바르지 않습니다")

    resident = db.query(Resident).filter(Resident.id == body.resident_id).first()
    if not resident or resident.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")

    assessment = RiskAssessment(
        resident_id=body.resident_id,
        assessment_type=body.assessment_type,
        assessed_by=actor.id,
        assessed_date=datetime.utcnow(),
        score=body.score,
        risk_level=body.risk_level,
        notes=body.notes or None,
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return {"status": "success", "data": _to_dict(assessment, actor.full_name)}


@router.get("/resident/{resident_id}")
def list_risk_assessments(
    resident_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """한 이용자의 위험도/기능평가 현황. 종류별로 최신 평가 + 다음 평가 기한 + 이력을 묶어 돌려준다."""
    resident = db.query(Resident).filter(Resident.id == resident_id).first()
    if not resident or resident.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")

    rows = (
        db.query(RiskAssessment)
        .filter(RiskAssessment.resident_id == resident_id)
        .order_by(RiskAssessment.assessed_date.desc())
        .all()
    )
    assessors = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}

    now = datetime.utcnow()
    result = {}
    for code, label in ASSESSMENT_TYPES.items():
        history = [_to_dict(a, assessors.get(a.assessed_by)) for a in rows if a.assessment_type == code]
        latest = history[0] if history else None
        if latest and latest["assessed_date"]:
            next_due = datetime.fromisoformat(latest["assessed_date"]) + timedelta(days=CADENCE_DAYS)
            is_overdue = next_due < now
            next_due_date = next_due.date().isoformat()
        else:
            is_overdue = True  # 한 번도 평가한 적이 없으면 미실시로 간주
            next_due_date = None
        result[code] = {
            "type": code,
            "type_label": label,
            "latest": latest,
            "next_due_date": next_due_date,
            "is_overdue": is_overdue,
            "history": history,
        }
    return {"resident_name": resident.name, "assessments": result}
