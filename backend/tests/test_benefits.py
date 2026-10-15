import pytest

from app import benefits
from app.billing_rules import VISIT_FEES


def test_home_care_matches_nhis_table_and_existing_billing_rules():
    # 공단 2026.1.1 기준표 전부
    expected = {30: 17450, 60: 25320, 90: 34120, 120: 43430, 150: 50640, 180: 57020, 210: 63530, 240: 70080}
    assert {m: benefits.home_care_fee(m) for m in expected} == expected
    # 지금 청구 계산(billing_rules)이 쓰는 방문요양 금액과 어긋나면 안 된다
    assert all(benefits.home_care_fee(m) == fee for m, fee in VISIT_FEES.items())
    # 구간 사이 값은 아래 구간 금액, 240분 넘으면 같은 금액
    assert benefits.home_care_fee(59) == 17450 and benefits.home_care_fee(61) == 25320 and benefits.home_care_fee(300) == 70080
    with pytest.raises(ValueError):
        benefits.home_care_fee(29)


def test_home_bath_has_three_modes():
    assert benefits.home_bath_fee("vehicle_in") == 88990
    assert benefits.home_bath_fee("vehicle_home") == 80230
    assert benefits.home_bath_fee("no_vehicle") == 50100
    with pytest.raises(ValueError):
        benefits.home_bath_fee("car")


def test_home_nursing_bands_and_boundaries():
    assert [benefits.home_nursing_fee(m) for m in (15, 29, 30, 59, 60, 120)] == [42880, 42880, 53770, 53770, 64690, 64690]
    with pytest.raises(ValueError):
        benefits.home_nursing_fee(14)


def test_day_night_bands_grades_and_boundaries():
    assert benefits.day_night_fee(180, 1) == 41820 and benefits.day_night_fee(359, 2) == 38720
    assert benefits.day_night_fee(360, 3) == 47940 and benefits.day_night_fee(479, 4) == 46300
    assert benefits.day_night_fee(480, 5) == 56360 and benefits.day_night_fee(599, None) == 56360
    # 10시간 이상 13시간 이하는 한 구간, 13시간 넘으면 다음 구간
    assert benefits.day_night_fee(600, 1) == 76820 and benefits.day_night_fee(780, 1) == 76820 and benefits.day_night_fee(781, 1) == 82370
    # 인지지원등급은 3시간 이상 8시간 미만에서 5등급과 같고, 10시간 이상은 56,360원으로 고정
    assert benefits.day_night_fee(200, None) == benefits.day_night_fee(200, 5) == 32490
    assert benefits.day_night_fee(900, None) == 56360 and benefits.day_night_fee(900, 5) == 67240
    with pytest.raises(ValueError):
        benefits.day_night_fee(179, 1)
    with pytest.raises(ValueError):
        benefits.day_night_fee(300, 6)


def test_short_stay_and_facility_daily_fees():
    assert [benefits.short_stay_fee(g) for g in (1, 2, 3, 4, 5)] == [74060, 68580, 63350, 61680, 60000]
    assert [benefits.nursing_home_fee(g) for g in (1, 2, 3, 4, 5)] == [93070, 86340, 81540, 81540, 81540]
    assert [benefits.nursing_home_fee(g, staffing_met=False) for g in (1, 2, 5)] == [88520, 82120, 77540]
    assert [benefits.group_home_fee(g) for g in (1, 2, 3, 5)] == [74590, 69210, 63800, 63800]
    with pytest.raises(ValueError):
        benefits.short_stay_fee(None)  # 인지지원등급은 단기보호·시설 표에 없다
    with pytest.raises(ValueError):
        benefits.nursing_home_fee(0)


def test_catalog_groups_benefits_like_carefor_programs_and_tracks_what_is_implemented():
    cat = benefits.catalog("방문요양,방문목욕,알수없음,주야간보호")
    assert [p["label"] for p in cat["programs"]] == ["가정방문", "주야간보호", "시설·공생"]
    flat = {b["code"]: b for p in cat["programs"] for b in p["benefits"]}
    assert cat["enabled"] == ["home_care", "home_bath", "day_night"]  # 모르는 이름은 무시, 선택 순서 유지
    assert flat["home_care"]["enabled"] and flat["home_care"]["implemented"]
    assert flat["home_bath"]["enabled"] and flat["home_bath"]["implemented"] and flat["home_nursing"]["implemented"]  # 방문 3종은 기능이 있다
    assert flat["day_night"]["enabled"] and flat["day_night"]["implemented"]  # 주야간보호도 기록·청구가 구현됨
    assert not flat["nursing_home"]["enabled"]
    assert benefits.catalog(None)["enabled"] == [] and benefits.enabled_codes("") == []
    # 시설은 재가급여 월 한도 대상이 아니다
    assert not benefits.BY_CODE["nursing_home"]["monthly_limited"] and benefits.BY_CODE["day_night"]["monthly_limited"]


def test_catalog_serves_the_visit_fee_tables_for_screen_previews():
    fees = benefits.catalog(None)["visit_fees"]
    assert {f["min"]: f["fee"] for f in fees["home_care"]}[60] == 25320
    assert {f["mode"]: f["fee"] for f in fees["home_bath"]} == {"vehicle_in": 88990, "vehicle_home": 80230, "no_vehicle": 50100}
    assert [(f["min"], f["max"], f["fee"]) for f in fees["home_nursing"]] == [(15, 30, 42880), (30, 60, 53770), (60, None, 64690)]
