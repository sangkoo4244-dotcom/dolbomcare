from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.users import get_password_hash
from app.auth import require_platform_admin
from app.database import get_db
from app.models import (
    AlimtalkUsage,
    BillingRecord,
    Center,
    CopayInvoice,
    DailyRecord,
    GuardianInvite,
    HealthMetric,
    MonthlySummary,
    NeedsAssessment,
    Notification,
    Resident,
    ResidentChangeRequest,
    ResidentMedia,
    ResidentMessage,
    ResidentThreadRead,
    RiskAssessment,
    Salary,
    SalaryStatement,
    Schedule,
    StaffCertificate,
    StaffRecord,
    User,
    VoiceRecord,
)

router = APIRouter()


@router.get("/is-admin")
def check_is_admin(actor: User = Depends(require_platform_admin)):
    """프런트에서 운영자 콘솔 링크를 보여줄지 판단하기 위한 가벼운 확인용 (DB 조회 없음)."""
    return {"is_admin": True}


class CenterCreateRequest(BaseModel):
    center_name: str
    manager_name: str
    manager_email: str
    manager_password: str


@router.post("/centers")
def create_center(
    body: CenterCreateRequest, db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)
):
    """새 센터와 센터장 계정을 만든다 (운영자 전용). 지금은 가입 페이지가 실제 계정을 만들지
    않기 때문에, 파일럿 센터를 쓰게 하려면 운영자가 이 화면에서 직접 만들어 전달해야 한다."""
    if not body.center_name.strip():
        raise HTTPException(status_code=400, detail="센터명을 입력해 주세요")
    if len(body.manager_password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 최소 8자 이상이어야 합니다")
    if db.query(User).filter(User.email == body.manager_email).first():
        raise HTTPException(status_code=400, detail="이미 사용 중인 이메일입니다")

    center = Center(name=body.center_name.strip())
    db.add(center)
    db.flush()
    manager = User(
        email=body.manager_email,
        hashed_password=get_password_hash(body.manager_password),
        full_name=body.manager_name,
        role="center_manager",
        center_id=center.id,
        is_active=True,
    )
    db.add(manager)
    db.commit()
    return {"status": "success", "center_id": center.id, "center_name": center.name, "manager_email": manager.email}


@router.get("/alimtalk-overview")
def list_alimtalk_overview(db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)):
    """센터별 이번 달 알림톡 사용량·충전 잔액 (운영자 전용)."""
    year_month = datetime.utcnow().strftime("%Y-%m")
    usages = {u.center_id: u for u in db.query(AlimtalkUsage).filter(AlimtalkUsage.year_month == year_month).all()}
    centers = db.query(Center).order_by(Center.name).all()
    return [
        {
            "center_id": c.id,
            "center_name": c.name,
            "balance": c.alimtalk_balance or 0,
            "free_sent": usages[c.id].free_sent if c.id in usages else 0,
            "paid_sent": usages[c.id].paid_sent if c.id in usages else 0,
            "blocked_count": usages[c.id].blocked_count if c.id in usages else 0,
            "resident_count": db.query(Resident).filter(Resident.center_id == c.id).count(),
            "staff_count": db.query(User).filter(User.center_id == c.id).count(),
        }
        for c in centers
    ]


