"""센터가 보호자에게 보내는 문자 (안내 문자). 발송 건수는 알림톡과 같은 무료 한도·충전 잔액에서 차감한다.
발송 키가 설정되어 있지 않으면 아무것도 보내지 않고, 건수도 차감하지 않는다."""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.alimtalk import send_sms, sms_configured
from app.alimtalk_billing import reserve_send
from app.auth import require_manager
from app.database import get_db
from app.models import Resident, ResidentGuardian, SmsLog, User

router = APIRouter()
MAX_TEXT = 300


class SmsSendIn(BaseModel):
    resident_ids: List[int] = Field(..., min_length=1, max_length=200)
    text: str = Field(..., min_length=1, max_length=MAX_TEXT)


def _to_dict(row: SmsLog, names: dict) -> dict:
    return {"id": row.id, "resident_name": names.get(row.resident_id, ""), "phone": row.phone, "text": row.text,
            "status": row.status, "created_at": row.created_at.isoformat(timespec="minutes") if row.created_at else None}


def _recipient_phones(db: Session, resident: Resident) -> list:
    """주 보호자와 추가 보호자의 연락처를 중복 없이 모은다. 같은 번호에는 한 번만 보낸다."""
    phones = []
    for raw in [resident.guardian_phone] + [g.phone for g in db.query(ResidentGuardian).filter(ResidentGuardian.resident_id == resident.id).order_by(ResidentGuardian.id).all()]:
        phone = (raw or "").strip()
        if phone and phone not in phones:
            phones.append(phone)
    return phones


@router.post("/send")
def send_guardian_sms(body: SmsSendIn, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="보낼 내용을 적어 주세요")
    if not sms_configured():
        raise HTTPException(status_code=503, detail="문자 발송이 아직 설정되지 않았습니다. 운영자에게 문의해 주세요")
    residents = db.query(Resident).filter(Resident.center_id == actor.center_id, Resident.id.in_(body.resident_ids)).all()
    counts = {"sent": 0, "failed": 0, "no_phone": 0, "blocked": 0}
    for resident in residents:
        phones = _recipient_phones(db, resident)
        if not phones:
            counts["no_phone"] += 1
            db.add(SmsLog(center_id=actor.center_id, resident_id=resident.id, sent_by=actor.id, phone="", text=text, status="no_phone"))
            continue
        for phone in phones:
            if not reserve_send(db, actor.center_id):
                status = "blocked"  # 무료 한도와 충전 잔액이 모두 없으면 보내지 않는다
            else:
                status = "sent" if send_sms(phone, text) else "failed"
            counts[status] += 1
            db.add(SmsLog(center_id=actor.center_id, resident_id=resident.id, sent_by=actor.id, phone=phone, text=text, status=status))
    db.commit()
    return {"status": "success", "data": counts}


@router.get("/history")
def sms_history(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    rows = db.query(SmsLog).filter(SmsLog.center_id == actor.center_id).order_by(SmsLog.created_at.desc()).limit(100).all()
    names = {r.id: r.name for r in db.query(Resident).filter(Resident.center_id == actor.center_id).all()}
    return {"status": "success", "data": [_to_dict(r, names) for r in rows]}
