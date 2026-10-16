"""방문간호지시서 보관: 센터장이 발급일·번호와 파일을 올리고, 같은 센터 직원이 확인한다."""
import base64
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_manager
from app.database import get_db
from app.models import NursingOrder, Resident, User

router = APIRouter()
MAX_BYTES = 3 * 1024 * 1024
ALLOWED_TYPES = ("application/pdf", "image/png", "image/jpeg")


class OrderBody(BaseModel):
    resident_id: int
    issued_date: date
    order_no: Optional[str] = Field(None, max_length=60)
    physician: Optional[str] = Field(None, max_length=100)
    file_name: Optional[str] = Field(None, max_length=200)
    file_type: Optional[str] = None
    file_data: Optional[str] = None  # base64 (data URL 앞부분 없이)


def _resident_in_center(db: Session, resident_id: int, center_id: Optional[int]) -> Resident:
    resident = db.query(Resident).filter(Resident.id == resident_id, Resident.center_id == center_id).first() if center_id else None
    if not resident:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    return resident


def _info(order: NursingOrder) -> dict:
    return {"id": order.id, "resident_id": order.resident_id, "issued_date": order.issued_date.isoformat(),
            "order_no": order.order_no, "physician": order.physician, "file_name": order.file_name,
            "file_type": order.file_type, "has_file": bool(order.file_data)}


@router.post("")
def create_order(body: OrderBody, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    _resident_in_center(db, body.resident_id, actor.center_id)
    if body.file_data:
        if body.file_type not in ALLOWED_TYPES:
            raise HTTPException(status_code=400, detail="파일은 PDF 또는 PNG·JPG 사진으로 올려 주세요")
        try:
            size = len(base64.b64decode(body.file_data, validate=True))
        except Exception:
            raise HTTPException(status_code=400, detail="파일 내용을 읽지 못했습니다")
        if size > MAX_BYTES:
            raise HTTPException(status_code=400, detail="파일은 3MB 이하로 올려 주세요")
    order = NursingOrder(center_id=actor.center_id, resident_id=body.resident_id, issued_date=body.issued_date,
                         order_no=(body.order_no or "").strip() or None, physician=(body.physician or "").strip() or None,
                         file_name=body.file_name, file_type=body.file_type, file_data=body.file_data, uploaded_by=actor.id)
    db.add(order)
    db.commit()
    return {"status": "success", "data": _info(order)}


@router.get("")
def list_orders(resident_id: int = Query(...), db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role not in ("center_manager", "caregiver"):
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    _resident_in_center(db, resident_id, actor.center_id)
    rows = db.query(NursingOrder).filter(NursingOrder.resident_id == resident_id, NursingOrder.center_id == actor.center_id) \
        .order_by(NursingOrder.issued_date.desc()).all()
    return {"status": "success", "data": [_info(o) for o in rows]}


@router.get("/{order_id}/file")
def order_file(order_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    order = db.query(NursingOrder).filter(NursingOrder.id == order_id, NursingOrder.center_id == actor.center_id).first() if actor.center_id else None
    if not order or actor.role not in ("center_manager", "caregiver") or not order.file_data:
        raise HTTPException(status_code=404, detail="지시서 파일을 찾을 수 없습니다")
    return {"status": "success", "data": {"file_name": order.file_name, "file_type": order.file_type, "file_data": order.file_data}}


@router.delete("/{order_id}")
def delete_order(order_id: int, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    order = db.query(NursingOrder).filter(NursingOrder.id == order_id, NursingOrder.center_id == actor.center_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="지시서를 찾을 수 없습니다")
    db.delete(order)
    db.commit()
    return {"status": "success"}
