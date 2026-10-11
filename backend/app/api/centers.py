from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

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

    db.commit()
    db.refresh(center)
    return {"status": "success", "data": _to_dict(center)}
