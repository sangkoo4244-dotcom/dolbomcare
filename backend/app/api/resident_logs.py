from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Resident, ResidentLog, User

router = APIRouter()

KINDS = ("observation", "feedback")
SOURCES = ("수급자", "보호자", "요양보호사", "기타")
WRITER_ROLES = ("caregiver", "center_manager", "social_worker")


class LogBody(BaseModel):
    resident_id: int
    log_date: date
    kind: str
    source: Optional[str] = None
    content: str
    action: Optional[str] = None


def _writer_check(actor: User) -> None:
    if actor.role not in WRITER_ROLES or not actor.center_id:
        raise HTTPException(status_code=403, detail="기록을 쓸 수 있는 권한이 없습니다")


def _clean(body: LogBody) -> dict:
    if body.kind not in KINDS:
        raise HTTPException(status_code=400, detail="기록 종류가 올바르지 않습니다")
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="내용을 적어 주세요")
    if body.kind == "feedback" and body.source not in SOURCES:
        raise HTTPException(status_code=400, detail="의견을 낸 사람을 골라 주세요")
    is_feedback = body.kind == "feedback"
    return {
        "log_date": body.log_date,
        "kind": body.kind,
        "source": body.source if is_feedback else None,
        "content": content,
        "action": ((body.action or "").strip() or None) if is_feedback else None,
    }


def _to_dict(r: ResidentLog, names: dict) -> dict:
    return {
        "id": r.id,
        "resident_id": r.resident_id,
        "log_date": r.log_date.isoformat(),
        "kind": r.kind,
        "source": r.source or "",
        "content": r.content,
        "action": r.action or "",
        "author_id": r.author_id,
        "author_name": names.get(r.author_id, ""),
        "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M") if r.updated_at else None,
    }


@router.get("")
def list_logs(resident_id: int = Query(...), kind: str = Query("observation", pattern="^(observation|feedback)$"),
              db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role not in ("caregiver", "center_manager", "social_worker") or not actor.center_id:
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    resident = db.query(Resident).filter(Resident.id == resident_id, Resident.center_id == actor.center_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    rows = db.query(ResidentLog).filter(ResidentLog.resident_id == resident_id, ResidentLog.kind == kind,
                                        ResidentLog.center_id == actor.center_id) \
        .order_by(ResidentLog.log_date.desc(), ResidentLog.id.desc()).limit(200).all()
    names = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}
    return {"status": "success", "data": {"resident_name": resident.name, "items": [_to_dict(r, names) for r in rows]}}


@router.post("")
def create_log(body: LogBody, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    _writer_check(actor)
    resident = db.query(Resident).filter(Resident.id == body.resident_id, Resident.center_id == actor.center_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    row = ResidentLog(center_id=actor.center_id, resident_id=resident.id, author_id=actor.id, **_clean(body))
    db.add(row)
    db.commit()
    return {"status": "success", "data": {"id": row.id}}


@router.put("/{log_id}")
def update_log(log_id: int, body: LogBody, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    _writer_check(actor)
    row = db.query(ResidentLog).filter(ResidentLog.id == log_id, ResidentLog.center_id == actor.center_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다")
    if row.author_id != actor.id and actor.role != "center_manager":
        raise HTTPException(status_code=403, detail="작성한 본인이나 센터장만 고칠 수 있습니다")
    for k, v in _clean(body).items():
        setattr(row, k, v)
    row.updated_at = datetime.now()
    db.commit()
    return {"status": "success"}
