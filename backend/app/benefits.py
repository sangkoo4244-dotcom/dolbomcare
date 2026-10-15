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
    {"code": "day_night", "label": "주야간보호", "program": "day", "monthly_limited": True, "implemented": False},
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
    }
