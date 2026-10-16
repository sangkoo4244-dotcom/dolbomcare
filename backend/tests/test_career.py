"""경력직 비율 계산 규칙 단위 테스트 (원문: 분모 6개월 이상, 분자 연속 24개월(운영 2년 미만 12개월), 반올림, 점수 구간)."""
from datetime import date

from app.career import compute, employment_months, score_of


def test_worked_example_ratio_and_score():
    a = employment_months(date(2022, 1, 1), None)
    b = employment_months(date(2024, 6, 1), None)   # 19개월: 연속 24 미달
    c = employment_months(date(2024, 1, 1), date(2024, 3, 31))  # 3개월: 분모 제외
    d = employment_months(date(2023, 1, 1), date(2025, 12, 31))
    r = compute([{"name": "A", "months": a}, {"name": "B", "months": b}, {"name": "C", "months": c},
                 {"name": "D", "months": d}, {"name": "E", "months": a, "excluded": True}], operated_months=40)
    assert (r["denominator"], r["numerator"], r["ratio_pct"], r["score"], r["threshold_months"]) == (3, 2, 67, 1, 24)


def test_short_operation_uses_twelve_months_and_score_bands():
    d = employment_months(date(2023, 1, 1), date(2025, 12, 31))
    b = employment_months(date(2024, 6, 1), None)  # 19개월: 2년 미만 기관이면 12개월 기준 충족
    r = compute([{"name": "B", "months": b}, {"name": "D", "months": d}], operated_months=20)
    assert r["threshold_months"] == 12 and r["numerator"] == 2 and r["ratio_pct"] == 100
    assert score_of(50) == 1 and score_of(49) == 0.75 and score_of(30) == 0.75 and score_of(29) == 0
