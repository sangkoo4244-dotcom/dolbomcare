"""장기요양 급여 종류와 급여비용(수가)표.

수가는 국민건강보험공단 장기요양보험 사이트 '급여비용' 안내 페이지의 2026.1.1 기준 표를 그대로 옮긴 것이다.
https://www.longtermcare.or.kr/npbs/e/b/502/npeb502m01.web?menuId=npe0000002742
고시가 개정되면 아래 표만 고친다. 표에 없는 입력은 추측해서 계산하지 않고 ValueError를 낸다.
본인부담률·월 한도 같은 규칙은 이 파일이 아니라 billing_rules.py에 있다.

급여 종류는 케어포 프로그램 구분(가정방문 / 주야간보호 / 시설·공생)에 맞춰 묶는다.
"""

PROGRAMS = {
    "visit": "가정방문",
    "day": "주야간보호",
    "facility": "시설·공생",
}

# code, 센터가 고르는 이름(Center.service_types에 저장되는 값), 프로그램 묶음, 재가급여 월 한도에 포함되는지, 돌봄케어에 구현됐는지
BENEFITS = [
    {"code": "home_care", "label": "방문요양", "program": "visit", "monthly_limited": True, "implemented": True},
    {"code": "home_bath", "label": "방문목욕", "program": "visit", "monthly_limited": True, "implemented": True},
    {"code": "home_nursing", "label": "방문간호", "program": "visit", "monthly_limited": True, "implemented": True},
    {"code": "day_night", "label": "주야간보호", "program": "day", "monthly_limited": True, "implemented": True},
    {"code": "short_stay", "label": "단기보호", "program": "day", "monthly_limited": True, "implemented": False},
    {"code": "nursing_home", "label": "노인요양시설", "program": "facility", "monthly_limited": False, "implemented": False},
    {"code": "group_home", "label": "노인요양공동생활가정", "program": "facility", "monthly_limited": False, "implemented": False},
]
BY_CODE = {b["code"]: b for b in BENEFITS}
BY_LABEL = {b["label"]: b for b in BENEFITS}

# 방문요양(방문당): 제공 시간 이상 -> 급여비용
HOME_CARE_FEES = [(30, 17450), (60, 25320), (90, 34120), (120, 43430), (150, 50640), (180, 57020), (210, 63530), (240, 70080)]

# 방문목욕(방문당)
HOME_BATH_FEES = {"vehicle_in": 88990, "vehicle_home": 80230, "no_vehicle": 50100}
HOME_BATH_LABELS = {"vehicle_in": "방문목욕차량 이용(차량 내 목욕)", "vehicle_home": "방문목욕차량 이용(가정 내 목욕)", "no_vehicle": "방문목욕차량 미이용"}

# 방문목욕 산정(고시 제26조): 2인 이상 요양보호사가 60분 이상이면 전액, 40분 이상 60분 미만이면 80%, 40분 미만은 청구할 수 없다.
# 이동보조·몸 씻기 전 과정을 1인이 단독 제공하면 일체 불산정이다. 다만 차량 미이용 방문목욕에서 수치심 때문에 몸 씻기만 1인이 제공했다면
# '나-3'(차량 미이용) 금액의 80%(60분 이상) 또는 70%(40분 이상 60분 미만)를 산정한다(사유를 급여제공기록지에 기재).
HOME_BATH_FULL_MINUTES = 60
HOME_BATH_MIN_MINUTES = 40
HOME_BATH_REDUCED_PERCENT = 80
HOME_BATH_SOLO_PERCENT = {"full": 80, "reduced": 70}
HOME_BATH_SOLO_MODE = "no_vehicle"

# 방문간호(방문당): (최소 분, 미만 분, 급여비용)
HOME_NURSING_FEES = [(15, 30, 42880), (30, 60, 53770), (60, None, 64690)]

