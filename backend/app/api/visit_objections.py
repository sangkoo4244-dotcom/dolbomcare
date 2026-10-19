"""보호자 이의 제기: "그 날 방문이 없었다"는 신고. 센터장이 처리하기 전까지 그 날짜의 청구는 승인되지 않는다."""
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.notifications import notify
from app.auth import get_current_user, require_manager
from app.database import get_db
from app.models import Resident, User, VisitObjection

router = APIRouter()


class ObjectionCreate(BaseModel):
    resident_id: int
    visit_date: date
    memo: str = Field(..., min_length=2, max_length=500)


class ResolveBody(BaseModel):
    resolution_note: str = Field(..., min_length=2, max_length=500)


def open_objection_for(db: Session, resident_id: int, visit_day: date):
    """같은 이용자·같은 날짜에 처리되지 않은 이의가 있으면 돌려준다 (청구 승인 보류에 쓴다)."""
    return db.query(VisitObjection).filter(
        VisitObjection.resident_id == resident_id, VisitObjection.visit_date == visit_day,
        VisitObjection.status == "open").first()


def _to_dict(o: VisitObjection, names: dict) -> dict:
    return {
        "id": o.id, "resident_id": o.resident_id, "visit_date": o.visit_date.isoformat() if o.visit_date else None,
        "memo": o.memo, "status": o.status, "guardian_name": names.get(o.guardian_id),
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "resolved_at": o.resolved_at.isoformat() if o.resolved_at else None,
        "resolution_note": o.resolution_note,
    }


@router.post("")
def report_objection(body: ObjectionCreate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role != "guardian":
        raise HTTPException(status_code=403, detail="보호자만 방문 이의를 신고할 수 있습니다")
    resident = db.query(Resident).filter(Resident.id == body.resident_id).first()
    if not resident or resident.guardian_id != actor.id:
        raise HTTPException(status_code=403, detail="연결된 이용자의 방문만 신고할 수 있습니다")
    if body.visit_date > datetime.now().date():
        raise HTTPException(status_code=400, detail="아직 오지 않은 날짜는 신고할 수 없습니다")

    existing = open_objection_for(db, resident.id, body.visit_date)
    if existing:
        return {"status": "success", "message": "이미 신고된 날짜입니다. 센터에서 확인 중입니다",
                "data": _to_dict(existing, {actor.id: actor.full_name})}

    objection = VisitObjection(center_id=resident.center_id, resident_id=resident.id, guardian_id=actor.id,
                               visit_date=body.visit_date, memo=body.memo.strip())
    db.add(objection)
    db.flush()
    for manager in db.query(User).filter(User.center_id == resident.center_id, User.role == "center_manager").all():
        notify(db, manager.id, "objection_raised",
               f"{resident.name} 보호자가 {body.visit_date.isoformat()} 방문 사실 없음을 신고했습니다. "
               "처리 전까지 그 날짜 청구는 승인되지 않습니다")
    db.commit()
    db.refresh(objection)
    return {"status": "success", "message": "신고가 접수되었습니다. 센터에서 확인한 뒤 답변이 갑니다",
            "data": _to_dict(objection, {actor.id: actor.full_name})}


@router.get("/mine")
def my_objections(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role != "guardian":
        raise HTTPException(status_code=403, detail="보호자만 이용할 수 있습니다")
    rows = db.query(VisitObjection).filter(VisitObjection.guardian_id == actor.id) \
        .order_by(VisitObjection.created_at.desc()).limit(100).all()
    return {"objections": [_to_dict(o, {actor.id: actor.full_name}) for o in rows]}


@router.get("")
def center_objections(db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    rows = db.query(VisitObjection).filter(VisitObjection.center_id == manager.center_id) \
        .order_by(VisitObjection.status.desc(), VisitObjection.created_at.desc()).limit(200).all()
    names = {u.id: u.full_name for u in db.query(User).filter(User.center_id == manager.center_id).all()}
    return {"objections": [_to_dict(o, names) for o in rows]}


@router.post("/{objection_id}/resolve")
def resolve_objection(objection_id: int, body: ResolveBody, db: Session = Depends(get_db),
                      manager: User = Depends(require_manager)):
    objection = db.query(VisitObjection).filter(VisitObjection.id == objection_id,
                                                VisitObjection.center_id == manager.center_id).first()
    if not objection:
        raise HTTPException(status_code=404, detail="신고를 찾을 수 없습니다")
    if objection.status != "open":
        raise HTTPException(status_code=400, detail="이미 처리된 신고입니다")
    objection.status = "resolved"
    objection.resolved_by_id = manager.id
    objection.resolved_at = datetime.now()
    objection.resolution_note = body.resolution_note.strip()
    notify(db, objection.guardian_id, "objection_resolved",
           f"{objection.visit_date.isoformat()} 방문 신고에 대한 센터의 답변이 왔습니다: {objection.resolution_note}")
    db.commit()
    return {"status": "success", "message": "신고를 처리했습니다. 이제 해당 날짜 청구를 승인할 수 있습니다"}
