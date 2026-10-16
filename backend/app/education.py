"""요양보호사 보수교육 이수 상태 계산.

규칙 출처(2차 자료, 공단 운영지침 원문 확인 필요): 2년마다 한 번 이수하고, 출생연도 홀수는 홀수 연도, 짝수는 짝수 연도에 이수한다.
11월 이후 입사한 신규 직원은 차기 교육 대상 연도에 이수해도 인정한다(2026 평가 Q20). 면제는 센터가 '면제'로 기록한 경우만 인정한다.
계산 결과에는 항상 '운영지침 확인 필요' 문구를 함께 보여 준다.
"""
from datetime import date
from typing import Optional

NOTE = "보수교육 기준은 공단 운영지침 원문으로 확인해 주세요 (2년 주기·출생연도 홀짝·11월 입사 예외)"


def due_year(birth_date: date, hire_date: Optional[date], today: date) -> int:
    """이수해야 하는 가장 가까운 대상 연도. 출생연도와 같은 홀짝의 연도 중 오늘 이후 첫 연도."""
    parity = birth_date.year % 2
    year = today.year if today.year % 2 == parity else today.year + 1
    # 11월 이후 입사해 그해 대상이면 차기 대상 연도로 넘긴다 (Q20 예외)
    if hire_date and hire_date.year == year and hire_date.month >= 11:
        year += 2
    return year


def status_for(birth_date: Optional[date], hire_date: Optional[date], record_dates: list, exempt: bool, today: date) -> dict:
    if exempt:
        return {"state": "exempt", "label": "면제", "due_year": None, "note": NOTE}
    if not birth_date:
        return {"state": "birth_missing", "label": "생년월일 입력 필요 (센터장에게 요청)", "due_year": None, "note": NOTE}
    year = due_year(birth_date, hire_date, today)
    done = any(d.year == year for d in record_dates)
    if done:
        return {"state": "done", "label": f"{year}년 이수 완료", "due_year": year, "note": NOTE}
    if year == today.year:
        return {"state": "due", "label": f"{year}년 이수 필요 (올해 안에)", "due_year": year, "note": NOTE}
    return {"state": "upcoming", "label": f"{year}년 대상 (이수 필요)", "due_year": year, "note": NOTE}
