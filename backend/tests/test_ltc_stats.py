import pytest

from app import ltc_stats


def row(sido, sigungu, age="75-79세", applicants="10", **grades):
    base = {f: "0" for f in ltc_stats.GRADE_FIELDS}
    base.update(grades)
    return {"시도": sido, "시군구": sigungu, "연령구분": age, "신청자": applicants, "성별": "남자", "자격별": "일반", **base}


ROWS = [
    row("서울특별시", "강남구", applicants="10", **{"1등급": "2", "3등급": "*"}),
    row("서울특별시", "강남구", age="80-84세", applicants="5", **{"등급외A": "1", "등급외B": "2"}),
    row("서울특별시", "중구"),
    row("대전광역시", "중구"),
    row("경기도", "고양시"),
    row("세종특별자치시", "_"),
    row("전남광주통합특별시", "광산구"),
]


@pytest.mark.parametrize("address,expected", [
    ("서울특별시 강남구 테헤란로 1", ("서울특별시", "강남구")),
    ("서울 강남구 역삼동", ("서울특별시", "강남구")),
    ("경기도 고양시 덕양구 어딘가", ("경기도", "고양시")),
    ("광주광역시 광산구 1번지", ("전남광주통합특별시", "광산구")),
    ("세종특별자치시 한누리대로 1", ("세종특별자치시", "_")),
    ("강남구 역삼동", ("서울특별시", "강남구")),  # 시도 생략, 전국에서 하나뿐인 시군구
    ("중구 어딘가", None),  # 서울/대전 둘 다 있어 특정 불가
    ("", None),
    (None, None),
])
def test_match_region(address, expected):
    assert ltc_stats.match_region(address, ROWS) == expected


def test_summarize_sums_and_flags_hidden_values():
    result = ltc_stats.summarize(ROWS, "서울특별시", "강남구")
    assert result["applicants"] == 15
    assert result["grades"]["1등급"] == 2
    assert result["grades"]["3등급"] == 0  # "*"는 0으로 더하되
    assert result["has_hidden_values"] is True  # 가려진 값이 있음을 알린다
    assert result["grades"]["등급외"] == 3
    assert {a["label"]: a["applicants"] for a in result["by_age"]}["80-84세"] == 5


def test_get_region_demand_without_key(monkeypatch):
    monkeypatch.delenv("ODCLOUD_SERVICE_KEY", raising=False)
    result = ltc_stats.get_region_demand("서울 강남구")
    assert result["ok"] is False


def test_get_region_demand_fails_open_on_api_error(monkeypatch):
    monkeypatch.setenv("ODCLOUD_SERVICE_KEY", "x")
    def boom():
        raise RuntimeError("network down")
    monkeypatch.setattr(ltc_stats, "_fetch_latest_rows", boom)
    result = ltc_stats.get_region_demand("서울 강남구")
    assert result["ok"] is False and "network down" in result["message"]


def test_get_region_demand_ok(monkeypatch):
    monkeypatch.setenv("ODCLOUD_SERVICE_KEY", "x")
    monkeypatch.setattr(ltc_stats, "_fetch_latest_rows", lambda: ("2026-08", ROWS))
    result = ltc_stats.get_region_demand("서울특별시 강남구 테헤란로")
    assert result["ok"] and result["region"] == "서울특별시 강남구" and result["base_month"] == "2026-08"
    assert result["applicants"] == 15


def test_get_region_demand_unmatched_address(monkeypatch):
    monkeypatch.setenv("ODCLOUD_SERVICE_KEY", "x")
    monkeypatch.setattr(ltc_stats, "_fetch_latest_rows", lambda: ("2026-08", ROWS))
    assert ltc_stats.get_region_demand("주소불명")["ok"] is False


def test_region_options_lists_regions_and_own(monkeypatch):
    monkeypatch.setenv("ODCLOUD_SERVICE_KEY", "x")
    monkeypatch.setattr(ltc_stats, "_fetch_latest_rows", lambda: ("2026-08", ROWS))
    result = ltc_stats.get_region_options("서울특별시 강남구 테헤란로")
    assert result["ok"]
    assert result["regions"]["서울특별시"] == ["강남구", "중구"]
    assert result["regions"]["세종특별자치시"] == []
    assert result["own"] == {"sido": "서울특별시", "sigungu": "강남구"}
    assert ltc_stats.get_region_options("주소불명")["own"] is None


def test_get_region_demand_for_chosen_region(monkeypatch):
    monkeypatch.setenv("ODCLOUD_SERVICE_KEY", "x")
    monkeypatch.setattr(ltc_stats, "_fetch_latest_rows", lambda: ("2026-08", ROWS))
    result = ltc_stats.get_region_demand("주소불명", "서울특별시", "강남구")
    assert result["ok"] and result["region"] == "서울특별시 강남구"
    sejong = ltc_stats.get_region_demand("주소불명", "세종특별자치시")
    assert sejong["ok"] and sejong["region"] == "세종특별자치시"
    assert ltc_stats.get_region_demand("서울 강남구", "서울특별시", "없는구")["ok"] is False
