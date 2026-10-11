"""국민건강보험공단 장기요양기관 시설별 상세조회 서비스 연동 (공공데이터포털, 서비스 B550928).

필요한 환경변수: NHIS_LTC_SERVICE_KEY (data.go.kr에서 발급받은 일반 인증키). 미설정이면
조용히 "조회 불가" 결과만 돌려주고 나머지 기능은 그대로 동작한다 (alimtalk.py와 같은 패턴).

공단이 응답 필드명을 정의한 활용가이드 문서는 포털 로그인 후에만 열람 가능해, 여기서는
XML 응답의 <item> 하위 요소를 태그명 그대로 돌려준다 - 실제 기관코드로 호출해 화면에서
어떤 필드가 뭔지 확인한 뒤 필요하면 라벨을 다듬는다.
"""
import os
import xml.etree.ElementTree as ET

import httpx

NHIS_LTC_SERVICE_KEY = os.getenv("NHIS_LTC_SERVICE_KEY")
BASE_URL = "https://apis.data.go.kr/B550928/getLtcInsttDetailInfoService02"


def _call(operation: str, institution_code: str) -> dict:
    if not NHIS_LTC_SERVICE_KEY:
        return {"ok": False, "message": "NHIS_LTC_SERVICE_KEY가 설정되지 않았습니다", "fields": {}}
    if not institution_code or not institution_code.strip():
        return {"ok": False, "message": "장기요양기관코드를 입력해 주세요", "fields": {}}

    try:
        response = httpx.get(
            f"{BASE_URL}/{operation}",
            params={"serviceKey": NHIS_LTC_SERVICE_KEY, "longTermAdminSym": institution_code.strip()},
            timeout=10,
        )
        response.raise_for_status()
        root = ET.fromstring(response.text)
    except Exception as e:
        return {"ok": False, "message": f"공단 API 호출 실패: {e}", "fields": {}}

    header = root.find("header")
    result_code = header.findtext("resultCode") if header is not None else None
    result_msg = (header.findtext("resultMsg") if header is not None else None) or "알 수 없는 오류"
    if result_code != "00":
        return {"ok": False, "message": result_msg, "fields": {}}

    item = root.find(".//item")
    if item is None:
        return {"ok": False, "message": "해당 기관코드로 조회된 정보가 없습니다", "fields": {}}

    fields = {child.tag: (child.text or "").strip() for child in item}
    return {"ok": True, "message": result_msg, "fields": fields}


def get_general_status(institution_code: str) -> dict:
    """일반현황: 기관명·주소·전화번호·기관지정일 등."""
    return _call("getGeneralSttusDetailInfoItem02", institution_code)


def get_staff_status(institution_code: str) -> dict:
    """인력현황: 사무업무 인원·의료진·요양보호사·영양사·조리사 등."""
    return _call("getStaffSttusDetailInfoItem02", institution_code)
