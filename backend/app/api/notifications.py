from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Notification, User
from app.alimtalk import send_alimtalk, TEMPLATE_IDS

router = APIRouter()


def notify(db: Session, user_id: int, kind: str, message: str) -> None:
    """호출한 쪽에서 commit한다 (결정과 알림이 함께 저장되도록)."""
    db.add(Notification(user_id=user_id, kind=kind, message=message))

    if TEMPLATE_IDS.get(kind):
        user = db.query(User).filter(User.id == user_id).first()
        if user and user.phone and user.alimtalk_opt_in:
            send_alimtalk(user.phone, kind, message)


def _to_dict(n: Notification) -> dict:
    return {
        "id": n.id,
        "kind": n.kind,
        "message": n.message,
        "is_read": bool(n.is_read),
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


@router.get("/mine")
def list_my_notifications(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    rows = (
        db.query(Notification)
        .filter(Notification.user_id == actor.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(50)
        .all()
    )
    unread = db.query(Notification).filter(Notification.user_id == actor.id, Notification.is_read == False).count()  # noqa: E712
    return {"notifications": [_to_dict(n) for n in rows], "unread_count": unread}


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    db.query(Notification).filter(Notification.user_id == actor.id, Notification.is_read == False).update(  # noqa: E712
        {"is_read": True}, synchronize_session=False
    )
    db.commit()
    return {"status": "success"}


@router.post("/{notification_id}/read")
def mark_read(notification_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    notification = db.query(Notification).filter(
        Notification.id == notification_id, Notification.user_id == actor.id
    ).first()
    if not notification:
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다")
    notification.is_read = True
    db.commit()
    return {"status": "success"}
