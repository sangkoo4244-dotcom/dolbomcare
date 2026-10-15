"""방문 일정·기록에 붙는 급여 종류(방문요양·방문목욕·방문간호)와 함께 가는 요양보호사를 검증하고 정리한다.

일정 만들기, 계획 제안, 방문 기록이 모두 같은 규칙을 쓰도록 한 곳에 둔다. 근거는 공단 고시(장기요양급여 제공기준 및 급여비용 산정방법 등에 관한 고시):
- 방문요양(제19조 ⑦): 기본은 요양보호사 1인. 수급자 상태상 불가피해 같은 기관 요양보호사 2인이 동시에 제공하면 요양보호사별로 각각 산정하고,
  급여제공기록지에 수급자 동의 내용과 당시 상태를 적어야 한다.
- 방문목욕(제24조·제26조): 요양보호사 2인 이상이 제공한다. 60분 이상 전액, 40~60분 80%, 40분 미만과 1인 단독 제공은 청구할 수 없다.
  예외로 차량 미이용 방문목욕에서 수치심 때문에 몸 씻기만 1인이 제공한 경우는 사유를 적고 80%/70%를 산정한다. 주 1회까지 산정한다.
- 방문간호(제27조): 간호직이 제공하고 방문간호지시서가 있어야 한다(지시서는 화면에서 확인 메모로 받고 막지는 않는다).
"""
from fastapi import HTTPException

from app import benefits
from app.billing_rules import VALID_DURATIONS
from app.models import Center, User

HOME_BENEFITS = ("home_care", "home_bath", "home_nursing")
NURSING_JOB_TYPES = ("간호사", "간호조무사", "치과위생사")
JOB_TYPES = ("요양보호사",) + NURSING_JOB_TYPES  # 직원 직종 선택지. 비어 있으면 요양보호사로 본다


def job_type_of(user) -> str:
    return (user.job_type or "요양보호사") if user else "요양보호사"


def _partner(db, co_caregiver_id, caregiver_id, center_id):
    """함께 가는 요양보호사: 본인이 아니고, 같은 센터의 요양보호사여야 한다(간호직은 안 된다)."""
    if co_caregiver_id == caregiver_id:
        return None
    co = db.query(User).filter(User.id == co_caregiver_id).first()
    if not co or co.role != "caregiver" or co.center_id != center_id or job_type_of(co) != "요양보호사":
        raise HTTPException(status_code=400, detail="함께 가는 요양보호사는 우리 센터의 요양보호사여야 합니다")
    return co


