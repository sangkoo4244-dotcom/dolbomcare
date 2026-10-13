"""업무 인계인수 - 담당 요양보호사가 바뀌거나 휴가·교대로 다른 사람이 방문할 때,
이용자의 최근 상태와 주의사항을 다음 담당자에게 남기고 받은 사람이 읽었음을 확인한다.

공단 평가의 '직원 변경 시 이용자 상담'(14일 이내)과 함께, 담당자가 바뀌어도 서비스가 이어지는지 보여 주는 기록이 된다.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.notifications import notify
from app.auth import get_current_user
from app.database import get_db
from app.models import HandoverNote, Resident, User

router = APIRouter()

MIN_CONTENT_LEN = 10


class HandoverBody(BaseModel):
    resident_id: int
    to_caregiver_id: Optional[int] = None  # 비우면 센터 전체 공유(받는 사람 지정 없음)
    content: str


def _names(db: Session, rows: list) -> dict:
    names = {}
    if not rows:
        return names
    for r in db.query(Resident).filter(Resident.id.in_({x.resident_id for x in rows})).all():
        names[("r", r.id)] = r.name
    ids = {x.author_id for x in rows} | {x.to_caregiver_id for x in rows if x.to_caregiver_id}
    for u in db.query(User).filter(User.id.in_(ids)).all():
        names[("u", u.id)] = u.full_name
    return names


def _to_dict(n: HandoverNote, names: dict) -> dict:
    return {
        "id": n.id, "resident_id": n.resident_id, "resident_name": names.get(("r", n.resident_id)),
        "author_name": names.get(("u", n.author_id)),
        "to_caregiver_id": n.to_caregiver_id, "to_caregiver_name": names.get(("u", n.to_caregiver_id)) if n.to_caregiver_id else None,
        "content": n.content, "created_at": n.created_at.isoformat(),
        "acknowledged_at": n.acknowledged_at.isoformat() if n.acknowledged_at else None,
    }


@router.get("/options")
def options(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role not in ("center_manager", "caregiver"):
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    residents = db.query(Resident).filter(Resident.center_id == actor.center_id).order_by(Resident.name).all()
    caregivers = db.query(User).filter(User.center_id == actor.center_id, User.role == "caregiver", User.id != actor.id).order_by(User.full_name).all()
    return {"residents": [{"id": r.id, "name": r.name} for r in residents],
            "caregivers": [{"id": u.id, "name": u.full_name} for u in caregivers]}


@router.get("")
def list_notes(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """센터장은 센터 전체, 요양보호사는 내가 쓴 것과 나에게 온 것만 본다."""
    if actor.role not in ("center_manager", "caregiver"):
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    q = db.query(HandoverNote).filter(HandoverNote.center_id == actor.center_id)
    if actor.role == "caregiver":
        q = q.filter((HandoverNote.author_id == actor.id) | (HandoverNote.to_caregiver_id == actor.id))
    rows = q.order_by(HandoverNote.created_at.desc(), HandoverNote.id.desc()).limit(200).all()
    names = _names(db, rows)
    notes = [_to_dict(n, names) for n in rows]
    unread = sum(1 for n in rows if n.to_caregiver_id == actor.id and not n.acknowledged_at)
    return {"notes": notes, "unread_for_me": unread}


@router.post("")
def create_note(body: HandoverBody, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role not in ("center_manager", "caregiver"):
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    resident = db.query(Resident).filter(Resident.id == body.resident_id, Resident.center_id == actor.center_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    if len(body.content.strip()) < MIN_CONTENT_LEN:
        raise HTTPException(status_code=400, detail=f"인계 내용을 {MIN_CONTENT_LEN}자 이상 구체적으로 적어 주세요 (최근 상태, 주의사항, 선호)")
    if body.to_caregiver_id:
        target = db.query(User).filter(User.id == body.to_caregiver_id, User.center_id == actor.center_id, User.role == "caregiver").first()
        if not target or target.id == actor.id:
            raise HTTPException(status_code=404, detail="받는 요양보호사를 찾을 수 없습니다")
    note = HandoverNote(center_id=actor.center_id, resident_id=resident.id, author_id=actor.id,
                        to_caregiver_id=body.to_caregiver_id, content=body.content.strip())
    db.add(note)
    if body.to_caregiver_id:
        notify(db, body.to_caregiver_id, "handover_received", f"{resident.name} 어르신 인계 메모가 도착했습니다. 방문 전에 확인해 주세요.")
    db.commit()
    return {"status": "success", "data": _to_dict(note, _names(db, [note]))}


@router.post("/{note_id}/ack")
def acknowledge(note_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    note = db.query(HandoverNote).filter(HandoverNote.id == note_id, HandoverNote.center_id == actor.center_id).first()
    if not note or note.to_caregiver_id != actor.id:
        raise HTTPException(status_code=404, detail="받은 인계 메모만 확인할 수 있습니다")
    if not note.acknowledged_at:
        note.acknowledged_at = datetime.utcnow()
        db.commit()
    return {"status": "success"}
