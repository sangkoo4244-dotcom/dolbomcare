import base64
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Resident, ResidentMedia, User

router = APIRouter()

# base64 데이터 URL 기준 최대 크기 (약 3MB 원본 이미지에 해당). DB에 직접 저장하는 방식이라
# 너무 큰 사진이 쌓이면 DB가 무거워지니 업로드 단계에서 막는다.
MAX_IMAGE_DATA_LENGTH = 4_000_000


def _check_access(db: Session, resident_id: int, actor: User) -> Resident:
    resident = db.query(Resident).filter(Resident.id == resident_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    if actor.role == "guardian":
        if resident.guardian_id != actor.id:
            raise HTTPException(status_code=403, detail="본인이 연결된 이용자만 볼 수 있습니다")
    else:
        if resident.center_id != actor.center_id:
            raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    return resident


def _to_dict(m: ResidentMedia, uploader_name: Optional[str] = None) -> dict:
    return {
        "id": m.id,
        "resident_id": m.resident_id,
        "uploaded_by": m.uploaded_by,
        "uploaded_by_name": uploader_name,
        "uploaded_by_role": m.uploaded_by_role,
        "image_data": m.image_data,
        "caption": m.caption,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


class ResidentMediaCreate(BaseModel):
    resident_id: int
    image_data: str  # base64 data URL (예: "data:image/jpeg;base64,...")
    caption: str = ""


@router.post("/")
def upload_media(
    body: ResidentMediaCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """사진 업로드 (요양사·센터장·보호자 모두 가능 - 양쪽 다 올릴 수 있어야 신뢰가 쌓인다)."""
    if actor.role not in ("caregiver", "center_manager", "guardian"):
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    if not body.image_data.startswith("data:image/"):
        raise HTTPException(status_code=400, detail="이미지 데이터 형식이 올바르지 않습니다")
    if len(body.image_data) > MAX_IMAGE_DATA_LENGTH:
        raise HTTPException(status_code=400, detail="사진 용량이 너무 큽니다 (최대 약 3MB)")

    _check_access(db, body.resident_id, actor)

    media = ResidentMedia(
        resident_id=body.resident_id,
        uploaded_by=actor.id,
        uploaded_by_role=actor.role,
        image_data=body.image_data,
        caption=body.caption or None,
    )
    db.add(media)
    db.commit()
    db.refresh(media)
    return {"status": "success", "data": _to_dict(media, actor.full_name)}


@router.get("/resident/{resident_id}")
def list_media(
    resident_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """한 이용자의 사진첩 (최신순). 직원이 올린 것/보호자가 올린 것 개수를 따로 센다."""
    resident = _check_access(db, resident_id, actor)

    rows = (
        db.query(ResidentMedia)
        .filter(ResidentMedia.resident_id == resident_id)
        .order_by(ResidentMedia.created_at.desc())
        .all()
    )
    uploader_ids = {r.uploaded_by for r in rows}
    names = {u.id: u.full_name for u in db.query(User).filter(User.id.in_(uploader_ids)).all()} if uploader_ids else {}

    staff_count = sum(1 for r in rows if r.uploaded_by_role in ("caregiver", "center_manager"))
    guardian_count = sum(1 for r in rows if r.uploaded_by_role == "guardian")

    return {
        "resident_name": resident.name,
        "staff_count": staff_count,
        "guardian_count": guardian_count,
        "media": [_to_dict(r, names.get(r.uploaded_by)) for r in rows],
    }


@router.delete("/{media_id}")
def delete_media(
    media_id: int,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """본인이 올린 사진이거나 센터장이면 삭제할 수 있다."""
    media = db.query(ResidentMedia).filter(ResidentMedia.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="사진을 찾을 수 없습니다")
    resident = _check_access(db, media.resident_id, actor)
    if media.uploaded_by != actor.id and actor.role != "center_manager":
        raise HTTPException(status_code=403, detail="본인이 올린 사진만 삭제할 수 있습니다")
    db.delete(media)
    db.commit()
    return {"status": "success"}
