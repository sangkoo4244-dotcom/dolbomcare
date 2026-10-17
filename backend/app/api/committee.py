from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.notifications import notify
from app.auth import require_manager
from app.database import get_db
from app.models import CommitteeMeeting, User

router = APIRouter()


class MeetingBody(BaseModel):
    meeting_date: date
    title: str
    attendees: Optional[str] = None
    agenda: Optional[str] = None
    minutes: Optional[str] = None
    decisions: Optional[str] = None


def _to_dict(m: CommitteeMeeting, names: dict) -> dict:
    return {
        "id": m.id,
        "meeting_date": m.meeting_date.isoformat(),
        "title": m.title,
        "attendees": m.attendees or "",
        "agenda": m.agenda or "",
        "minutes": m.minutes or "",
        "decisions": m.decisions or "",
        "author_name": names.get(m.author_id, ""),
        "updated_at": m.updated_at.strftime("%Y-%m-%d %H:%M") if m.updated_at else None,
    }


def _clean(body: MeetingBody) -> dict:
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="회의 제목을 적어 주세요")
    return {
        "meeting_date": body.meeting_date,
        "title": title,
        "attendees": (body.attendees or "").strip() or None,
        "agenda": (body.agenda or "").strip() or None,
        "minutes": (body.minutes or "").strip() or None,
        "decisions": (body.decisions or "").strip() or None,
    }


def _notify_staff(db: Session, center_id: int, row: CommitteeMeeting) -> None:
    """회의 날짜가 정해지면 같은 센터 요양보호사·사회복지사에게 알린다 (인앱 알림)."""
    agenda = f" 안건: {row.agenda}" if row.agenda else ""
    msg = f"{row.meeting_date.strftime('%m/%d')} {row.title} 회의가 있습니다.{agenda}"
    for u in db.query(User).filter(User.center_id == center_id, User.role.in_(("caregiver", "social_worker")),
                                   User.is_active == True).all():  # noqa: E712
        notify(db, u.id, "staff_meeting", msg)


@router.get("")
def list_meetings(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    rows = db.query(CommitteeMeeting).filter(CommitteeMeeting.center_id == actor.center_id) \
        .order_by(CommitteeMeeting.meeting_date.desc(), CommitteeMeeting.id.desc()).all()
    names = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}
    return {"status": "success", "data": [_to_dict(m, names) for m in rows]}


@router.post("")
def create_meeting(body: MeetingBody, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    row = CommitteeMeeting(center_id=actor.center_id, author_id=actor.id, **_clean(body))
    db.add(row)
    db.flush()
    _notify_staff(db, actor.center_id, row)
    db.commit()
    return {"status": "success", "data": {"id": row.id}}


@router.put("/{meeting_id}")
def update_meeting(meeting_id: int, body: MeetingBody, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    row = db.query(CommitteeMeeting).filter(CommitteeMeeting.id == meeting_id, CommitteeMeeting.center_id == actor.center_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="회의록을 찾을 수 없습니다")
    date_changed = row.meeting_date != body.meeting_date
    for k, v in _clean(body).items():
        setattr(row, k, v)
    row.updated_at = datetime.now()
    if date_changed:
        _notify_staff(db, actor.center_id, row)
    db.commit()
    return {"status": "success"}
