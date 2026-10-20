import math

# 급여 공제율 (현재 화면과 동일한 임시 기준). 실제 기준은 노무·세무 확인 후 여기서만 바꾼다.
RATES = {
    "income_tax": 0.033,
    "pension": 0.09,
    "health": 0.0349,
    "employment": 0.0065,
}
# 승인 이후 상태의 청구만 급여 대상이다 (금액 집계 기준과 동일)
SALARY_STATUSES = ("approved", "submitted_to_nhis", "reimbursed")

# 요양사가 실제로 받는 급여 비율의 기본값(%). 센터가 직원관리에서 개별 설정하기 전까지는
# 청구액 전체를 급여 기준액으로 본다 (기존 동작과 동일하게 유지).
DEFAULT_WAGE_RATIO = 100


def _round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def calc_wage_base(billing_total: int, wage_ratio) -> int:
    """공단 청구액(billing_total)과 요양보호사 실수령 월급은 다른 돈이다 — 청구액은 센터 매출이고,
    급여는 그중 계약된 비율만큼이다. wage_ratio가 없으면(아직 설정 안 한 요양사) 100%로 취급해
    기존 동작과 같게 유지한다."""
    ratio = DEFAULT_WAGE_RATIO if wage_ratio is None else wage_ratio
    return _round_half_up(billing_total * ratio / 100)


PAY_METHODS = ("ratio", "hourly")


def calc_hourly_base(work_minutes: int, hourly_wage: int) -> int:
    """시급 방식 급여 산정액 = 시급 × 제공 시간(분) / 60. 원 단위로 반올림한다."""
    return _round_half_up(hourly_wage * work_minutes / 60)


def calc_deductions(amount: int) -> dict:
    items = {name: _round_half_up(amount * rate) for name, rate in RATES.items()}
    total_tax = sum(items.values())
    return {**items, "total_deduction": total_tax, "net": amount - total_tax}
