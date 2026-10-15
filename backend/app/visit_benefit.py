"""방문 일정·기록에 붙는 급여 종류(방문요양·방문목욕·방문간호)를 검증하고 정리한다.

일정 만들기, 계획 제안, 방문 기록이 모두 같은 규칙을 쓰도록 한 곳에 둔다.
규칙 중 공단 고시로 확인된 것: 방문목욕은 요양보호사 2인 이상이 제공하고 방식에 따라 수가가 다르다(차량 내 / 가정 내 / 차량 미이용).
방문간호는 간호직이 제공한다(방문간호지시서가 필요 - 지시서는 화면에서 확인 메모로 받고 막지는 않는다).
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


def normalize_visit_benefit(db, *, center_id, caregiver_id, benefit_type=None, bath_mode=None, co_caregiver_id=None,
                            duration_minutes=None, require_duration=False, strict_home_care_duration=False) -> dict:
    """급여 종류와 그에 딸린 값을 검사해 {benefit_type, bath_mode, co_caregiver_id}로 돌려준다. 문제가 있으면 400.
    방문요양은 기존과 똑같이 동작하고(아무 값도 안 보내면 방문요양), 방문목욕·방문간호는 센터가 제공 급여로 골라 둔 경우에만 쓸 수 있다.
    방문요양 제공 시간을 정해진 값으로 제한하는 것(strict_home_care_duration)은 청구가 만들어지는 방문 기록에서만 켠다.
    일정 계획 시간은 예전부터 제한이 없었으므로 그대로 둔다."""
    benefit_type = benefit_type or "home_care"
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
        return {"benefit_type": "home_care", "bath_mode": None, "co_caregiver_id": None}

    if benefit_type == "home_bath":
        if bath_mode not in benefits.HOME_BATH_FEES:
            raise HTTPException(status_code=400, detail="방문목욕 방식을 골라 주세요 (차량 내 목욕 / 가정 내 목욕 / 차량 미이용)")
        if not co_caregiver_id or co_caregiver_id == caregiver_id:
            raise HTTPException(status_code=400, detail="방문목욕은 요양보호사 2인 이상이 제공해야 합니다. 함께 가는 요양보호사를 골라 주세요")
        co = db.query(User).filter(User.id == co_caregiver_id).first()
        if not co or co.role != "caregiver" or co.center_id != center_id or job_type_of(co) != "요양보호사":
            raise HTTPException(status_code=400, detail="함께 가는 요양보호사는 우리 센터의 요양보호사여야 합니다")
        if caregiver and job_type_of(caregiver) != "요양보호사":
            raise HTTPException(status_code=400, detail="방문목욕은 요양보호사가 제공합니다")
        if duration_minutes is not None and not 1 <= duration_minutes <= 240:
            raise HTTPException(status_code=400, detail="제공 시간은 1~240분 사이로 입력해 주세요")
        return {"benefit_type": "home_bath", "bath_mode": bath_mode, "co_caregiver_id": co_caregiver_id}

    # home_nursing
    if caregiver and job_type_of(caregiver) not in NURSING_JOB_TYPES:
        raise HTTPException(status_code=400, detail="방문간호는 간호사·간호조무사·치과위생사만 제공할 수 있습니다. 직원 정보의 직종을 확인해 주세요")
    if duration_minutes is not None and not 15 <= duration_minutes <= 240:
        raise HTTPException(status_code=400, detail="방문간호 제공 시간은 15분 이상 240분 이하로 입력해 주세요")
    if require_duration and duration_minutes is None:
        raise HTTPException(status_code=400, detail="제공 시간을 입력해 주세요")
    return {"benefit_type": "home_nursing", "bath_mode": None, "co_caregiver_id": None}
