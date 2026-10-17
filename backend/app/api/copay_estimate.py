"""공개 본인부담금 계산기: 로그인 없이 쓰는 참고용 계산. 개인 정보를 받지 않고 저장도 하지 않는다.

계산은 billing_rules의 방문 요금·본인부담률·월 한도를 그대로 쓴다. 월 한도를 넘는 금액은 전액 본인부담으로 본다.
중증 가산과 공휴일·야간 가산은 포함하지 않는다. 실제 금액은 공단 확인이 필요하다.
"""
from fastapi import APIRouter, HTTPException, Query

from app.billing_rules import MONTHLY_LIMITS, PATIENT_RATES, VISIT_FEES

router = APIRouter()

GRADES = {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "cognitive": None}


def _round10(value: float) -> int:
    return int(value) // 10 * 10


@router.get("/estimate")
def estimate(
    grade: str = Query(..., description="1~5 또는 cognitive(인지지원등급)"),
    client_type: str = Query("일반"),
    minutes: int = Query(60),
    visits_per_month: int = Query(8, ge=1, le=31),
):
    if grade not in GRADES:
        raise HTTPException(status_code=400, detail="등급을 골라 주세요")
    if client_type not in PATIENT_RATES:
        raise HTTPException(status_code=400, detail="소득 구분을 골라 주세요")
    if minutes not in VISIT_FEES:
        raise HTTPException(status_code=400, detail="제공 시간을 골라 주세요")

    rate = PATIENT_RATES[client_type]
    fee = VISIT_FEES[minutes]
    visit_patient = _round10(fee * rate)  # 청구는 1회마다 10원 단위로 반올림한다
    limit = MONTHLY_LIMITS[GRADES[grade]]

    month_total = fee * visits_per_month
    covered = min(month_total, limit)
    excess = month_total - covered
    full_visits = covered // fee  # 한도 안에 온전히 들어가는 방문 수
    remainder = covered - full_visits * fee  # 한도에 걸친 마지막 방문의 한도 안쪽 금액
    patient = full_visits * visit_patient + _round10(remainder * rate) + excess
    insurer = month_total - patient

    return {
        "status": "success",
        "data": {
            "per_visit": {"minutes": minutes, "total": fee, "patient": visit_patient, "insurer": fee - visit_patient},
            "month": {
                "visits": visits_per_month,
                "total": month_total,
                "limit": limit,
                "over_limit": excess,
                "patient": patient,
                "insurer": insurer,
            },
            "notes": [
                "참고용 계산입니다. 실제 금액은 공단 고시와 개인별 등급·계약 내용에 따라 달라질 수 있습니다.",
                "중증 가산, 공휴일·야간 가산은 포함하지 않았습니다.",
                "월 한도를 넘는 금액은 전액 본인부담으로 계산했습니다.",
            ],
        },
    }
