from datetime import date

from app.labor_rules import annual_leave_days, retirement_estimate


def test_annual_leave_under_one_year_counts_full_months_capped_at_11():
    assert annual_leave_days(date(2026, 1, 15), date(2026, 1, 15))["days"] == 0
    assert annual_leave_days(date(2026, 1, 15), date(2026, 2, 14))["days"] == 0  # 아직 한 달이 안 지남
    assert annual_leave_days(date(2026, 1, 15), date(2026, 2, 15))["days"] == 1  # 정확히 한 달
    assert annual_leave_days(date(2025, 2, 15), date(2026, 1, 20))["days"] == 11  # 11개월 경과, 아직 1년 미만


def test_annual_leave_one_year_or_more_is_15_plus_accrual_capped_at_25():
    result = annual_leave_days(date(2025, 1, 1), date(2026, 1, 1))
    assert result["service_years"] == 1
    assert result["days"] == 15

    result = annual_leave_days(date(2023, 1, 1), date(2026, 1, 1))
    assert result["service_years"] == 3
    assert result["days"] == 16  # 15 + (3-1)//2

    result = annual_leave_days(date(2001, 1, 1), date(2026, 1, 1))
    assert result["service_years"] == 25
    assert result["days"] == 25  # 상한 25일


def test_retirement_estimate_requires_one_year_service():
    result = retirement_estimate(date(2026, 1, 1), date(2026, 6, 1), [])
    assert result["eligible"] is False
    assert "1년 미만" in result["reason"]


def test_retirement_estimate_without_wage_history_reports_unknown():
    result = retirement_estimate(date(2024, 1, 1), date(2026, 1, 1), [])
    assert result["eligible"] is True
    assert result["average_daily_wage"] is None
    assert result["estimated_amount"] is None


def test_retirement_estimate_computes_average_daily_wage_and_amount():
    wages = [("2026-01", 3_000_000), ("2026-02", 3_000_000), ("2026-03", 3_000_000)]
    result = retirement_estimate(date(2025, 1, 1), date(2026, 1, 1), wages)
    assert result["eligible"] is True
    assert result["service_days"] == 365
    # 9,000,000원 / (31+28+31)일 = 100,000원
    assert result["average_daily_wage"] == 100000
    # 100,000 * 30 * (365/365)
    assert result["estimated_amount"] == 3_000_000
