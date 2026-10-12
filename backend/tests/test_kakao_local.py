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
