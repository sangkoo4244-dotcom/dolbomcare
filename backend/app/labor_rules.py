"""근로기준법 제60조(연차유급휴가) · 근로자퇴직급여보장법 제8조(퇴직금) 계산.

공식 수치만 반영한다. 실제 지급 여부(80% 이상 출근 등 요건 충족 여부)는 센터가 직접
판단해야 하므로, 여기서는 "근속기간 기준으로 발생 가능한 일수/추정 퇴직금"만 계산해
참고 자료로 제공한다 - 최종 확정·지급은 센터 책임이다.
"""
import calendar
from datetime import date


def _full_months_elapsed(start: date, end: date) -> int:
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(months, 0)


def annual_leave_days(hire_date: date, as_of: date) -> dict:
    """근로기준법 제60조: 계속근로기간에 따른 연차유급휴가 일수.
    - 계속근로 1년 미만: 1개월 개근마다 1일 (최대 11일)
    - 계속근로 1년 이상: 15일 + 3년차부터 매 2년마다 1일 가산, 최대 25일
    """
    if as_of < hire_date:
        return {"service_days": 0, "service_years": 0, "days": 0, "basis": "입사 전"}

    service_days = (as_of - hire_date).days
    service_years = service_days // 365

    if service_years < 1:
        months = min(_full_months_elapsed(hire_date, as_of), 11)
        return {
            "service_days": service_days, "service_years": 0, "days": months,
            "basis": "계속근로 1년 미만 - 1개월 개근마다 1일(최대 11일)",
        }

    days = min(15 + (service_years - 1) // 2, 25)
    return {
        "service_days": service_days, "service_years": service_years, "days": days,
        "basis": "계속근로 1년 이상 - 15일 + 3년차부터 2년마다 1일 가산(최대 25일)",
    }


def retirement_estimate(hire_date: date, as_of: date, recent_monthly_wages: list[tuple[str, int]]) -> dict:
    """근로자퇴직급여보장법: 평균임금(최근 3개월 세전 임금 ÷ 그 기간 총일수) × 30일 × (재직일수 ÷ 365).
    recent_monthly_wages: [("YYYY-MM", 그 달 세전 임금), ...] - 최근 확정된 급여 순으로 최대 3개월.
    """
    service_days = (as_of - hire_date).days if as_of >= hire_date else 0
    if service_days < 365:
        return {"eligible": False, "service_days": service_days, "reason": "계속근로 1년 미만 - 퇴직금 지급 대상이 아닙니다"}

    if not recent_monthly_wages:
        return {
            "eligible": True, "service_days": service_days,
            "reason": "최근 확정된 급여 내역이 없어 평균임금을 계산할 수 없습니다",
            "average_daily_wage": None, "estimated_amount": None,
        }

    total_wage = sum(wage for _, wage in recent_monthly_wages)
    total_days = 0
    for year_month, _ in recent_monthly_wages:
        year, month = map(int, year_month.split("-"))
        total_days += calendar.monthrange(year, month)[1]

    average_daily_wage = total_wage / total_days if total_days else 0
    estimated_amount = round(average_daily_wage * 30 * (service_days / 365))
    return {
        "eligible": True,
        "service_days": service_days,
        "average_daily_wage": round(average_daily_wage),
        "estimated_amount": estimated_amount,
        "wage_months_used": [ym for ym, _ in recent_monthly_wages],
    }
