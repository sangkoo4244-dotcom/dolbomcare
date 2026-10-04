VISIT_FEES = {30: 17450, 60: 25320, 90: 34120, 120: 43430, 180: 57020, 240: 70080}

MONTHLY_LIMITS = {1: 2512900, 2: 2331200, 3: 1528200, 4: 1409700, 5: 1208900}

PATIENT_RATES = {
    "일반": 0.15,
    "차상위계층": 0.06,
    "기초생활보장": 0.0,
    "의료급여": 0.0,
}

VALID_DURATIONS = tuple(VISIT_FEES.keys())


def split_visit(duration_minutes: int, client_type: str | None) -> tuple[int, int, int]:
    """1회 방문의 (급여비용 총액, 본인부담금, 공단부담금)을 반환한다."""
    if duration_minutes not in VISIT_FEES:
        raise ValueError(f"지원하지 않는 제공 시간: {duration_minutes}분")
    total = VISIT_FEES[duration_minutes]
    rate = PATIENT_RATES.get(client_type or "일반", PATIENT_RATES["일반"])
    patient = int(total * rate) // 10 * 10
    return total, patient, total - patient
