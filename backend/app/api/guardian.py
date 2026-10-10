import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.users import get_password_hash
from app.auth import get_current_user, require_manager
from app.database import get_db
from app.models import DailyRecord, GuardianInvite, Resident, User

router = APIRouter()

INVITE_VALID_DAYS = 7
CARE_ITEM_LABELS = {
    "meal_assist": "식사 보조", "toilet_assist": "배설 보조", "bath": "목욕·세면", "dressing": "옷 갈아입기",
    "mobility": "이동 보조", "medicine": "투약 확인", "vitals": "체온·혈압 측정", "symptom": "이상 증상 관찰",
    "emotional": "말벗·정서 지원", "cognitive": "인지활동", "cleaning": "청소·정돈", "laundry": "세탁",
    "shopping": "장보기·취사",
}
CONDITION_LABELS = {"good": "좋음", "normal": "보통", "poor": "나쁨"}


class InviteCreate(BaseModel):
    resident_id: int


class SignupBody(BaseModel):
    email: str
    password: str
    full_name: str
    phone: Optional[str] = None
    invite_code: str


def require_guardian(user: User = Depends(get_current_user)) -> User:
    if user.role != "guardian":
        raise HTTPException(status_code=403, detail="보호자만 이용할 수 있습니다")
    return user


@router.post("/invites")
def create_invite(body: InviteCreate, db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    resident = db.query(Resident).filter(Resident.id == body.resident_id, Resident.center_id == manager.center_id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    code = secrets.token_hex(4).upper()
    expires_at = datetime.utcnow() + timedelta(days=INVITE_VALID_DAYS)
    db.add(GuardianInvite(code=code, resident_id=resident.id, center_id=manager.center_id, expires_at=expires_at))
    db.commit()
    return {"code": code, "resident_name": resident.name, "expires_at": expires_at.isoformat()}


@router.post("/signup")
def guardian_signup(body: SignupBody, db: Session = Depends(get_db)):
    """보호자 회원가입. 초대 코드가 있어야 하고, 센터장이 승인하기 전까지는 아무 이용자도 볼 수 없다."""
    invite = db.query(GuardianInvite).filter(GuardianInvite.code == body.invite_code.strip().upper()).first()
    if not invite or invite.status != "issued" or invite.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="초대 코드가 올바르지 않거나 만료되었습니다")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 8자 이상이어야 합니다")
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="이미 등록된 이메일입니다")

    guardian = User(
        email=body.email, hashed_password=get_password_hash(body.password), full_name=body.full_name,
        phone=body.phone, role="guardian", center_id=invite.center_id, is_active=True,
    )
    db.add(guardian)
    db.flush()
    invite.status = "submitted"
    invite.guardian_id = guardian.id
    db.commit()
    return {"status": "success", "message": "가입을 신청했습니다. 센터장이 승인하면 이용할 수 있습니다"}


class RedeemBody(BaseModel):
    invite_code: str


@router.post("/redeem-invite")
def redeem_invite(body: RedeemBody, db: Session = Depends(get_db), guardian: User = Depends(require_guardian)):
    """로그인한 보호자가 초대 코드를 입력한다. 센터장이 승인하기 전까지는 이용자가 보이지 않는다."""
    invite = db.query(GuardianInvite).filter(GuardianInvite.code == body.invite_code.strip().upper()).first()
    if not invite or invite.status != "issued" or invite.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="초대 코드가 올바르지 않거나 만료되었습니다")
    if guardian.center_id is None:
        guardian.center_id = invite.center_id
    elif guardian.center_id != invite.center_id:
        raise HTTPException(status_code=400, detail="다른 센터의 초대 코드입니다")
    invite.status = "submitted"
    invite.guardian_id = guardian.id
    db.commit()
    return {"status": "success", "message": "요청을 보냈습니다. 센터장이 승인하면 이용자 기록을 볼 수 있습니다"}