def _cascade_delete_center(db: Session, center: Center) -> None:
    """센터에 딸린 모든 데이터를 지운다 (이용자·직원·청구·기록 등 전부). FK 제약(특히 운영 DB인
    PostgreSQL)을 어기지 않도록, 참조당하는 테이블부터 역순으로 지운다."""
    center_id = center.id
    resident_ids = [r.id for r in db.query(Resident.id).filter(Resident.center_id == center_id).all()]
    user_ids = [u.id for u in db.query(User.id).filter(User.center_id == center_id).all()]

    # billing_records.daily_record_id가 daily_records를 참조하므로 daily_records보다 먼저 지운다
    db.query(BillingRecord).filter(BillingRecord.center_id == center_id).delete(synchronize_session=False)

    if resident_ids:
        db.query(DailyRecord).filter(DailyRecord.resident_id.in_(resident_ids)).delete(synchronize_session=False)
        db.query(HealthMetric).filter(HealthMetric.resident_id.in_(resident_ids)).delete(synchronize_session=False)
        db.query(NeedsAssessment).filter(NeedsAssessment.resident_id.in_(resident_ids)).delete(synchronize_session=False)
        db.query(RiskAssessment).filter(RiskAssessment.resident_id.in_(resident_ids)).delete(synchronize_session=False)
        db.query(ResidentMedia).filter(ResidentMedia.resident_id.in_(resident_ids)).delete(synchronize_session=False)
        db.query(ResidentThreadRead).filter(ResidentThreadRead.resident_id.in_(resident_ids)).delete(synchronize_session=False)

    if user_ids:
        db.query(StaffCertificate).filter(StaffCertificate.user_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(StaffRecord).filter(StaffRecord.staff_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(ResidentThreadRead).filter(ResidentThreadRead.user_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(Notification).filter(Notification.user_id.in_(user_ids)).delete(synchronize_session=False)

    db.query(ResidentMessage).filter(ResidentMessage.center_id == center_id).delete(synchronize_session=False)
    db.query(ResidentChangeRequest).filter(ResidentChangeRequest.center_id == center_id).delete(synchronize_session=False)
    db.query(GuardianInvite).filter(GuardianInvite.center_id == center_id).delete(synchronize_session=False)
    db.query(Schedule).filter(Schedule.center_id == center_id).delete(synchronize_session=False)
    db.query(MonthlySummary).filter(MonthlySummary.center_id == center_id).delete(synchronize_session=False)
    db.query(Salary).filter(Salary.center_id == center_id).delete(synchronize_session=False)
    db.query(SalaryStatement).filter(SalaryStatement.center_id == center_id).delete(synchronize_session=False)
    db.query(CopayInvoice).filter(CopayInvoice.center_id == center_id).delete(synchronize_session=False)
    db.query(VoiceRecord).filter(VoiceRecord.center_id == center_id).delete(synchronize_session=False)
    db.query(AlimtalkUsage).filter(AlimtalkUsage.center_id == center_id).delete(synchronize_session=False)

    db.query(Resident).filter(Resident.center_id == center_id).delete(synchronize_session=False)
    db.query(User).filter(User.center_id == center_id).delete(synchronize_session=False)
    db.delete(center)


@router.delete("/centers/{center_id}")
def delete_center(center_id: int, db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)):
    """사용하지 않는 센터를 삭제한다 (운영자 전용). 이용자가 한 명이라도 있거나 센터장 외에
    직원이 등록돼 있으면 실수로 실제 운영 데이터를 지우는 것을 막기 위해 거부한다.
    데이터가 있는 센터를 지우려면 /centers/{center_id}/force를 쓴다."""
    center = db.query(Center).filter(Center.id == center_id).first()
    if not center:
        raise HTTPException(status_code=404, detail="센터를 찾을 수 없습니다")

    resident_count = db.query(Resident).filter(Resident.center_id == center_id).count()
    if resident_count > 0:
        raise HTTPException(status_code=400, detail=f"이용자가 {resident_count}명 등록돼 있어 삭제할 수 없습니다")

    staff_count = db.query(User).filter(User.center_id == center_id).count()
    if staff_count > 1:
        raise HTTPException(status_code=400, detail="센터장 외 직원이 등록돼 있어 삭제할 수 없습니다")

    _cascade_delete_center(db, center)
    db.commit()
    return {"status": "success"}


class ForceDeleteRequest(BaseModel):
    confirm_name: str


@router.delete("/centers/{center_id}/force")
def force_delete_center(
    center_id: int,
    body: ForceDeleteRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_platform_admin),
):
    """이용자·직원이 있는 센터도 강제로 삭제한다 (운영자 전용, 복구 불가능).
    실수 방지를 위해 센터명을 정확히 입력해야만 실행된다."""
    center = db.query(Center).filter(Center.id == center_id).first()
    if not center:
        raise HTTPException(status_code=404, detail="센터를 찾을 수 없습니다")
    if body.confirm_name.strip() != center.name:
        raise HTTPException(status_code=400, detail="센터명이 일치하지 않습니다")

    _cascade_delete_center(db, center)
    db.commit()
    return {"status": "success"}


class ChargeRequest(BaseModel):
    center_id: int
    amount: int


@router.post("/alimtalk-charge")
def charge_alimtalk_balance(
    body: ChargeRequest, db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)
):
    """센터 충전 잔액을 수동으로 올린다 (운영자 전용). 입금 확인 후 운영자가 직접 호출한다."""
    if body.amount == 0:
        raise HTTPException(status_code=400, detail="금액을 입력해 주세요")
    center = db.query(Center).filter(Center.id == body.center_id).first()
    if not center:
        raise HTTPException(status_code=404, detail="센터를 찾을 수 없습니다")
    center.alimtalk_balance = (center.alimtalk_balance or 0) + body.amount
    db.commit()
    return {"status": "success", "center_id": center.id, "balance": center.alimtalk_balance}
