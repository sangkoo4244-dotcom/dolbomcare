import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import RiskAssessment, Resident, User

router = APIRouter()

# 공단 2026년 재가급여 평가매뉴얼(방문요양) "위험도 평가" 지표 - 반기별 1회 이상 실시.
# 공단은 특정 배점표를 지정하지 않고 "검증된 도구(관련학회·논문 발표 도구)"를 쓰도록 요구하며,
# 매뉴얼이 예시로 든 도구는 다음과 같다:
#   낙상: Huhn의 낙상위험도 평가도구, Morse Fall Scale, Bobath Memorial Hospital Fall Risk Assessment Scales
#   욕창: Braden scale, Norton scale, Gosnell scale, Knoll scale
#   인지기능: CIST(인지선별검사), K-MMSE, MMSE-K
# 여기서는 그중 가장 널리 쓰이고 국제적으로 표준화된 Morse Fall Scale과 Braden Scale을 체크리스트로
# 구현한다. 인지기능평가는 검사 자체(그림检사 등 포함)가 복잡하고 일부 도구는 중앙치매센터 교육
# 이수가 필요해 앱 안에서 검사를 대신하지 않고, 점수·도구명 기록과 공단이 인정하는 대체 경로
# (치매진단+투약 확인)만 지원한다.
ASSESSMENT_TYPES = {
    "fall_risk": "낙상위험도",
    "pressure_sore_risk": "욕창위험도",
    "cognitive_function": "인지기능평가",
}
CADENCE_DAYS = 183  # 반기 1회

# Morse Fall Scale: 6개 항목, 0~125점. 25점 이상부터 표준 낙상예방조치 강화가 권고된다.
MORSE_FALL_ITEMS = {
    "history": {"label": "낙상 경험 (최근 3개월 이내)", "options": {"no": ["없음", 0], "yes": ["있음", 25]}},
    "secondary_diagnosis": {"label": "동반 진단 2개 이상", "options": {"no": ["아니오", 0], "yes": ["예", 15]}},
    "ambulatory_aid": {"label": "보행 보조기구", "options": {
        "none": ["없음·침상안정·휠체어·직원 부축", 0], "crutch_cane_walker": ["목발·지팡이·보행기", 15], "furniture": ["가구 짚고 이동", 30],
    }},
    "iv_therapy": {"label": "정맥주사·헤파린락 여부", "options": {"no": ["없음", 0], "yes": ["있음", 20]}},
    "gait": {"label": "보행 상태", "options": {
        "normal": ["정상·침상안정·부동", 0], "weak": ["약함", 10], "impaired": ["장애 있음", 20],
    }},
    "mental_status": {"label": "정신 상태", "options": {
        "aware": ["자신의 능력을 인지함", 0], "overestimates": ["자신의 능력을 과대평가·망각함", 15],
    }},
}

# Braden Scale: 6개 하위영역(마찰력과전단력만 1~3점, 나머지 1~4점), 총점 6~23점.
# 15점 이하를 욕창 위험군으로 본다 (6~9 최고위험 / 10~12 고위험 / 13~14 중등도위험 / 15~18 경도위험).
BRADEN_ITEMS = {
    "sensory_perception": {"label": "감각 인지", "options": {"1": ["완전 제한", 1], "2": ["매우 제한", 2], "3": ["약간 제한", 3], "4": ["제한 없음", 4]}},
    "moisture": {"label": "습기", "options": {"1": ["항상 습함", 1], "2": ["매우 습함", 2], "3": ["가끔 습함", 3], "4": ["거의 없음", 4]}},
    "activity": {"label": "활동", "options": {"1": ["와상", 1], "2": ["의자 이용", 2], "3": ["가끔 보행", 3], "4": ["자주 보행", 4]}},
    "mobility": {"label": "움직임", "options": {"1": ["완전 부동", 1], "2": ["매우 제한", 2], "3": ["약간 제한", 3], "4": ["제한 없음", 4]}},
    "nutrition": {"label": "영양", "options": {"1": ["매우 불량", 1], "2": ["부적절", 2], "3": ["적절", 3], "4": ["매우 양호", 4]}},
    "friction_shear": {"label": "마찰력과 전단력", "options": {"1": ["문제 있음", 1], "2": ["잠재적 문제", 2], "3": ["문제 없음", 3]}},
}

