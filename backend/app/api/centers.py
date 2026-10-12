from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.alimtalk_billing import get_usage_summary
from app.auth import require_manager
from app.database import get_db
from app.models import Center, User

router = APIRouter()


def _to_dict(center: Center) -> dict:
    return {
        "id": center.id,
        "name": center.name,
        "address": center.address,
        "phone": center.phone,
        "institution_code": center.institution_code,
        "logo_image": center.logo_image,
        "is_public_listed": bool(center.is_public_listed),
    }


def _to_directory_dict(center: Center) -> dict:
    """공개 디렉토리용 - 센터가 스스로 공개 동의한 항목만, 운영 관련 정보(알림톡 잔액 등)는 빼고 내려준다."""
    return {
        "id": center.id,
        "name": center.name,
        "address": center.address,
        "phone": center.phone,
        "logo_image": center.logo_image,
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
    if body.address is not None:
        center.address = body.address
    if body.phone is not None:
        center.phone = body.phone
    if body.institution_code is not None:
        center.institution_code = body.institution_code
    if body.logo_image is not None:
        center.logo_image = body.logo_image or None
    if body.is_public_listed is not None:
        center.is_public_listed = body.is_public_listed

    db.commit()
    db.refresh(center)
    return {"status": "success", "data": _to_dict(center)}


@router.get("/me/alimtalk-usage")
def get_my_alimtalk_usage(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    """내 센터의 이번 달 알림톡 발송 현황·잔액 (센터장 전용)."""
    return get_usage_summary(db, actor.center_id)
