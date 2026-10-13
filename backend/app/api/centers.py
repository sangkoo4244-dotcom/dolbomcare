from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.alimtalk_billing import get_usage_summary
from app.auth import require_manager
from app.database import get_db
from app.kakao_local import geocode_address
from app.ltc_stats import get_region_demand
from app.models import Center, User

router = APIRouter()

# 장기요양보험 급여 종류 중 센터가 실제로 제공 중인 항목을 직접 고르게 한다 (추측으로 채우지 않음).
SERVICE_TYPE_OPTIONS = ["방문요양", "방문목욕", "방문간호", "주야간보호", "단기보호", "가사활동 지원"]


def _to_dict(center: Center) -> dict:
    return {
        "id": center.id,
        "name": center.name,
        "address": center.address,
        "phone": center.phone,
        "institution_code": center.institution_code,
        "logo_image": center.logo_image,
        "is_public_listed": bool(center.is_public_listed),
        "latitude": center.latitude,
        "longitude": center.longitude,
        "service_types": [s for s in (center.service_types or "").split(",") if s],
    }


def _to_directory_dict(center: Center) -> dict:
    """공개 디렉토리용 - 센터가 스스로 공개 동의한 항목만, 운영 관련 정보(알림톡 잔액 등)는 빼고 내려준다."""
    return {
        "id": center.id,
        "name": center.name,
        "address": center.address,
        "phone": center.phone,
        "logo_image": center.logo_image,
        "latitude": center.latitude,
        "longitude": center.longitude,
        "service_types": [s for s in (center.service_types or "").split(",") if s],
        # 실제 11자리 기관코드 자체는 공개하지 않고, 등록 여부만 - 공단에 등록된 기관임을 보호자가 확인할 수 있게
        "institution_verified": bool(center.institution_code),
    }


@router.get("/me")
def get_my_center(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    """내 센터 정보 조회 (센터장 전용)."""
    center = db.query(Center).filter(Center.id == actor.center_id).first()
    if not center:
        raise HTTPException(status_code=404, detail="센터를 찾을 수 없습니다")
    return _to_dict(center)


class CenterUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    institution_code: Optional[str] = None
    logo_image: Optional[str] = None  # base64 data URL. 빈 문자열이면 이미지 제거로 본다
    is_public_listed: Optional[bool] = None  # 예비 보호자용 공개 디렉토리 노출 동의
    service_types: Optional[list] = None  # SERVICE_TYPE_OPTIONS 중 센터가 고른 항목


@router.put("/me")
def update_my_center(
    body: CenterUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_manager),
):
    """내 센터 정보 수정 (센터장 전용)."""
    center = db.query(Center).filter(Center.id == actor.center_id).first()
    if not center:
        raise HTTPException(status_code=404, detail="센터를 찾을 수 없습니다")

    if body.name is not None:
        center.name = body.name
    if body.address is not None and body.address != center.address:
        center.address = body.address
        geocoded = geocode_address(body.address)
        if geocoded:
            center.latitude, center.longitude = geocoded
        else:
            center.latitude, center.longitude = None, None
    if body.phone is not None:
        center.phone = body.phone
    if body.institution_code is not None:
        center.institution_code = body.institution_code
    if body.logo_image is not None:
        center.logo_image = body.logo_image or None
    if body.is_public_listed is not None:
        center.is_public_listed = body.is_public_listed
    if body.service_types is not None:
        valid = [s for s in body.service_types if s in SERVICE_TYPE_OPTIONS]
        center.service_types = ",".join(valid) if valid else None

    db.commit()
    db.refresh(center)
    return {"status": "success", "data": _to_dict(center)}


@router.get("/me/alimtalk-usage")
def get_my_alimtalk_usage(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    """내 센터의 이번 달 알림톡 발송 현황·잔액 (센터장 전용)."""
    return get_usage_summary(db, actor.center_id)


@router.get("/me/region-demand")
def get_my_region_demand(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    """센터 주소 지역(시군구)의 장기요양 등급판정 신청 현황 (센터장 전용, 공공데이터 통계)."""
    center = db.query(Center).filter(Center.id == actor.center_id).first()
    if not center:
        raise HTTPException(status_code=404, detail="센터를 찾을 수 없습니다")
    return get_region_demand(center.address)
