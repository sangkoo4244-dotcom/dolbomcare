from types import SimpleNamespace

from app import kakao_local


def test_search_without_api_key_fails_gracefully(monkeypatch):
    monkeypatch.setattr(kakao_local, "KAKAO_REST_API_KEY", None)
    result = kakao_local.search_nearby_facilities("강남구 요양원")
    assert result["ok"] is False
    assert "KAKAO_REST_API_KEY" in result["message"]
    assert result["places"] == []


def test_search_without_query():
    result = kakao_local.search_nearby_facilities("")
    assert result["ok"] is False


def test_search_parses_places_on_success(monkeypatch):
    monkeypatch.setattr(kakao_local, "KAKAO_REST_API_KEY", "dummy-key")
    monkeypatch.setattr(kakao_local.httpx, "get", lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"documents": [
            {"place_name": "사랑요양원", "category_name": "의료,건강>요양원", "road_address_name": "서울 강남구 테헤란로 1",
             "address_name": "서울 강남구 역삼동 1", "phone": "02-1234-5678", "place_url": "https://place.map.kakao.com/1"},
        ]},
    ))
    result = kakao_local.search_nearby_facilities("강남구 요양원")
    assert result["ok"] is True
    assert result["places"][0]["name"] == "사랑요양원"
    assert result["places"][0]["address"] == "서울 강남구 테헤란로 1"
    assert result["places"][0]["phone"] == "02-1234-5678"


def test_search_includes_coordinates_for_map_display(monkeypatch):
    monkeypatch.setattr(kakao_local, "KAKAO_REST_API_KEY", "dummy-key")
    monkeypatch.setattr(kakao_local.httpx, "get", lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"documents": [
            {"place_name": "사랑요양원", "x": "127.0276", "y": "37.4979"},
            {"place_name": "좌표없는곳", "x": "", "y": ""},
        ]},
    ))
    result = kakao_local.search_nearby_facilities("강남구 요양원")
    assert result["places"][0]["latitude"] == 37.4979
    assert result["places"][0]["longitude"] == 127.0276
    assert result["places"][1]["latitude"] is None
    assert result["places"][1]["longitude"] is None


def test_search_handles_no_results(monkeypatch):
    monkeypatch.setattr(kakao_local, "KAKAO_REST_API_KEY", "dummy-key")
    monkeypatch.setattr(kakao_local.httpx, "get", lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"documents": []},
    ))
    result = kakao_local.search_nearby_facilities("존재하지않는지역요양원")
    assert result["ok"] is True
    assert result["places"] == []


def test_search_handles_request_failure(monkeypatch):
    monkeypatch.setattr(kakao_local, "KAKAO_REST_API_KEY", "dummy-key")

    def raise_error(*a, **k):
        raise Exception("연결 실패")

    monkeypatch.setattr(kakao_local.httpx, "get", raise_error)
    result = kakao_local.search_nearby_facilities("강남구 요양원")
    assert result["ok"] is False
    assert "연결 실패" in result["message"]


def test_geocode_without_api_key_returns_none(monkeypatch):
    monkeypatch.setattr(kakao_local, "KAKAO_REST_API_KEY", None)
    assert kakao_local.geocode_address("서울시 강남구") is None


def test_geocode_without_address_returns_none(monkeypatch):
    monkeypatch.setattr(kakao_local, "KAKAO_REST_API_KEY", "dummy-key")
    assert kakao_local.geocode_address("") is None
    assert kakao_local.geocode_address(None) is None


def test_geocode_parses_coordinates_on_success(monkeypatch):
    monkeypatch.setattr(kakao_local, "KAKAO_REST_API_KEY", "dummy-key")
    monkeypatch.setattr(kakao_local.httpx, "get", lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"documents": [{"y": "37.498", "x": "127.027"}]},
    ))
    result = kakao_local.geocode_address("서울시 강남구 테헤란로 1")
    assert result == (37.498, 127.027)


def test_geocode_handles_no_match(monkeypatch):
    monkeypatch.setattr(kakao_local, "KAKAO_REST_API_KEY", "dummy-key")
    monkeypatch.setattr(kakao_local.httpx, "get", lambda *a, **k: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"documents": []},
    ))
    assert kakao_local.geocode_address("존재하지않는주소입니다") is None


def test_geocode_handles_request_failure(monkeypatch):
    monkeypatch.setattr(kakao_local, "KAKAO_REST_API_KEY", "dummy-key")

    def raise_error(*a, **k):
        raise Exception("연결 실패")

    monkeypatch.setattr(kakao_local.httpx, "get", raise_error)
    assert kakao_local.geocode_address("서울시 강남구") is None
