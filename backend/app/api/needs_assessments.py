import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import NeedsAssessment, Resident, User

router = APIRouter()

# 공단 표준 욕구사정 서식 기준 (케어포 데모 화면 구조 참고)
DISEASE_LABELS = {
    "stroke": "뇌졸중(뇌출혈,뇌경색 등)", "dementia": "치매", "parkinson": "파킨슨병", "depression": "우울증",
    "hypertension": "고혈압", "angina": "협심증", "mi": "심근경색증", "asthma": "천식", "copd": "만성폐쇄성폐질환",
    "diabetes": "당뇨", "hyperlipidemia": "고지혈증",
    "arthritis": "관절염(퇴행성,류마티스)", "osteoporosis": "골다공증", "fracture_sequela": "골절·탈골 등 사고로 인한 후유증",
    "ckd": "만성신부전", "uti": "요로감염", "cystitis": "만성방광염", "bph": "전립선비대",
    "cataract": "백내장", "glaucoma": "녹내장", "hearing_loss": "난청", "chronic_otitis": "만성중이염", "tinnitus": "이명",
    "tb": "결핵", "scabies": "옴",
}
NUTRITION_DETAIL_LABELS = {"appetite_loss": "식욕부진", "weight_loss": "체중감소", "weight_gain": "체중과다"}
MOBILITY_LABELS = {
    "independent": "자립보행 가능", "independent_with_device": "보장구를 사용하여 자립보행 가능",
    "assisted": "부축해주면 보행 가능", "assisted_with_device": "보장구를 사용하여 부축을 받아 보행 가능",
    "unable": "보행 불가",
}
FUNCTION_ITEMS = {
    "stand_up": "바닥에 앉은 상태에서 일어서기", "sit_up": "누운 상태에서 몸 일으켜 앉기",
    "eating": "식사하기", "washing_face": "세수하기", "brushing_teeth": "양치질하기", "toileting": "화장실 이용하기",
}
FUNCTION_LEVEL_LABELS = {"alone": "혼자 수행", "guided": "지시(준비)도움", "assisted": "직접(부축)도움", "unable": "전혀 수행할 수 없음"}


class NeedsAssessmentCreate(BaseModel):
    resident_id: int
    diseases: str = ""  # 쉼표 구분 코드
    nutrition_status: Optional[str] = None
    nutrition_detail: str = ""  # 쉼표 구분 코드
    mobility_status: Optional[str] = None
    function_status: dict = {}  # {"stand_up": "alone", ...}
    notes: str = ""


def _to_dict(a: NeedsAssessment, assessor_name: Optional[str] = None) -> dict:
    try:
        function_status = json.loads(a.function_status) if a.function_status else {}
    except (ValueError, TypeError):
        function_status = {}
    return {
        "id": a.id,
        "resident_id": a.resident_id,
        "assessed_by": a.assessed_by,
        "assessed_by_name": assessor_name,
        "assessed_date": a.assessed_date.isoformat() if a.assessed_date else None,
        "diseases": [c for c in (a.diseases or "").split(",") if c],
        "diseases_label": [DISEASE_LABELS.get(c, c) for c in (a.diseases or "").split(",") if c],
        "nutrition_status": a.nutrition_status,
        "nutrition_detail": [c for c in (a.nutrition_detail or "").split(",") if c],
        "nutrition_detail_label": [NUTRITION_DETAIL_LABELS.get(c, c) for c in (a.nutrition_detail or "").split(",") if c],
        "mobility_status": a.mobility_status,
        "mobility_status_label": MOBILITY_LABELS.get(a.mobility_status),
        "function_status": function_status,
        "notes": a.notes,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("/options")
def get_options():
    """화면에서 쓸 코드표 (라벨은 서버가 기준이다 - 프론트엔드에 따로 베끼지 않는다)"""
    return {
        "diseases": DISEASE_LABELS,
        "nutrition_detail": NUTRITION_DETAIL_LABELS,
        "mobility_status": MOBILITY_LABELS,
        "function_items": FUNCTION_ITEMS,
        "function_levels": FUNCTION_LEVEL_LABELS,
    }


@router.post("/")
def create_assessment(
    body: NeedsAssessmentCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """욕구조사 작성 (요양사·센터장). 매 방문이 아니라 주기 평가용이라 이력으로 계속 쌓인다."""
    if actor.role not in ("caregiver", "center_manager"):
        raise HTTPException(status_code=403, detail="요양사 또는 센터장만 작성할 수 있습니다")

    resident = db.query(Resident).filter(Resident.id == body.resident_id).first()
    if not resident or resident.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")

    if body.nutrition_status and body.nutrition_status not in ("good", "poor"):
        raise HTTPException(status_code=400, detail="영양상태 값이 올바르지 않습니다")
    if body.mobility_status and body.mobility_status not in MOBILITY_LABELS:
        raise HTTPException(status_code=400, detail="보행상태 값이 올바르지 않습니다")
    for level in body.function_status.values():
        if level not in FUNCTION_LEVEL_LABELS:
            raise HTTPException(status_code=400, detail="기능상태 값이 올바르지 않습니다")

    assessment = NeedsAssessment(
        resident_id=body.resident_id,
        assessed_by=actor.id,
        assessed_date=datetime.utcnow(),
        diseases=body.diseases or None,
        nutrition_status=body.nutrition_status,
        nutrition_detail=body.nutrition_detail or None,
        mobility_status=body.mobility_status,
        function_status=json.dumps(body.function_status, ensure_ascii=False) if body.function_status else None,
        notes=body.notes or None,
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return {"status": "success", "message": "욕구조사가 저장되었습니다", "data": _to_dict(assessment, actor.full_name)}


@router.get("/resident/{resident_id}")
def list_assessments(
    resident_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """한 이용자의 욕구조사 이력 (최신순)"""
    resident = db.query(Resident).filter(Resident.id == resident_id).first()
    if not resident or resident.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")

    rows = (
        db.query(NeedsAssessment)
        .filter(NeedsAssessment.resident_id == resident_id)
        .order_by(NeedsAssessment.assessed_date.desc())
        .all()
    )
    assessors = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}
    return {"assessments": [_to_dict(a, assessors.get(a.assessed_by)) for a in rows]}
