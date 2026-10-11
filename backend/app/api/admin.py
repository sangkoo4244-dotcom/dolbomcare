from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.users import get_password_hash
from app.auth import require_platform_admin
from app.database import get_db
from app.models import AlimtalkUsage, Center, User

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
        }
        for c in centers
    ]


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
