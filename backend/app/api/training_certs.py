import base64
import re
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_manager
from app.database import get_db
from app.models import TrainingCertificate, User

router = APIRouter()

MAX_FILE_BYTES = 2 * 1024 * 1024
ALLOWED_TYPES = ("application/pdf", "image/png", "image/jpeg")
DATA_URL = re.compile(r"^data:(application/pdf|image/png|image/jpeg);base64,([A-Za-z0-9+/=]+)$")


class CertBody(BaseModel):
    user_id: int
    title: str
    completed_on: date
    hours: Optional[int] = None
    issuer: Optional[str] = None
    file_name: Optional[str] = None
    file_data: Optional[str] = None


def _check_file(file_data: Optional[str]) -> Optional[str]:
    if not file_data:
        return None
    m = DATA_URL.match(file_data)
    if not m:
        raise HTTPException(status_code=400, detail="PDF 또는 이미지(PNG, JPG) 파일만 올릴 수 있습니다")
    try:
        size = len(base64.b64decode(m.group(2), validate=True))
    except Exception:
        raise HTTPException(status_code=400, detail="파일을 읽을 수 없습니다")
    if size > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail="파일은 2MB 이하만 올릴 수 있습니다")
    return file_data


def _to_dict(c: TrainingCertificate, names: dict) -> dict:
    return {
        "id": c.id,
        "user_id": c.user_id,
        "staff_name": names.get(c.user_id, ""),
        "title": c.title,
        "completed_on": c.completed_on.isoformat(),
        "hours": c.hours,
        "issuer": c.issuer or "",
        "file_name": c.file_name or "",
        "has_file": bool(c.file_data),
    }


@router.get("")
def list_certs(user_id: Optional[int] = Query(None), db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """센터장은 센터 직원 전체, 그 밖의 직원은 본인 수료증만 본다."""
    if not actor.center_id or actor.role == "guardian":
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    q = db.query(TrainingCertificate).filter(TrainingCertificate.center_id == actor.center_id)
    if actor.role != "center_manager":
        q = q.filter(TrainingCertificate.user_id == actor.id)
    elif user_id:
        q = q.filter(TrainingCertificate.user_id == user_id)
    rows = q.order_by(TrainingCertificate.completed_on.desc(), TrainingCertificate.id.desc()).all()
    names = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}
    return {"status": "success", "data": [_to_dict(c, names) for c in rows]}


@router.post("")
def create_cert(body: CertBody, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="교육 이름을 적어 주세요")
    staff = db.query(User).filter(User.id == body.user_id, User.center_id == actor.center_id).first()
    if not staff or staff.role == "guardian":
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다")
    if body.hours is not None and body.hours < 0:
        raise HTTPException(status_code=400, detail="교육 시간은 0 이상이어야 합니다")
    row = TrainingCertificate(center_id=actor.center_id, user_id=staff.id, title=title, completed_on=body.completed_on,
                              hours=body.hours, issuer=(body.issuer or "").strip() or None,
                              file_name=(body.file_name or "").strip()[:200] or None, file_data=_check_file(body.file_data),
                              created_by=actor.id)
    db.add(row)
    db.commit()
    return {"status": "success", "data": {"id": row.id}}


@router.get("/{cert_id}/file")
def get_file(cert_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    row = db.query(TrainingCertificate).filter(TrainingCertificate.id == cert_id, TrainingCertificate.center_id == actor.center_id).first()
    if not row or not row.file_data:
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    if actor.role != "center_manager" and row.user_id != actor.id:
        raise HTTPException(status_code=403, detail="본인 수료증만 볼 수 있습니다")
    m = DATA_URL.match(row.file_data)
    return Response(content=base64.b64decode(m.group(2)), media_type=m.group(1),
                    headers={"Content-Disposition": f'inline; filename="{row.file_name or "certificate"}"'})


@router.delete("/{cert_id}")
def delete_cert(cert_id: int, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    row = db.query(TrainingCertificate).filter(TrainingCertificate.id == cert_id, TrainingCertificate.center_id == actor.center_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="수료증을 찾을 수 없습니다")
    db.delete(row)
    db.commit()
    return {"status": "success"}
