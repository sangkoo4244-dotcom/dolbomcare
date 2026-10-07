from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import date
from typing import Optional
from app.database import get_db
from app.auth import get_current_user, require_manager
from app.models import StaffCertificate, User

router = APIRouter()


class CertificateCreate(BaseModel):
    user_id: int
    name: str
    grade: Optional[str] = None
    issued_on: Optional[date] = None
    expires_on: Optional[date] = None


def to_dict(c: StaffCertificate) -> dict:
    return {
        "id": c.id,
        "user_id": c.user_id,
        "name": c.name,
        "grade": c.grade,
        "issued_on": c.issued_on.isoformat() if c.issued_on else None,
        "expires_on": c.expires_on.isoformat() if c.expires_on else None,
    }


@router.get("/")
def list_certificates(
    center_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """센터의 직원 자격증 목록"""
    query = db.query(StaffCertificate)
    if center_id:
        query = query.join(User, User.id == StaffCertificate.user_id).filter(User.center_id == center_id)
    return {"certificates": [to_dict(c) for c in query.order_by(StaffCertificate.id).all()]}


@router.post("/")
def create_certificate(
    body: CertificateCreate,
    db: Session = Depends(get_db),
    manager: User = Depends(require_manager),
):
    """센터장이 직원의 자격증을 등록한다"""
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="자격증 이름을 입력해 주세요")
    target = db.query(User).filter(User.id == body.user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다")
    if target.center_id != manager.center_id:
        raise HTTPException(status_code=403, detail="같은 센터 직원만 등록할 수 있습니다")
    if body.issued_on and body.expires_on and body.expires_on < body.issued_on:
        raise HTTPException(status_code=400, detail="만료일이 발급일보다 빠를 수 없습니다")

    cert = StaffCertificate(
        user_id=body.user_id,
        name=body.name.strip(),
        grade=(body.grade or "").strip() or None,
        issued_on=body.issued_on,
        expires_on=body.expires_on,
    )
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return to_dict(cert)


@router.delete("/{cert_id}")
def delete_certificate(
    cert_id: int,
    db: Session = Depends(get_db),
    manager: User = Depends(require_manager),
):
    """센터장이 자격증을 삭제한다"""
    cert = db.query(StaffCertificate).filter(StaffCertificate.id == cert_id).first()
    if not cert:
        raise HTTPException(status_code=404, detail="자격증을 찾을 수 없습니다")
    target = db.query(User).filter(User.id == cert.user_id).first()
    if target and target.center_id != manager.center_id:
        raise HTTPException(status_code=403, detail="같은 센터 직원의 자격증만 삭제할 수 있습니다")
    db.delete(cert)
    db.commit()
    return {"deleted": cert_id}
