"""국민건강보험공단 노인장기요양보험 등급판정 현황(공공데이터포털) - 센터 지역 수요 카드에 쓴다.

시군구별·성별·연령별·자격별 신청자 수와 등급 분포 통계다. 개별 이용자 정보는 없다.
소수 인원은 공단이 "*"로 가려서 내려주므로, 합계는 공개된 인원 기준(실제보다 적을 수 있음)이다.

필요한 환경변수: ODCLOUD_SERVICE_KEY (공공데이터포털 일반 인증키). 미설정이거나 호출이 실패해도
예외를 던지지 않고 ok=False 결과만 돌려준다 - 대시보드의 다른 부분은 그대로 동작해야 한다
(kakao_local.py와 같은 패턴).
"""
import os
import re
import time

import httpx

BASE_URL = "https://api.odcloud.kr/api"
SWAGGER_URL = "https://infuser.odcloud.kr/oas/docs?namespace=3051421/v1"
CACHE_SECONDS = 24 * 3600  # 통계는 월 단위로 갱신되므로 하루 캐시면 충분

GRADE_FIELDS = ["1등급", "2등급", "3등급", "4등급", "5등급", "인지지원등급", "등급외A", "등급외B", "등급외C"]
AGE_ORDER = ["65세미만", "65-69세", "70-74세", "75-79세", "80-84세", "85세이상"]

# 주소에 흔히 쓰는 줄임말 -> 데이터의 시도 이름. 광주광역시·전라남도는 2026년 통합돼 한 시도로 나온다.
SIDO_ALIASES = {
    "서울": "서울특별시", "서울시": "서울특별시", "서울특별시": "서울특별시",
    "부산": "부산광역시", "부산시": "부산광역시", "부산광역시": "부산광역시",
    "대구": "대구광역시", "대구시": "대구광역시", "대구광역시": "대구광역시",
    "인천": "인천광역시", "인천시": "인천광역시", "인천광역시": "인천광역시",
    "대전": "대전광역시", "대전시": "대전광역시", "대전광역시": "대전광역시",
    "울산": "울산광역시", "울산시": "울산광역시", "울산광역시": "울산광역시",
    "세종": "세종특별자치시", "세종시": "세종특별자치시", "세종특별자치시": "세종특별자치시",
    "경기": "경기도", "경기도": "경기도",
    "강원": "강원특별자치도", "강원도": "강원특별자치도", "강원특별자치도": "강원특별자치도",
    "충북": "충청북도", "충청북도": "충청북도",
    "충남": "충청남도", "충청남도": "충청남도",
    "전북": "전북특별자치도", "전라북도": "전북특별자치도", "전북특별자치도": "전북특별자치도",
    "전남": "전남광주통합특별시", "전라남도": "전남광주통합특별시",
    "광주광역시": "전남광주통합특별시", "전남광주통합특별시": "전남광주통합특별시",
    "경북": "경상북도", "경상북도": "경상북도",
    "경남": "경상남도", "경상남도": "경상남도",
    "제주": "제주특별자치도", "제주도": "제주특별자치도", "제주특별자치도": "제주특별자치도",
}

_cache = {}  # {"rows": (시각, 월, 행목록)}


def _service_key():
    return os.getenv("ODCLOUD_SERVICE_KEY")


def _fetch_latest_rows():
    """가장 최근 월 데이터 전체를 (기준월 'YYYY-MM', 행 목록)으로 돌려준다. 하루 캐시."""
    cached = _cache.get("rows")
    if cached and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1], cached[2]

    docs = httpx.get(SWAGGER_URL, timeout=15).json()
    dated = []
    for path, methods in docs["paths"].items():
        summary = next(iter(methods.values())).get("summary", "")
        match = re.search(r"_(\d{8})$", summary)
        if match:
            dated.append((match.group(1), path))
    if not dated:
        raise RuntimeError("최신 월 데이터를 찾지 못했습니다")
    ymd, path = max(dated)

    rows = []
    page = 1
    while True:
        data = httpx.get(
            f"{BASE_URL}{path}",
            params={"page": page, "perPage": 2000, "serviceKey": _service_key()},
            timeout=30,
        ).json()
        rows.extend(data["data"])
        if len(rows) >= data["totalCount"] or not data["data"]:
            break
        page += 1

    month = f"{ymd[:4]}-{ymd[4:6]}"
    _cache["rows"] = (time.time(), month, rows)
    return month, rows


def match_region(address, rows):
    """센터 주소에서 (시도, 시군구)를 찾는다. 못 찾으면 None."""
    if not address:
        return None
    tokens = address.replace(",", " ").split()
    regions = {}
    for r in rows:
        regions.setdefault(r["시도"], set()).add(r["시군구"])

    sido = next((SIDO_ALIASES[t] for t in tokens if t in SIDO_ALIASES and SIDO_ALIASES[t] in regions), None)
    if sido:
        sigungu = next((t for t in tokens if t in regions[sido]), None)
        if sigungu:
            return sido, sigungu
        if regions[sido] == {"_"}:  # 세종처럼 시군구 구분이 없는 시도
            return sido, "_"
        return None

    # 시도가 주소에 없으면, 전국에서 하나로만 특정되는 시군구 이름일 때만 받아들인다
    for t in tokens:
        owners = [s for s, names in regions.items() if t in names and t != "_"]
        if len(owners) == 1:
            return owners[0], t
    return None


def _num(value):
    """공단이 소수 인원을 가린 "*"는 None, 그 외는 정수."""
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def summarize(rows, sido, sigungu):
    mine = [r for r in rows if r["시도"] == sido and r["시군구"] == sigungu]
    hidden = False
    applicants = 0
    grades = {f: 0 for f in GRADE_FIELDS}
    by_age = {a: 0 for a in AGE_ORDER}
    for r in mine:
        n = _num(r.get("신청자"))
        if n is None:
            hidden = True
        else:
            applicants += n
            if r.get("연령구분") in by_age:
                by_age[r["연령구분"]] += n
        for f in GRADE_FIELDS:
            g = _num(r.get(f))
            if g is None:
                hidden = True
            else:
                grades[f] += g
    return {
        "applicants": applicants,
        "grades": {
            "1등급": grades["1등급"], "2등급": grades["2등급"], "3등급": grades["3등급"],
            "4등급": grades["4등급"], "5등급": grades["5등급"], "인지지원등급": grades["인지지원등급"],
            "등급외": grades["등급외A"] + grades["등급외B"] + grades["등급외C"],
        },
        "by_age": [{"label": a, "applicants": by_age[a]} for a in AGE_ORDER],
        "has_hidden_values": hidden,
    }


def get_region_demand(address):
    if not _service_key():
        return {"ok": False, "message": "ODCLOUD_SERVICE_KEY가 설정되지 않았습니다"}
    try:
        month, rows = _fetch_latest_rows()
    except Exception as e:
        return {"ok": False, "message": f"공공데이터 조회 실패: {e}"}
    region = match_region(address, rows)
    if not region:
        return {"ok": False, "message": "센터 주소에서 시군구를 찾지 못했습니다. 센터 정보에서 주소를 확인해 주세요"}
    sido, sigungu = region
    result = summarize(rows, sido, sigungu)
    result.update({
        "ok": True,
        "region": sido if sigungu == "_" else f"{sido} {sigungu}",
        "base_month": month,
        "source": "국민건강보험공단 노인장기요양보험 등급판정 현황(공공데이터포털)",
    })
    return result
