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


def _round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def calc_deductions(amount: int) -> dict:
    items = {name: _round_half_up(amount * rate) for name, rate in RATES.items()}
    total_tax = sum(items.values())
    return {**items, "total_deduction": total_tax, "net": amount - total_tax}