def normalize_visit_benefit(db, *, center_id, caregiver_id, benefit_type=None, bath_mode=None, co_caregiver_id=None,
                            duration_minutes=None, require_duration=False, strict_home_care_duration=False,
                            special_note=None, solo_exception=False, for_record=False) -> dict:
    """급여 종류와 그에 딸린 값을 검사해 {benefit_type, bath_mode, co_caregiver_id, solo_exception}로 돌려준다. 문제가 있으면 400.

    방문요양은 기존과 똑같이 동작하고(아무 값도 안 보내면 방문요양 1인), 방문목욕·방문간호는 센터가 제공 급여로 골라 둔 경우에만 쓸 수 있다.
    for_record=True는 청구가 만들어지는 방문 기록일 때다: 방문요양 시간을 정해진 값으로 제한하고(strict_home_care_duration),
    방문목욕은 40분 이상이어야 하며, 2인 동시 제공·1인 몸 씻기 예외에는 사유(special_note)가 있어야 한다.
    일정 계획은 시간 제한이 예전부터 없었으므로 그대로 두고 사유도 묻지 않는다."""
    benefit_type = benefit_type or "home_care"
    note = (special_note or "").strip()
    if benefit_type not in HOME_BENEFITS:
        raise HTTPException(status_code=400, detail="방문 급여 종류는 방문요양·방문목욕·방문간호 중에서 골라 주세요")

    if benefit_type != "home_care":
        center = db.query(Center).filter(Center.id == center_id).first() if center_id else None
        label = benefits.BY_CODE[benefit_type]["label"]
        if benefit_type not in benefits.enabled_codes(center.service_types if center else None):
            raise HTTPException(status_code=400, detail=f"{label}은(는) 센터 정보에서 제공 급여로 선택한 뒤 쓸 수 있습니다")

    caregiver = db.query(User).filter(User.id == caregiver_id).first() if caregiver_id else None

    if benefit_type == "home_care":
        if strict_home_care_duration and duration_minutes is not None and duration_minutes not in VALID_DURATIONS:
            raise HTTPException(status_code=400, detail=f"방문요양 제공 시간은 {', '.join(str(d) for d in VALID_DURATIONS)}분 중에서 골라 주세요")
        if require_duration and duration_minutes is None:
            raise HTTPException(status_code=400, detail="제공 시간을 골라 주세요")
        co = _partner(db, co_caregiver_id, caregiver_id, center_id) if co_caregiver_id else None
        if co and for_record and not note:
            raise HTTPException(status_code=400, detail="요양보호사 2인이 동시에 제공한 경우에는 수급자 동의 내용과 당시 상태를 적어 주세요")
        return {"benefit_type": "home_care", "bath_mode": None, "co_caregiver_id": co.id if co else None, "solo_exception": False}

    if benefit_type == "home_bath":
        if bath_mode not in benefits.HOME_BATH_FEES:
            raise HTTPException(status_code=400, detail="방문목욕 방식을 골라 주세요 (차량 내 목욕 / 가정 내 목욕 / 차량 미이용)")
        solo = bool(solo_exception)
        if solo:
            if bath_mode != benefits.HOME_BATH_SOLO_MODE:
                raise HTTPException(status_code=400, detail="1인 몸 씻기 예외는 방문목욕차량을 쓰지 않은 방문목욕에만 해당합니다")
            if for_record and not note:
                raise HTTPException(status_code=400, detail="수치심 등 몸 씻기를 1인이 제공한 부득이한 사유를 적어 주세요")
        co = None
        if co_caregiver_id and co_caregiver_id != caregiver_id:
            co = _partner(db, co_caregiver_id, caregiver_id, center_id)
        if not co and not solo:
            raise HTTPException(status_code=400, detail="방문목욕은 요양보호사 2인 이상이 제공해야 합니다. 함께 가는 요양보호사를 골라 주세요")
        if caregiver and job_type_of(caregiver) != "요양보호사":
            raise HTTPException(status_code=400, detail="방문목욕은 요양보호사가 제공합니다")
        if duration_minutes is not None and not 1 <= duration_minutes <= 240:
            raise HTTPException(status_code=400, detail="제공 시간은 1~240분 사이로 입력해 주세요")
        if for_record and duration_minutes is not None and duration_minutes < benefits.HOME_BATH_MIN_MINUTES:
            raise HTTPException(status_code=400, detail=f"방문목욕은 {benefits.HOME_BATH_MIN_MINUTES}분 이상 제공해야 청구할 수 있습니다 (60분 미만 40분 이상은 80%만 청구)")
        return {"benefit_type": "home_bath", "bath_mode": bath_mode, "co_caregiver_id": co.id if co else None, "solo_exception": solo}

    # home_nursing
    if caregiver and job_type_of(caregiver) not in NURSING_JOB_TYPES:
        raise HTTPException(status_code=400, detail="방문간호는 간호사·간호조무사·치과위생사만 제공할 수 있습니다. 직원 정보의 직종을 확인해 주세요")
    if duration_minutes is not None and not 15 <= duration_minutes <= 240:
        raise HTTPException(status_code=400, detail="방문간호 제공 시간은 15분 이상 240분 이하로 입력해 주세요")
    if require_duration and duration_minutes is None:
        raise HTTPException(status_code=400, detail="제공 시간을 입력해 주세요")
    return {"benefit_type": "home_nursing", "bath_mode": None, "co_caregiver_id": None, "solo_exception": False}
