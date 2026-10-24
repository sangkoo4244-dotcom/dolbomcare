"""민원·고충 대장: 접수 → 처리 내용 → 처리 완료. 센터장과 사회복지사가 쓰고, 같은 센터 기록만 보인다."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import require_social_or_manager
from app.database import get_db
from app.models import Complaint, Resident, User

router = APIRouter()

CATEGORIES = {"service": "서비스", "caregiver": "요양보호사", "facility": "시설·환경", "other": "기타"}


class ComplaintBody(BaseModel):
    resident_id: Optional[int] = None  # 특정 이용자와 관계없는 민원은 비운다
    complainant: str = Field(..., max_length=100)  # 접수인 (예: 김영희(딸))
    received_date: date
    category: str
    content: str = Field(..., max_length=4000)


class ResolveBody(BaseModel):
    action_taken: str = Field(..., max_length=4000)
    resolved_date: date


def _to_dict(row: Complaint, resident_names: dict, today: date) -> dict:
    return {
        "id": row.id,
        "resident_id": row.resident_id,
        "resident_name": resident_names.get(row.resident_id, ""),
        "complainant": row.complainant,
        "received_date": row.received_date.isoformat(),
        "category": row.category,
        "category_label": CATEGORIES.get(row.category, row.category),
        "content": row.content,
        "status": row.status,
        "action_taken": row.action_taken,
        "resolved_date": row.resolved_date.isoformat() if row.resolved_date else None,
        "days_open": (today - row.received_date).days if row.status == "open" else None,
    }


def _resident_or_none(db: Session, resident_id: Optional[int], center_id: Optional[int]) -> Optional[int]:
    if resident_id is None:
        return None
    r = db.query(Resident).filter(Resident.id == resident_id, Resident.center_id == center_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    return r.id


@router.post("")
def create_complaint(body: ComplaintBody, db: Session = Depends(get_db), actor: User = Depends(require_social_or_manager)):
    if body.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail="민원 분류가 올바르지 않습니다")
    complainant = body.complainant.strip()
    content = body.content.strip()
    if not complainant or not content:
        raise HTTPException(status_code=400, detail="접수인과 민원 내용을 적어 주세요")
    row = Complaint(center_id=actor.center_id, resident_id=_resident_or_none(db, body.resident_id, actor.center_id),
                    complainant=complainant, received_date=body.received_date, category=body.category,
                    content=content, status="open", recorded_by=actor.id)
    db.add(row)
    db.commit()
    return {"status": "success", "data": {"id": row.id}}


@router.get("")
def list_complaints(status: str = Query("open", pattern="^(open|resolved|all)$"), db: Session = Depends(get_db),
                    actor: User = Depends(require_social_or_manager)):
    q = db.query(Complaint).filter(Complaint.center_id == actor.center_id)
    if status != "all":
        q = q.filter(Complaint.status == status)
    rows = q.order_by(Complaint.received_date.desc(), Complaint.id.desc()).all()
    names = {r.id: r.name for r in db.query(Resident).filter(Resident.center_id == actor.center_id).all()}
    today = date.today()
    return {"status": "success", "data": [_to_dict(r, names, today) for r in rows]}


@router.put("/{complaint_id}/resolve")
def resolve_complaint(complaint_id: int, body: ResolveBody, db: Session = Depends(get_db),
                      actor: User = Depends(require_social_or_manager)):
    row = db.query(Complaint).filter(Complaint.id == complaint_id, Complaint.center_id == actor.center_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="민원을 찾을 수 없습니다")
    if row.status == "resolved":
        raise HTTPException(status_code=400, detail="이미 처리 완료된 민원입니다")
    action = body.action_taken.strip()
    if not action:
        raise HTTPException(status_code=400, detail="처리 내용을 적어 주세요")
    if body.resolved_date < row.received_date:
        raise HTTPException(status_code=400, detail="처리일은 접수일보다 빠를 수 없습니다")
    row.status = "resolved"
    row.action_taken = action
    row.resolved_date = body.resolved_date
    db.commit()
    return {"status": "success"}
