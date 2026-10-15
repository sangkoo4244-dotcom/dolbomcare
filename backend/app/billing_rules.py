from app import benefits

VISIT_FEES = {30: 17450, 60: 25320, 90: 34120, 120: 43430, 180: 57020, 240: 70080}

MONTHLY_LIMITS = {1: 2512900, 2: 2331200, 3: 1528200, 4: 1409700, 5: 1208900, None: 676320}  # None = 인지지원등급

PATIENT_RATES = {
    "일반": 0.15,
    "차상위계층": 0.06,
    "기초생활보장": 0.0,
    "의료급여": 0.0,
}

VALID_DURATIONS = tuple(VISIT_FEES.keys())


def _split(total: int, client_type: str | None) -> tuple[int, int, int]:
    rate = PATIENT_RATES.get(client_type or "일반", PATIENT_RATES["일반"])
    patient = int(total * rate) // 10 * 10
    return total, patient, total - patient


def split_visit(duration_minutes: int, client_type: str | None) -> tuple[int, int, int]:
    """1회 방문요양의 (급여비용 총액, 본인부담금, 공단부담금)을 반환한다."""
    if duration_minutes not in VISIT_FEES:
        raise ValueError(f"지원하지 않는 제공 시간: {duration_minutes}분")
    return _split(VISIT_FEES[duration_minutes], client_type)


def split_day_night(minutes: int, grade, client_type: str | None) -> tuple[int, int, int]:
    """주·야간보호 1일의 (급여비용 총액, 본인부담금, 공단부담금). 이동서비스비용·목욕 가산은 수급자 부담이 없고 월 한도 밖이라 여기에 넣지 않는다."""
    return _split(benefits.day_night_fee(minutes, grade), client_type)


def split_benefit(benefit_type: str | None, duration_minutes: int | None, client_type: str | None, bath_mode: str | None = None,
                  solo_exception: bool = False) -> tuple[int, int, int]:
    """방문요양·방문목욕·방문간호 1회의 (급여비용 총액, 본인부담금, 공단부담금). 급여비용은 benefits.py의 공단 수가표를 따른다.
    방문목욕은 시간(제26조: 60분 이상 전액, 40~60분 80%, 40분 미만 불가)과 1인 몸 씻기 예외를 반영한다.
    중증 가산, 야간 가산, 최초 방문간호 본인부담 면제 같은 가산·면제는 아직 계산하지 않는다."""
    if benefit_type in (None, "", "home_care"):
        return split_visit(duration_minutes, client_type)
    if benefit_type == "home_bath":
        return _split(benefits.home_bath_fee(bath_mode, duration_minutes, solo_exception), client_type)
    if benefit_type == "home_nursing":
        return _split(benefits.home_nursing_fee(duration_minutes), client_type)
    raise ValueError(f"지원하지 않는 급여 종류: {benefit_type}")

# 승인 이후 상태만 청구 금액(월별 정산·급여·대시보드)에 포함한다
REVENUE_STATUSES = ("approved", "submitted_to_nhis", "reimbursed")