# 주·야간보호(1일당): (최소 분, 최대 분, {등급: 급여비용}). 등급 None = 인지지원등급. 10시간 이상 13시간 이하까지 한 구간이다.
DAY_NIGHT_FEES = [
    (180, 359, {1: 41820, 2: 38720, 3: 35740, 4: 34120, 5: 32490, None: 32490}),
    (360, 479, {1: 56060, 2: 51930, 3: 47940, 4: 46300, 5: 44650, None: 44650}),
    (480, 599, {1: 69730, 2: 64590, 3: 59640, 4: 58010, 5: 56360, None: 56360}),
    (600, 780, {1: 76820, 2: 71160, 3: 65750, 4: 64090, 5: 62460, None: 56360}),
    (781, None, {1: 82370, 2: 76310, 3: 70500, 4: 68860, 5: 67240, None: 56360}),
]

# 주·야간보호 이동서비스비용(고시 제34조): 기관에서 수급자 실거주지까지 최단거리(편도)별 1일 금액. 이용 횟수와 무관하게 1일 1회만 산정하고
# 편도만 이용하면 50%. 수급자 부담이 없고 월 한도에 포함되지 않는다. (분류, 이상 km, 미만 km, 금액)
DAY_NIGHT_TRANSPORT_FEES = [("러-1", 0, 5, 830), ("러-2", 5, 10, 2630), ("러-3", 10, 20, 5230), ("러-4", 20, None, 8630)]
# 주·야간보호 목욕서비스 가산(제35조): 수급자당 주 1회, 몸 씻기는 반드시 요양보호사가 제공. 수급자 부담 없음.
DAY_NIGHT_BATH_BONUS = 3000
DAY_NIGHT_STANDARD_HOURS = (8, 22)  # 표준급여제공시간 08~22시(제30조 ②). 24시 이후 보호하거나 24시간 이상 보호하면 일체 불산정(제32조 ①)

# 단기보호(1일당)
SHORT_STAY_FEES = {1: 74060, 2: 68580, 3: 63350, 4: 61680, 5: 60000}

# 노인요양시설(1일당): 3~5등급은 한 줄. (요양보호사 배치 기준 충족, 미충족)
NURSING_HOME_FEES = {1: (93070, 88520), 2: (86340, 82120), 3: (81540, 77540)}

# 노인요양공동생활가정(1일당): 3~5등급은 한 줄
GROUP_HOME_FEES = {1: 74590, 2: 69210, 3: 63800}


def _check_grade(grade, allow_cognitive=True):
    valid = {1, 2, 3, 4, 5} | ({None} if allow_cognitive else set())
    if grade not in valid:
        raise ValueError(f"지원하지 않는 등급: {grade}")


def home_care_fee(minutes: int) -> int:
    """방문요양 1회 급여비용. 30분 미만은 청구할 수 없고, 240분 이상은 같은 금액이다."""
    if minutes is None or minutes < HOME_CARE_FEES[0][0]:
        raise ValueError(f"방문요양은 30분 이상부터 청구할 수 있습니다: {minutes}분")
    return [fee for threshold, fee in HOME_CARE_FEES if minutes >= threshold][-1]


# 중증 가산(1·2등급 수급자): 수급자 부담 없이 공단이 해당 요양보호사에게 따로 지급, 1인 1일 한도 6,000원, 가족 요양보호사는 제외
# 방문요양(고시 제19조의2): 1회 60분 이상 120분 미만 2,000원 / 120분 이상 180분 미만 4,000원 / 180분 이상 6,000원
# 방문목욕(제26조의2): 1회 60분 이상 요양보호사 1인당 3,000원
SEVERE_GRADES = (1, 2)
SEVERE_DAILY_CAP = 6000
HOME_CARE_SEVERE_BONUS = [(180, 6000), (120, 4000), (60, 2000)]
HOME_BATH_SEVERE_BONUS = 3000


