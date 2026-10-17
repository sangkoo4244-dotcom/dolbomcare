from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_manager
from app.database import get_db
from app.models import Equipment, User

router = APIRouter()

STATUS_LABEL = {"in_use": "사용중", "repair": "수리중", "disposed": "폐기"}


class EquipmentBody(BaseModel):
    name: str
    category: Optional[str] = None
    quantity: int = 1
    location: Optional[str] = None
    purchase_date: Optional[date] = None
    note: Optional[str] = None


class StatusBody(BaseModel):
    status: str
    disposed_date: Optional[date] = None


def _to_dict(e: Equipment) -> dict:
    return {
        "id": e.id,
        "name": e.name,
        "category": e.category or "",
        "quantity": e.quantity,
        "location": e.location or "",
        "purchase_date": e.purchase_date.isoformat() if e.purchase_date else None,
        "status": e.status,
        "status_label": STATUS_LABEL.get(e.status, e.status),
        "disposed_date": e.disposed_date.isoformat() if e.disposed_date else None,
        "note": e.note or "",
    }


@router.get("")
def list_equipment(status: str = Query("all", pattern="^(all|in_use|repair|disposed)$"),
                   db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    q = db.query(Equipment).filter(Equipment.center_id == actor.center_id)
    if status != "all":
        q = q.filter(Equipment.status == status)
    rows = q.order_by(Equipment.status, Equipment.name).all()
    return {"status": "success", "data": [_to_dict(e) for e in rows]}


@router.post("")
def create_equipment(body: EquipmentBody, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="비품 이름을 적어 주세요")
    if body.quantity < 1:
        raise HTTPException(status_code=400, detail="수량은 1개 이상이어야 합니다")
    row = Equipment(center_id=actor.center_id, name=name, category=(body.category or "").strip() or None,
                    quantity=body.quantity, location=(body.location or "").strip() or None,
                    purchase_date=body.purchase_date, note=(body.note or "").strip() or None)
    db.add(row)
    db.commit()
    return {"status": "success", "data": {"id": row.id}}


@router.post("/{equipment_id}/status")
def change_status(equipment_id: int, body: StatusBody, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    if body.status not in STATUS_LABEL:
        raise HTTPException(status_code=400, detail="상태가 올바르지 않습니다")
    row = db.query(Equipment).filter(Equipment.id == equipment_id, Equipment.center_id == actor.center_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="비품을 찾을 수 없습니다")
    if row.status == "disposed" and body.status != "disposed":
        raise HTTPException(status_code=400, detail="폐기한 비품은 다시 사용 상태로 바꿀 수 없습니다. 새로 등록해 주세요")
    row.status = body.status
    if body.status == "disposed":
        row.disposed_date = body.disposed_date or date.today()
    row.updated_at = datetime.now()
    db.commit()
    return {"status": "success"}