@router.get("/invites")
def list_invites(db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    """센터의 발급된 초대 코드 전체 조회 (읽기 전용, 보호자 목록/발급내역 표시용)"""
    rows = db.query(GuardianInvite).filter(GuardianInvite.center_id == manager.center_id).order_by(GuardianInvite.created_at.desc()).all()
    residents = {r.id: r for r in db.query(Resident).filter(Resident.center_id == manager.center_id).all()}
    guardians = {u.id: u for u in db.query(User).filter(User.role == "guardian").all()}
    now = datetime.utcnow()
    return {"invites": [
        {
            "id": inv.id,
            "code": inv.code,
            "status": inv.status,
            "expired": inv.expires_at < now and inv.status == "issued",
            "resident_id": inv.resident_id,
            "resident_name": residents[inv.resident_id].name if inv.resident_id in residents else None,
            "guardian_id": inv.guardian_id,
            "guardian_name": guardians[inv.guardian_id].full_name if inv.guardian_id in guardians else None,
            "guardian_phone": guardians[inv.guardian_id].phone if inv.guardian_id in guardians else None,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
            "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
        }
        for inv in rows
    ]}


@router.get("/requests")
def list_requests(db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    rows = db.query(GuardianInvite).filter(
        GuardianInvite.center_id == manager.center_id, GuardianInvite.status == "submitted"
    ).all()
    residents = {r.id: r for r in db.query(Resident).filter(Resident.center_id == manager.center_id).all()}
    guardians = {u.id: u for u in db.query(User).filter(User.role == "guardian").all()}
    return {"requests": [
        {
            "id": r.id,
            "resident_id": r.resident_id,
            "resident_name": residents[r.resident_id].name if r.resident_id in residents else None,
            "resident_gender": residents[r.resident_id].gender if r.resident_id in residents else None,
            "guardian_name": guardians[r.guardian_id].full_name if r.guardian_id in guardians else None,
            "guardian_phone": guardians[r.guardian_id].phone if r.guardian_id in guardians else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]}


def _get_submitted(db: Session, request_id: int, manager: User) -> GuardianInvite:
    invite = db.query(GuardianInvite).filter(GuardianInvite.id == request_id, GuardianInvite.center_id == manager.center_id).first()
    if not invite:
        raise HTTPException(status_code=404, detail="요청을 찾을 수 없습니다")
    if invite.status != "submitted":
        raise HTTPException(status_code=400, detail="대기 중인 요청만 처리할 수 있습니다")
    return invite


@router.post("/requests/{request_id}/approve")
def approve_request(request_id: int, db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    invite = _get_submitted(db, request_id, manager)
    resident = db.query(Resident).filter(Resident.id == invite.resident_id).first()
    resident.guardian_id = invite.guardian_id
    invite.status = "approved"
    db.commit()
    return {"status": "success", "message": "보호자를 연결했습니다"}


@router.post("/requests/{request_id}/reject")
def reject_request(request_id: int, db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    invite = _get_submitted(db, request_id, manager)
    invite.status = "rejected"
    db.commit()
    return {"status": "success", "message": "보호자 요청을 반려했습니다"}


@router.get("/my-residents")
def my_residents(db: Session = Depends(get_db), guardian: User = Depends(require_guardian)):
    rows = db.query(Resident).filter(Resident.guardian_id == guardian.id).all()
    return {"residents": [
        {
            "id": r.id, "name": r.name, "gender": r.gender, "age": r.age,
            "birth_date": r.birth_date.isoformat() if r.birth_date else None,
        }
        for r in rows
    ]}


@router.get("/residents/{resident_id}/visits")
def resident_visits(resident_id: int, days: int = 14, db: Session = Depends(get_db), guardian: User = Depends(require_guardian)):
    """보호자에게는 방문 기록만 보인다. 청구 금액과 요양사 급여는 포함하지 않는다."""
    resident = db.query(Resident).filter(Resident.id == resident_id).first()
    if not resident or resident.guardian_id != guardian.id:
        raise HTTPException(status_code=403, detail="연결된 이용자의 기록만 볼 수 있습니다")

    since = datetime.now() - timedelta(days=days)
    records = db.query(DailyRecord).filter(
        DailyRecord.resident_id == resident_id, DailyRecord.recorded_date >= since
    ).order_by(DailyRecord.recorded_date.desc()).all()
    caregivers = {u.id: u.full_name for u in db.query(User).all()}

    visits = []
    for r in records:
        codes = [c for c in (r.care_items or "").split(",") if c]
        visits.append({
            "date": r.recorded_date.date().isoformat(),
            "time": r.recorded_date.strftime("%H:%M"),
            "duration_minutes": r.duration_minutes,
            "caregiver_name": caregivers.get(r.caregiver_id),
            "care_items": [CARE_ITEM_LABELS.get(c, c) for c in codes],
            "condition": CONDITION_LABELS.get(r.condition, None),
            "notes": r.notes,
            "has_signature": bool(r.signature),
        })
    return {"resident_name": resident.name, "visits": visits}
