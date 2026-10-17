from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.notifications import notify
from app.auth import get_current_user, require_social_or_manager
from app.database import get_db
from app.models import BillingRecord, DailyRecord, Resident, User

router = APIRouter()


class ReturnBody(BaseModel):
    note: str


def require_social(actor: User = Depends(get_current_user)) -> User:
    if actor.role != "social_worker":
        raise HTTPException(status_code=403, detail="사회복지사만 기록을 확인하거나 보완 요청할 수 있습니다")
    return actor


def _status(record: DailyRecord) -> str:
    return record.review_status or "pending"


def _center_record(db: Session, record_id: int, actor: User):
    record = db.query(DailyRecord).filter(DailyRecord.id == record_id).first()
    resident = db.query(Resident).filter(Resident.id == record.resident_id, Resident.center_id == actor.center_id).first() if record else None
    if not record or not resident:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다")
    return record, resident


@router.get("/records")
def list_records(status: str = Query("pending", pattern="^(pending|confirmed|returned|all)$"),
                 days: int = Query(14, ge=1, le=90),
                 db: Session = Depends(get_db),
                 actor: User = Depends(require_social_or_manager)):
    """센터의 요양보호사 제공 기록을 최근 며칠 치로 보여 준다. 탭별 건수는 기간 안 전체 기준이다."""
    since = datetime.now() - timedelta(days=days)
    rows = db.query(DailyRecord, Resident).join(Resident, Resident.id == DailyRecord.resident_id) \
        .filter(Resident.center_id == actor.center_id, DailyRecord.recorded_date >= since) \
        .order_by(DailyRecord.recorded_date.desc(), DailyRecord.id.desc()).all()
    names = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}

    counts = {"pending": 0, "confirmed": 0, "returned": 0}
    items = []
    for record, resident in rows:
        st = _status(record)
        counts[st] += 1
        if status != "all" and st != status:
            continue
        items.append({
            "id": record.id,
            "recorded_date": record.recorded_date.strftime("%Y-%m-%d") if record.recorded_date else None,
            "resident_name": resident.name,
            "caregiver_name": names.get(record.caregiver_id, ""),
            "service_type": record.service_type,
            "benefit_type": record.benefit_type,
            "duration_minutes": record.duration_minutes,
            "care_items": record.care_items,
            "notes": record.notes,
            "status": st,
            "review_note": record.review_note,
            "reviewed_by_name": names.get(record.reviewed_by_id, "") if record.reviewed_by_id else None,
            "reviewed_at": record.reviewed_at.strftime("%Y-%m-%d %H:%M") if record.reviewed_at else None,
        })
    return {"status": "success", "data": {"counts": counts, "items": items}}


@router.post("/records/{record_id}/confirm")
def confirm_record(record_id: int, db: Session = Depends(get_db), actor: User = Depends(require_social)):
    record, _ = _center_record(db, record_id, actor)
    record.review_status = "confirmed"
    record.reviewed_by_id = actor.id
    record.reviewed_at = datetime.now()
    record.review_note = None
    db.commit()
    return {"status": "success"}


@router.post("/records/{record_id}/return")
def return_record(record_id: int, body: ReturnBody, db: Session = Depends(get_db), actor: User = Depends(require_social)):
    note = body.note.strip()
    if not note:
        raise HTTPException(status_code=400, detail="보완 요청 내용을 적어 주세요")
    record, resident = _center_record(db, record_id, actor)
    billing = db.query(BillingRecord).filter(BillingRecord.daily_record_id == record.id).first()
    if billing and billing.approval_status not in ("draft", "rejected"):
        # 청구가 제출·승인된 기록은 요양보호사가 고칠 수 없어서, 보완 요청을 보내면 끝낼 방법이 없다
        raise HTTPException(status_code=400, detail="청구가 제출·승인 단계라 요양보호사가 고칠 수 없습니다. 센터장과 먼저 상의해 주세요")
    record.review_status = "returned"
    record.reviewed_by_id = actor.id
    record.reviewed_at = datetime.now()
    record.review_note = note
    if record.caregiver_id:
        day = record.recorded_date.strftime("%m/%d") if record.recorded_date else ""
        notify(db, record.caregiver_id, "record_returned", f"{resident.name} 어르신 {day} 제공 기록에 보완 요청이 왔습니다: {note}")
    db.commit()
    return {"status": "success"}


@router.get("/pending-count")
def pending_count(db: Session = Depends(get_db), actor: User = Depends(require_social_or_manager)):
    """메뉴 배지용: 최근 14일 안에 사회복지사 확인을 기다리는 제공 기록 수."""
    since = datetime.now() - timedelta(days=14)
    rows = db.query(DailyRecord).join(Resident, Resident.id == DailyRecord.resident_id).filter(
        Resident.center_id == actor.center_id, DailyRecord.recorded_date >= since,
        DailyRecord.review_status.is_(None)).count()
    return {"status": "success", "data": {"pending": rows}}
