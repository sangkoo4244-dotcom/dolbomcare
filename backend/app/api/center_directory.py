from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.centers import _to_directory_dict
from app.database import get_db
from app.kakao_local import KAKAO_JS_KEY, search_nearby_facilities
from app.models import Center

router = APIRouter()


@router.get("/kakao-js-key")
def get_kakao_js_key():
    """센터 찾기 지도에 쓸 카카오맵 JavaScript 키 (공개 가능 - 도메인으로 제한됨).
    미설정이면 key: null을 내려주고, 화면은 지도 없이 목록만 보여준다."""
    return {"key": KAKAO_JS_KEY}


@router.get("/partner-slots")
def partner_slots(db: Session = Depends(get_db)):
    """파트너 센터 이벤트의 남은 자리 (로그인 없이 볼 수 있다: 요금제·로그인 화면 안내용). 센터 이름은 내려주지 않는다."""
    from app.models import Center as _Center
    from app.plans import PARTNER_SLOT_LIMIT, PLAN_PARTNER
    used = db.query(_Center).filter(_Center.plan == PLAN_PARTNER).count()
    return {"limit": PARTNER_SLOT_LIMIT, "used": used, "remaining": max(0, PARTNER_SLOT_LIMIT - used)}


@router.get("/directory")
def list_public_centers(q: Optional[str] = None, db: Session = Depends(get_db)):
    """센터를 못 정한 예비 보호자용 공개 디렉토리 (로그인 불필요, find_center.html이 쓴다).
    centers.router는 전체에 로그인 필수 의존성이 걸려 있어 이 엔드포인트만 별도 라우터로 분리했다."""
    query = db.query(Center).filter(Center.is_public_listed == True)  # noqa: E712
    if q:
        like = f"%{q.strip()}%"
        query = query.filter((Center.name.like(like)) | (Center.address.like(like)))
    centers = query.order_by(Center.name).all()
    return {"centers": [_to_directory_dict(c) for c in centers]}


@router.get("/nearby-facilities")
def nearby_facilities(q: str):
    """카카오맵 기반 "주변 요양시설" 참고용 검색 (로그인 불필요). 공단 인증 목록이 아니므로
    참고용임을 화면에서 반드시 밝혀야 한다 - app/kakao_local.py 모듈 docstring 참고."""
    return search_nearby_facilities(q)
