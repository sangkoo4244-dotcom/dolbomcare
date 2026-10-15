"""2026.1.1 시행 공단 세부지침(공고 제2025-33호) 제5조·제7조의 가산 계산을 손계산 값과 대조한다."""
from datetime import datetime

from fastapi.testclient import TestClient  # noqa: F401
from app import benefits
from app.billing_rules import split_benefit, split_day_night
from tests.test_day_care import CG, DAY, MGR, env  # noqa: F401  (env 픽스처 재사용)

TUE = datetime(2026, 10, 13)


def round10(x):
    return int((x + 5) // 10) * 10


def test_home_nursing_surcharge_divides_by_the_fee_table_minimum_time():
    base = benefits.home_nursing_fee(45)  # 30~60분 구간 53,770원, 구간 최저시간 30분
    assert (base, benefits.visit_fee_minutes("home_nursing", 45)) == (53770, 30)
    # 21:30 시작 45분 중 22:00~22:15 15분만 야간: 53,770 × 0.3 × 15 ÷ 30 = 8,065.5 → 8,070 (실제 시간 45분으로 나누면 5,380)
    assert benefits.visit_surcharge(base, TUE.replace(hour=21, minute=30), 45, 30) == 8070
    # 45분 모두 야간이면 적용 시간이 최저시간을 넘으므로 비율 30%만: 16,131 → 16,130
    assert benefits.visit_surcharge(base, TUE.replace(hour=22), 45, 30) == 16130
    # 청구 총액에도 반영된다(일반 15%: 53,770 + 8,070 = 61,840, 본인부담 9,276→9,270)
    assert split_benefit("home_nursing", 45, "일반", start=TUE.replace(hour=21, minute=30)) == (61840, 9270, 52570)


def test_home_care_surcharge_is_unchanged_because_durations_equal_table_times():
    base = benefits.home_care_fee(120)
    assert benefits.visit_fee_minutes("home_care", 120) == 120
    assert benefits.visit_surcharge(base, TUE.replace(hour=21), 120, 120) == benefits.visit_surcharge(base, TUE.replace(hour=21), 120)


def test_day_night_evening_surcharge_follows_the_spec_example():
    base = benefits.day_night_fee(600, 3)  # 09:00~19:00 600분, 3등급 65,750원
    assert base == 65750
    # 세부지침 예시1: 가산 적용 18:00~19:00 60분 → 기본 × 0.2 × 60 ÷ 600 = 1,315
    a, l = TUE.replace(hour=9), TUE.replace(hour=19)
    assert benefits.day_night_surcharge_minutes(a, l) == 60
    assert benefits.day_night_surcharge(base, a, l) == 1320  # 1,315 → 10원 단위 반올림
    # 18시 전에 끝나면 가산 없음, 22시를 넘는 시간은 가산 시간에 넣지 않음
    assert benefits.day_night_surcharge(base, a, TUE.replace(hour=18)) == 0
    assert benefits.day_night_surcharge_minutes(TUE.replace(hour=17), TUE.replace(hour=23)) == 240
    # 총액·본인부담(일반 15%): 65,750 + 1,320 = 67,070, 본인부담 10,060.5 → 10,060
    assert split_day_night(600, 3, "일반", a, l) == (67070, 10060, 57010)
    # 시각을 주지 않으면 예전과 같다
    assert split_day_night(600, 3, "일반") == (65750, 9860, 55890)


def test_day_care_api_adds_evening_surcharge_and_warns_about_holidays(env):
    db, client = env
    body = {"resident_id": 1, "attendance_date": "2026-10-13", "arrive_time": "09:00", "leave_time": "19:00"}
    r = client.post("/api/v1/day-care/preview", headers=MGR, json=body)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["fee_total"] == 67070 and d["patient"] == 10060 and d["insurer"] == 57010
    assert any("18~22시" in n for n in d["notes"])
    # 한글날(2026-10-09, 금) 같은 공휴일에는 계산하지 않고 안내만 한다
    body["attendance_date"] = "2026-10-09"
    d = client.post("/api/v1/day-care/preview", headers=MGR, json=body).json()
    assert any("30% 가산" in n for n in d["notes"])
