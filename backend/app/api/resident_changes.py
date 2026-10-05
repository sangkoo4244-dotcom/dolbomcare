from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_manager
from app.database import get_db
from app.models import Resident, ResidentChangeRequest, User

router = APIRouter()

CLIENT_TYPES = ["일반", "차상위계층", "기초생활보장", "의료급여"]


class ChangeRequestCreate(BaseModel):
    field: str
    value: str


class RejectBody(BaseModel):
    reason: str = ""


def _validate(resident: Resident, field: str, value: str):
    """요청한 값을 저장 전에 검사하고, 저장할 형태로 바꿔 돌려준다."""
    value = value.strip()
    if field == "name":
        if not value:
            raise HTTPException(status_code=400, detail="이름을 입력해 주세요")
        return value
    if field == "birth_date":
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise HTTPException(status_code=400, detail="생년월일은 YYYY-MM-DD 형식으로 입력해 주세요")
    if field == "care_grade":
        if not value.isdigit() or int(value) not in range(1, 6):
            raise HTTPException(status_code=400, detail="등급은 1~5 사이여야 합니다")
        return int(value)
    if field == "client_type":
        if value not in CLIENT_TYPES:
            raise HTTPException(status_code=400, detail="소득분류 값이 올바르지 않습니다")
        return value
    if field == "recognition_number":
        return value or None
    if field in ("recognition_start", "recognition_end"):
        try:
            new_date = date.fromisoformat(value)
        except ValueError:
            raise HTTPException(status_code=400, detail="인정 기간은 YYYY-MM-DD 형식으로 입력해 주세요")
        start = new_date if field == "recognition_start" else resident.recognition_start
        end = new_date if field == "recognition_end" else resident.recognition_end
        if start and end and end < start:
            raise HTTPException(status_code=400, detail="인정 종료일이 시작일보다 빠를 수 없습니다")
        return new_date
    raise HTTPException(status_code=400, detail="변경 요청할 수 없는 항목입니다")


REQUESTABLE_FIELDS = {"name", "birth_date", "care_grade", "client_type", "recognition_number", "recognition_start", "recognition_end"}


@router.post("/{resident_id}/change-requests")
def create_change_request(
    resident_id: int,
    body: ChangeRequestCreate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """요양사가 청구에 영향을 주는 정보의 변경을 센터장에게 요청한다"""
    if actor.role != "caregiver":
        raise HTTPException(status_code=400, detail="센터장은 이용자 정보를 직접 수정합니다")
    if body.field not in REQUESTABLE_FIELDS:
        raise HTTPException(status_code=400, detail="변경 요청할 수 없는 항목입니다")
    resident = db.query(Resident).filter(Resident.id == resident_id).first()
    if not resident or resident.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    _validate(resident, body.field, body.value)  # 저장 전에 값부터 확인

    request = ResidentChangeRequest(
        resident_id=resident_id,
        center_id=actor.center_id,
        requested_by=actor.id,
        field=body.field,
        new_value=body.value.strip(),
        status="pending",
    )
    db.add(request)
    db.commit()
    return {"status": "success", "message": "센터장에게 변경을 요청했습니다", "data": {"id": request.id}}


@router.get("/change-requests/mine")
def my_change_requests(
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """요양사가 올린 변경 요청과 처리 결과 (최근 순)"""
    rows = (
        db.query(ResidentChangeRequest, Resident)
        .join(Resident, Resident.id == ResidentChangeRequest.resident_id)
        .filter(ResidentChangeRequest.requested_by == actor.id)
        .order_by(ResidentChangeRequest.created_at.desc())
        .limit(20)
        .all()
    )
    return {
        "requests": [
            {
                "id": r.id,
                "resident_name": res.name,
                "field": r.field,
                "new_value": r.new_value,
                "status": r.status,
                "reason": r.reason,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "decided_at": r.decided_at.isoformat() if r.decided_at else None,
            }
            for r, res in rows
        ]
    }


@router.get("/change-requests")
def list_change_requests(
    status: str = "pending",
    db: Session = Depends(get_db),
    manager: User = Depends(require_manager),
):
    rows = (
        db.query(ResidentChangeRequest, Resident, User)
        .join(Resident, Resident.id == ResidentChangeRequest.resident_id)
        .join(User, User.id == ResidentChangeRequest.requested_by)
        .filter(ResidentChangeRequest.center_id == manager.center_id, ResidentChangeRequest.status == status)
        .order_by(ResidentChangeRequest.created_at)
        .all()
    )
    return {
        "requests": [
            {
                "id": r.id,
                "resident_id": res.id,
                "resident_name": res.name,
                "field": r.field,
                "new_value": r.new_value,
                "requested_by": req_user.full_name,
                "status": r.status,
                "reason": r.reason,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r, res, req_user in rows
        ]
    }


@router.post("/change-requests/{request_id}/approve")
def approve_change_request(
    request_id: int,
    db: Session = Depends(get_db),
    manager: User = Depends(require_manager),
):
    req = db.query(ResidentChangeRequest).filter(ResidentChangeRequest.id == request_id).first()
    if not req or req.center_id != manager.center_id:
        raise HTTPException(status_code=404, detail="변경 요청을 찾을 수 없습니다")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="대기 중인 요청만 승인할 수 있습니다")

    resident = db.query(Resident).filter(Resident.id == req.resident_id).first()
    value = _validate(resident, req.field, req.new_value or "")
    setattr(resident, req.field, value)
    if req.field == "birth_date":
        today = datetime.now().date()
        resident.age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))

    req.status = "approved"
    req.decided_by = manager.id
    req.decided_at = datetime.utcnow()
    db.commit()
    return {"status": "success", "message": "변경을 승인해 반영했습니다"}


@router.post("/change-requests/{request_id}/reject")
def reject_change_request(
    request_id: int,
    body: RejectBody,
    db: Session = Depends(get_db),
    manager: User = Depends(require_manager),
):
    req = db.query(ResidentChangeRequest).filter(ResidentChangeRequest.id == request_id).first()
    if not req or req.center_id != manager.center_id:
        raise HTTPException(status_code=404, detail="변경 요청을 찾을 수 없습니다")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="대기 중인 요청만 반려할 수 있습니다")
    if not body.reason.strip():
        raise HTTPException(status_code=400, detail="반려 사유를 입력해 주세요")

    req.status = "rejected"
    req.reason = body.reason.strip()
    req.decided_by = manager.id
    req.decided_at = datetime.utcnow()
    db.commit()
    return {"status": "success", "message": "변경 요청을 반려했습니다"}