def severe_bonus(benefit_type: str | None, grade, minutes: int | None) -> int:
    """방문요양·방문목욕 1회의 중증 가산 금액(1일 한도 적용 전). 해당 없으면 0."""
    if grade not in SEVERE_GRADES or not minutes:
        return 0
    if benefit_type in (None, "", "home_care"):
        return next((fee for lo, fee in HOME_CARE_SEVERE_BONUS if minutes >= lo), 0)
    if benefit_type == "home_bath":
        return HOME_BATH_SEVERE_BONUS if minutes >= HOME_BATH_FULL_MINUTES else 0
    return 0


# 방문요양·방문간호 시간 가산(고시 제20조 + 공단 세부지침 제5조)
#   22시~06시 야간 30%, 일요일 30%, 유급휴일(공휴일·대체공휴일, 일요일 제외)과 근로자의 날 50%.
#   겹치면 중복 가산하지 않고(일요일과 유급휴일이 겹치면 유급휴일 50%) 분 단위로 더 높은 쪽을 쓴다.
#   1회 방문 안에서 시간대가 섞이면 '가산 적용 시간 비율'로 가산한다.
#   가산금액 = 기본급여비용 × Σ(분별 가산율) ÷ 총급여제공시간(분)   (10원 미만은 반올림, 고시 제47조)
#   세부지침 예시: 공휴일 18시 시작 480분 → 18~24시는 50%, 자정 이후 평일 야간(24~02시)은 30%.
NIGHT_START_HOUR, NIGHT_END_HOUR = 22, 6
NIGHT_SUNDAY_PERCENT, HOLIDAY_PERCENT = 30, 50

from datetime import date as _date

# 유급휴일 달력: 해마다 음력·대체공휴일·임시공휴일이 달라 공식 월력요항으로 확인한 해만 넣는다. 표에 없는 해는 공휴일 가산을 계산하지 않고 화면에서 알린다.
# 출처: 관공서의 공휴일에 관한 규정, 근로자의 날 제정에 관한 법률, 공직선거법(선거일), 연도별 달력 자료(2차 자료와 음력 날짜 교차 확인).
_HOLIDAYS = {
    2026: ["01-01", "02-16", "02-17", "02-18", "03-01", "03-02", "05-01", "05-05", "05-24", "05-25", "06-03", "06-06",
           "08-15", "08-17", "09-24", "09-25", "09-26", "10-03", "10-05", "10-09", "12-25"],
    2027: ["01-01", "02-06", "02-07", "02-08", "02-09", "03-01", "05-01", "05-05", "05-13", "06-06", "08-15", "08-16",
           "09-14", "09-15", "09-16", "10-03", "10-04", "10-09", "10-11", "12-25", "12-27"],
}
# 한 곳의 2차 자료에만 나와 법적 근거를 확인하지 못한 날: 가산은 계산하지 않고 청구 입력 도우미에서 '확인 필요'로만 알린다.
_UNCERTAIN_HOLIDAYS = {2026: ["07-17"], 2027: ["05-03", "07-17", "07-19"]}
HOLIDAY_TABLE_YEARS = tuple(_HOLIDAYS)
PAID_HOLIDAYS = {_date(y, int(md[:2]), int(md[3:])) for y, days in _HOLIDAYS.items() for md in days}
UNCERTAIN_HOLIDAYS = {_date(y, int(md[:2]), int(md[3:])) for y, days in _UNCERTAIN_HOLIDAYS.items() for md in days}


def surcharge_percent(moment) -> int:
    """그 시각 1분에 적용되는 가산율(0·30·50)."""
    day = moment.date()
    if day in PAID_HOLIDAYS and day.weekday() != 6:  # 일요일에 겹친 공휴일은 일요일(30%)로 본다
        return HOLIDAY_PERCENT
    if day.weekday() == 6 or moment.hour >= NIGHT_START_HOUR or moment.hour < NIGHT_END_HOUR:
        return NIGHT_SUNDAY_PERCENT
    return 0


