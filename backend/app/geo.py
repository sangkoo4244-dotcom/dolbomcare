"""도착·퇴실 위치 확인. 위치 좌표는 저장하지 않고, 이용자 주소와의 거리와 판정 결과만 남긴다."""
import math

BASE_RADIUS_M = 100          # 주소 좌표 오차와 건물 구조를 감안한 기본 허용 반경
MAX_ACCURACY_CREDIT_M = 200  # 휴대폰이 알려 준 오차(정확도)는 이만큼까지만 허용 반경에 더한다


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    """두 좌표 사이의 거리(미터, 하버사인 공식)."""
    radius = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * radius * math.asin(math.sqrt(a)))


def judge(resident_lat, resident_lng, lat, lng, accuracy) -> tuple:
    """(판정, 거리m). 판정: ok / far / no_location / no_resident_coords"""
    if lat is None or lng is None:
        return "no_location", None
    if resident_lat is None or resident_lng is None:
        return "no_resident_coords", None
    dist = distance_m(resident_lat, resident_lng, lat, lng)
    credit = min(max(accuracy or 0, 0), MAX_ACCURACY_CREDIT_M)
    return ("ok" if dist <= BASE_RADIUS_M + credit else "far"), dist
