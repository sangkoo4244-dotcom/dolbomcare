from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.notifications import notify
from app.auth import get_current_user, require_manager
from app.database import get_db
from app.models import DailyRecord, Resident, ResidentMessage, ResidentThreadRead, Schedule, User

router = APIRouter()

ROLE_LABELS = {"guardian": "보호자", "caregiver": "요양사", "center_manager": "센터장"}
RECENT_DAYS = 60
MAX_LENGTH = 1000


class MessageCreate(BaseModel):
    body: str


def _resident_or_404(db: Session, resident_id: int) -> Resident:
    resident = db.query(Resident).filter(Resident.id == resident_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    return resident


def _check_access(resident: Resident, user: User) -> None:
    """보호자는 연결된 이용자만, 직원은 같은 센터 이용자만 볼 수 있다."""
    if user.role == "guardian":
        if resident.guardian_id == user.id:
            return
    elif user.center_id == resident.center_id:
        return
    raise HTTPException(status_code=403, detail="이 이용자의 메시지를 볼 수 없습니다")


def _staff_recipients(db: Session, resident: Resident, sender_id: int) -> set:
    """보호자 메시지를 받을 사람: 최근 방문한 요양사와 센터장."""
    since = datetime.now() - timedelta(days=RECENT_DAYS)
    caregiver_ids = {
        r.caregiver_id for r in db.query(DailyRecord).filter(
            DailyRecord.resident_id == resident.id, DailyRecord.recorded_date >= since)
    } | {
        s.caregiver_id for s in db.query(Schedule).filter(
            Schedule.resident_id == resident.id, Schedule.scheduled_date >= since)
    }
    manager_ids = {
        u.id for u in db.query(User).filter(User.center_id == resident.center_id, User.role == "center_manager")
    }
    return (caregiver_ids | manager_ids) - {sender_id, None}


def _accessible_residents(db: Session, user: User) -> list:
    if user.role == "guardian":
        return db.query(Resident).filter(Resident.guardian_id == user.id).all()
    return db.query(Resident).filter(Resident.center_id == user.center_id).all()


def _last_read_map(db: Session, user_id: int, resident_id: int) -> dict:
    row = db.query(ResidentThreadRead).filter(
        ResidentThreadRead.user_id == user_id, ResidentThreadRead.resident_id == resident_id
    ).first()
    return row.last_read_message_id if row else 0


def _unread_for(db: Session, user: User, resident_id: int) -> int:
    last_read = _last_read_map(db, user.id, resident_id)
    return db.query(ResidentMessage).filter(
        ResidentMessage.resident_id == resident_id,
        ResidentMessage.id > last_read,
        ResidentMessage.sender_id != user.id,
        ResidentMessage.is_deleted == False,  # noqa: E712
    ).count()


def _to_dict(m: ResidentMessage, names: dict, read_by: list) -> dict:
    return {
        "id": m.id,
        "sender_id": m.sender_id,
        "sender_name": names.get(m.sender_id),
        "sender_role": m.sender_role,
        "sender_role_label": ROLE_LABELS.get(m.sender_role, m.sender_role),
        "body": m.body,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "read_by": read_by,
    }


@router.get("/residents/{resident_id}")
def list_messages(resident_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    resident = _resident_or_404(db, resident_id)
    _check_access(resident, user)
    rows = db.query(ResidentMessage).filter(
        ResidentMessage.resident_id == resident_id, ResidentMessage.is_deleted == False  # noqa: E712
    ).order_by(ResidentMessage.created_at, ResidentMessage.id).all()
    names = {u.id: u.full_name for u in db.query(User).all()}
    readers = db.query(ResidentThreadRead).filter(ResidentThreadRead.resident_id == resident_id).all()
    out = []
    for m in rows:
        read_by = sorted(
            names[r.user_id] for r in readers
            if r.user_id != m.sender_id and r.user_id in names and r.last_read_message_id >= m.id
        )
        out.append(_to_dict(m, names, read_by))
    return {"resident_name": resident.name, "messages": out}


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    by_resident = {}
    for resident in _accessible_residents(db, user):
        count = _unread_for(db, user, resident.id)
        if count:
            by_resident[resident.id] = count
    return {"unread_count": sum(by_resident.values()), "by_resident": by_resident}


@router.post("/residents/{resident_id}/read")
def mark_read(resident_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    resident = _resident_or_404(db, resident_id)
    _check_access(resident, user)
    latest = db.query(ResidentMessage.id).filter(ResidentMessage.resident_id == resident_id).order_by(ResidentMessage.id.desc()).first()
    row = db.query(ResidentThreadRead).filter(
        ResidentThreadRead.user_id == user.id, ResidentThreadRead.resident_id == resident_id
    ).first()
    if not row:
        row = ResidentThreadRead(user_id=user.id, resident_id=resident_id, last_read_message_id=0)
        db.add(row)
    row.last_read_message_id = max(row.last_read_message_id or 0, latest[0] if latest else 0)
    db.commit()
    return {"status": "success"}


@router.post("/residents/{resident_id}")
def send_message(resident_id: int, body: MessageCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    resident = _resident_or_404(db, resident_id)
    _check_access(resident, user)
    text = body.body.strip()
    if not text:
        raise HTTPException(status_code=400, detail="메시지 내용을 입력해 주세요")
    if len(text) > MAX_LENGTH:
        raise HTTPException(status_code=400, detail=f"메시지는 {MAX_LENGTH}자 이하로 입력해 주세요")

    message = ResidentMessage(
        center_id=resident.center_id, resident_id=resident.id, sender_id=user.id, sender_role=user.role, body=text,
    )
    db.add(message)

    if user.role == "guardian":
        for staff_id in _staff_recipients(db, resident, user.id):
            notify(db, staff_id, "message_received", f"{resident.name} 보호자 메시지: {text[:30]}")
    elif resident.guardian_id and resident.guardian_id != user.id:
        notify(db, resident.guardian_id, "message_received", f"{resident.name} 센터 메시지: {text[:30]}")
    db.commit()
    return {"status": "success", "message": "메시지를 보냈습니다"}


@router.delete("/{message_id}")
def delete_message(message_id: int, db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    message = db.query(ResidentMessage).filter(
        ResidentMessage.id == message_id, ResidentMessage.center_id == manager.center_id
    ).first()
    if not message or message.is_deleted:
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다")
    message.is_deleted = True
    db.commit()
    return {"status": "success", "message": "메시지를 삭제했습니다"}
