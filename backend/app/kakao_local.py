"""카카오 로컬 API(키워드로 장소 검색) 연동 - "주변 요양시설 찾기" 참고용 검색에 쓴다.

여기서 나오는 결과는 공단이 인증한 장기요양기관 목록이 아니라 카카오맵에 등록된 업체
검색 결과다 (등급·급여종류 등은 보장 안 됨) - 화면에서 "참고용"이라고 반드시 밝힌다.

필요한 환경변수: KAKAO_REST_API_KEY (카카오 디벨로퍼스에서 발급받은 REST API 키).
미설정이면 조용히 "검색 불가" 결과만 돌려주고 나머지 기능은 그대로 동작한다
(nhis_ltc.py, alimtalk.py와 같은 패턴).
"""
import os

import httpx

KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY")
# 지도를 그리는 브라우저용 키. REST API 키와 발급 경로가 다르고(카카오맵 JavaScript 키),
# 카카오 디벨로퍼스에서 이 키를 쓸 도메인(플랫폼)을 따로 등록해야 지도가 뜬다. 공개되어도
# 되는 키라서(도메인으로 제한됨) 프런트에 그대로 내려줘도 된다.
KAKAO_JS_KEY = os.getenv("KAKAO_JS_KEY")
SEARCH_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
ADDRESS_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/address.json"


def search_nearby_facilities(query: str) -> dict:
    if not KAKAO_REST_API_KEY:
        return {"ok": False, "message": "KAKAO_REST_API_KEY가 설정되지 않았습니다", "places": []}
    if not query or not query.strip():
        return {"ok": False, "message": "검색어를 입력해 주세요", "places": []}

    try:
        response = httpx.get(
            SEARCH_URL,
            headers={"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"},
            params={"query": query.strip(), "size": 15},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        return {"ok": False, "message": f"카카오맵 검색 실패: {e}", "places": []}

    def _coord(d, key):
        try:
            return float(d[key]) if d.get(key) else None
        except (TypeError, ValueError):
            return None

    places = [
        {
            "name": d.get("place_name"),
            "category": d.get("category_name"),
            "address": d.get("road_address_name") or d.get("address_name"),
            "phone": d.get("phone") or None,
            "place_url": d.get("place_url"),
            "latitude": _coord(d, "y"),
            "longitude": _coord(d, "x"),
        }
        for d in data.get("documents", [])
    ]
    return {"ok": True, "message": "", "places": places}


def geocode_address(address: str):
    """주소 문자열 -> (위도, 경도). 센터 찾기 지도/거리 계산에 쓸 좌표를 한 번만 구해 저장해 둔다.

    실패해도(키 미설정, 주소 매칭 실패 등) 예외를 던지지 않고 None을 돌려준다 - 센터 정보 저장
    자체는 좌표 없이도 계속 되어야 한다.
    """
    if not KAKAO_REST_API_KEY or not address or not address.strip():
        return None
    try:
        response = httpx.get(
            ADDRESS_SEARCH_URL,
            headers={"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"},
            params={"query": address.strip()},
            timeout=10,
        )
        response.raise_for_status()
        documents = response.json().get("documents", [])
        if not documents:
            return None
        return float(documents[0]["y"]), float(documents[0]["x"])
    except Exception:
        return None