def _surcharge_by_minute(start, minutes):
    from datetime import timedelta
    return [surcharge_percent(start + timedelta(minutes=m)) for m in range(minutes)]


def surcharge_minutes(start, minutes: int | None) -> int:
    """방문 안에서 가산(야간·일요일·유급휴일)이 붙는 분."""
    if not start or not minutes or minutes <= 0:
        return 0
    return sum(1 for pct in _surcharge_by_minute(start, minutes) if pct)


def visit_surcharge(base_fee: int, start, minutes: int | None) -> int:
    """방문요양·방문간호 1회의 시간 가산금액(원). 해당 없으면 0."""
    if not start or not minutes or minutes <= 0 or not base_fee:
        return 0
    total_percent = sum(_surcharge_by_minute(start, minutes))
    if not total_percent:
        return 0
    from fractions import Fraction
    exact = Fraction(base_fee * total_percent, 100 * minutes)
    return int((exact + 5) // 10) * 10  # 10원 단위 반올림


def holiday_table_missing(start) -> bool:
    """방문한 해의 공휴일표가 없어 공휴일 가산을 계산하지 못한 경우."""
    return bool(start) and start.year not in HOLIDAY_TABLE_YEARS


def possible_unconfirmed_holiday(start, minutes: int | None) -> bool:
    """방문 시간대에 공휴일일 수 있지만 근거를 확인하지 못해 계산에 넣지 않은 날이 걸쳐 있는지."""
    if not start or not minutes:
        return False
    from datetime import timedelta
    return any((start + timedelta(minutes=m)).date() in UNCERTAIN_HOLIDAYS for m in (0, max(0, minutes - 1)))


def home_bath_fee(mode: str, minutes: int | None = None, solo_exception: bool = False) -> int:
    """방문목욕 1회 급여비용. minutes를 주면 제26조의 시간별 산정(60분 이상 전액, 40~60분 80%, 40분 미만 불가)을 적용한다.
    solo_exception은 차량 미이용에서 수치심으로 몸 씻기만 1인이 제공한 예외(80% 또는 70%)다."""
    if mode not in HOME_BATH_FEES:
        raise ValueError(f"지원하지 않는 방문목욕 방식: {mode}")
    base = HOME_BATH_FEES[mode]
    if minutes is None:
        return base
    if minutes < HOME_BATH_MIN_MINUTES:
        raise ValueError(f"방문목욕은 {HOME_BATH_MIN_MINUTES}분 이상 제공해야 청구할 수 있습니다: {minutes}분")
    reduced = minutes < HOME_BATH_FULL_MINUTES
    if solo_exception:
        if mode != HOME_BATH_SOLO_MODE:
            raise ValueError("1인 몸 씻기 예외는 방문목욕차량을 쓰지 않은 방문목욕에만 해당합니다")
        return base * HOME_BATH_SOLO_PERCENT["reduced" if reduced else "full"] // 100
    return base * HOME_BATH_REDUCED_PERCENT // 100 if reduced else base


def home_nursing_fee(minutes: int) -> int:
    """방문간호 1회 급여비용. 15분 미만은 청구할 수 없다."""
    if minutes is None or minutes < HOME_NURSING_FEES[0][0]:
        raise ValueError(f"방문간호는 15분 이상부터 청구할 수 있습니다: {minutes}분")
    for low, high, fee in HOME_NURSING_FEES:
        if minutes >= low and (high is None or minutes < high):
            return fee
    raise ValueError(f"지원하지 않는 방문간호 시간: {minutes}분")


def day_night_fee(minutes: int, grade) -> int:
    """주·야간보호 1일 급여비용. 3시간 미만은 청구할 수 없다. grade None은 인지지원등급."""
    _check_grade(grade)
    if minutes is None or minutes < DAY_NIGHT_FEES[0][0]:
        raise ValueError(f"주·야간보호는 3시간 이상부터 청구할 수 있습니다: {minutes}분")
    for low, high, fees in DAY_NIGHT_FEES:
        if minutes >= low and (high is None or minutes <= high):
            return fees[grade]
    raise ValueError(f"지원하지 않는 이용 시간: {minutes}분")


def day_night_transport_fee(distance_km, direction: str) -> tuple[str, int]:
    """주·야간보호 이동서비스비용 (분류, 금액). direction: both(왕복 전액) / in·out(편도 50%) / none(0)."""
    if direction == "none":
        return "", 0
    if direction not in ("both", "in", "out"):
        raise ValueError(f"지원하지 않는 이동서비스 방향: {direction}")
    if distance_km is None or distance_km < 0:
        raise ValueError("이동서비스는 기관에서 수급자 실거주지까지의 최단거리(편도, km)를 입력해야 합니다")
    for code, low, high, fee in DAY_NIGHT_TRANSPORT_FEES:
        if distance_km >= low and (high is None or distance_km < high):
            return code, fee if direction == "both" else fee // 2
    raise ValueError(f"지원하지 않는 거리: {distance_km}")


def short_stay_fee(grade) -> int:
    _check_grade(grade, allow_cognitive=False)
    return SHORT_STAY_FEES[grade]


def nursing_home_fee(grade, staffing_met: bool = True) -> int:
    """노인요양시설 1일 급여비용. 요양보호사 배치 기준을 못 채운 시설은 낮은 금액이다."""
    _check_grade(grade, allow_cognitive=False)
    met, unmet = NURSING_HOME_FEES[min(grade, 3)]
    return met if staffing_met else unmet


def group_home_fee(grade) -> int:
    _check_grade(grade, allow_cognitive=False)
    return GROUP_HOME_FEES[min(grade, 3)]


def enabled_codes(service_types: str | None) -> list[str]:
    """Center.service_types(쉼표로 구분한 이름)에서 센터가 제공하는 급여 코드를 순서대로 돌려준다. 모르는 이름은 무시한다."""
    names = [s.strip() for s in (service_types or "").split(",") if s.strip()]
    return [BY_LABEL[n]["code"] for n in names if n in BY_LABEL]


def catalog(service_types: str | None) -> dict:
    """화면용: 프로그램 묶음별 급여 목록과 센터의 사용 여부·구현 여부."""
    enabled = set(enabled_codes(service_types))
    programs = []
    for code, label in PROGRAMS.items():
        programs.append({
            "code": code, "label": label,
            "benefits": [{"code": b["code"], "label": b["label"], "enabled": b["code"] in enabled, "implemented": b["implemented"]}
                         for b in BENEFITS if b["program"] == code],
        })
    return {"programs": programs, "enabled": [c for c in enabled_codes(service_types)], "visit_fees": visit_fee_tables()}


def visit_fee_tables() -> dict:
    """방문 급여(요양·목욕·간호) 수가표를 화면 미리보기용으로 내려준다. 화면에 숫자를 따로 복사해 두지 않기 위해서다."""
    return {
        "home_care": [{"min": m, "fee": f} for m, f in HOME_CARE_FEES],
        "home_bath": [{"mode": k, "label": HOME_BATH_LABELS[k], "fee": v} for k, v in HOME_BATH_FEES.items()],
        "home_bath_rules": {"full_min": HOME_BATH_FULL_MINUTES, "min": HOME_BATH_MIN_MINUTES, "reduced_percent": HOME_BATH_REDUCED_PERCENT,
                            "solo_percent": HOME_BATH_SOLO_PERCENT, "solo_mode": HOME_BATH_SOLO_MODE},
        "home_nursing": [{"min": lo, "max": hi, "fee": f} for lo, hi, f in HOME_NURSING_FEES],
        "day_night_transport": [{"code": c, "min_km": lo, "max_km": hi, "fee": f} for c, lo, hi, f in DAY_NIGHT_TRANSPORT_FEES],
    }