COGNITIVE_TOOLS = {
    "k_mmse": "K-MMSE / MMSE-K (간이정신상태검사)",
    "cist": "CIST (인지선별검사 - 중앙치매센터 교육 이수 필요)",
    "external": "외부 전문기관 검사 (병원·보건소·치매안심센터 등)",
    "dementia_dx_medication": "치매진단 + 복약 확인 서류로 대체 인정",
    "other": "기타 검증된 도구",
}


def _score_checklist(items: dict, selections: dict) -> int:
    total = 0
    for code, choice in (selections or {}).items():
        item = items.get(code)
        if not item or choice not in item["options"]:
            raise HTTPException(status_code=400, detail=f"잘못된 체크리스트 응답입니다 ({code})")
        total += item["options"][choice][1]
    return total


def _to_dict(a: RiskAssessment, assessor_name: Optional[str] = None) -> dict:
    try:
        item_scores = json.loads(a.item_scores) if a.item_scores else None
    except (ValueError, TypeError):
        item_scores = None
    return {
        "id": a.id,
        "resident_id": a.resident_id,
        "assessment_type": a.assessment_type,
        "assessed_by": a.assessed_by,
        "assessed_by_name": assessor_name,
        "assessed_date": a.assessed_date.isoformat() if a.assessed_date else None,
        "tool_name": a.tool_name,
        "score": a.score,
        "risk_level": a.risk_level,
        "item_scores": item_scores,
        "notes": a.notes,
    }


@router.get("/options")
def get_options():
    return {
        "assessment_types": ASSESSMENT_TYPES,
        "morse_fall_items": MORSE_FALL_ITEMS,
        "braden_items": BRADEN_ITEMS,
        "cognitive_tools": COGNITIVE_TOOLS,
    }


class RiskAssessmentCreate(BaseModel):
    resident_id: int
    assessment_type: str
    tool_name: Optional[str] = None  # 'morse_fall_scale', 'braden_scale', 또는 인지기능 도구 코드
    item_scores: Optional[dict] = None  # Morse/Braden 체크리스트 응답 {항목코드: 선택코드} - 있으면 점수를 서버가 계산한다
    score: Optional[int] = None  # item_scores가 없을 때(인지기능, 기타 도구) 직접 입력
    risk_level: Optional[str] = None  # 'low', 'high' - item_scores가 있으면 서버가 계산해 덮어쓴다
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

    score = body.score
    risk_level = body.risk_level
    item_scores_json = None

    # 체크리스트 응답이 있으면 점수·위험군은 서버가 표준 배점으로 직접 계산한다 (클라이언트 합산을 신뢰하지 않는다)
    if body.tool_name == "morse_fall_scale" and body.item_scores:
        score = _score_checklist(MORSE_FALL_ITEMS, body.item_scores)
        risk_level = "high" if score >= 25 else "low"
        item_scores_json = json.dumps(body.item_scores, ensure_ascii=False)
    elif body.tool_name == "braden_scale" and body.item_scores:
        score = _score_checklist(BRADEN_ITEMS, body.item_scores)
        risk_level = "high" if score <= 15 else "low"
        item_scores_json = json.dumps(body.item_scores, ensure_ascii=False)
    elif body.tool_name == "dementia_dx_medication":
        # 공단 매뉴얼상 치매진단+투약 확인 서류가 있으면 검사 없이도 '충족'으로 인정되는 경로 - 진단이 있다는 것 자체가 위험군을 뜻한다
        risk_level = risk_level or "high"

    assessment = RiskAssessment(
        resident_id=body.resident_id,
        assessment_type=body.assessment_type,
        assessed_by=actor.id,
        assessed_date=datetime.utcnow(),
        tool_name=body.tool_name,
        score=score,
        risk_level=risk_level,
        item_scores=item_scores_json,
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
