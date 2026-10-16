"""경력직 비율 (2026 방문요양 평가 지표 '경력직', 점수 1점, 지표적용기간 2023.1~2025.12).

규칙(원문 확인): 분모 = 지표적용기간에 합산 6개월 이상 근무한 직원 수 (급여제공 직원은 실제 급여제공 월만 근무로 봄).
분자 = 분모 중 연속 근무 기간이 기준 이상인 직원 수 (운영 2년 이상 24개월, 2년 미만 12개월).
비율 = 분자/분모 × 100 (소수점 첫째 자리에서 반올림). 점수: 50% 이상 1점, 30% 이상 50% 미만 0.75점, 그 외 0점.
제외: 대표자 겸 시설장, 정년·사망·이민 등 불가피 퇴직, 출산·질병 대체직원 퇴직, 기간제 직원 퇴직 (센터가 '제외' 표시).
근사: 휴업 기간 제외와 증빙이 필요한 휴가 판단은 센터 기록으로 확인할 수 없어 반영하지 않았다.
"""
from datetime import date
from typing import Optional

WINDOW_START = (2023, 1)
WINDOW_END = (2025, 12)


def _months(start: tuple, end: tuple):
    y, m = start
    out = []
    while (y, m) <= end:
        out.append((y, m))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


WINDOW = _months(WINDOW_START, WINDOW_END)


def longest_run(months: set) -> int:
    best = cur = 0
    for ym in WINDOW:
        cur = cur + 1 if ym in months else 0
        best = max(best, cur)
    return best


def employment_months(hire: Optional[date], leave: Optional[date]) -> set:
    if not hire:
        return set()
    start = (hire.year, hire.month)
    end = (leave.year, leave.month) if leave else WINDOW_END
    return {ym for ym in WINDOW if start <= ym <= end}


def score_of(ratio_pct: int) -> float:
    if ratio_pct >= 50:
        return 1
    if ratio_pct >= 30:
        return 0.75
    return 0


def compute(staff: list, operated_months: int) -> dict:
    """staff: [{name, excluded, months(set of (y,m) 실제 근무·급여제공 월), }]. operated_months: 기관 운영 개월 수."""
    threshold = 24 if operated_months >= 24 else 12
    rows = []
    denom = numer = 0
    for s in staff:
        months = {ym for ym in s["months"] if ym in set(WINDOW)}
        if s.get("excluded"):
            rows.append({"name": s["name"], "included": False, "reason": "제외 표시", "months": len(months), "longest": longest_run(months)})
            continue
        if len(months) < 6:
            rows.append({"name": s["name"], "included": False, "reason": "지표기간 6개월 미만", "months": len(months), "longest": longest_run(months)})
            continue
        denom += 1
        longest = longest_run(months)
        ok = longest >= threshold
        numer += 1 if ok else 0
        rows.append({"name": s["name"], "included": True, "reason": "", "months": len(months), "longest": longest, "continuous_ok": ok})
    ratio = round(numer * 100 / denom) if denom else 0
    return {"window": "2023.01~2025.12", "threshold_months": threshold, "operated_months": operated_months,
            "denominator": denom, "numerator": numer, "ratio_pct": ratio, "score": score_of(ratio) if denom else 0,
            "staff": rows,
            "note": "휴업 기간·증빙 휴가는 반영하지 않은 근사 계산입니다. 제출 전 공단 원문과 직원 근무 기록을 확인하세요."}
