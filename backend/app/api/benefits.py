from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app import benefits
from app.benefits import catalog
from app.billing_rules import VISIT_FEES
from app.database import get_db
from app.models import Center, User

router = APIRouter()


@router.get("")
def my_center_benefits(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """내 센터가 제공하는 급여 종류를 프로그램(가정방문·주야간보호·시설·공생)별로 보여 준다.
    enabled는 센터가 고른 급여, implemented는 돌봄케어에 기능이 만들어졌는지다."""
    center = db.query(Center).filter(Center.id == actor.center_id).first() if actor.center_id else None
    return catalog(center.service_types if center else None)


@router.get("/visit-surcharge")
def visit_surcharge_preview(benefit_type: str, minutes: int, start: str, actor: User = Depends(get_current_user)):
    """방문요양·방문간호의 야간(22~06시)·일요일 가산금액 미리보기. 기록 화면의 금액 안내가 서버 계산과 같은 값을 쓰게 한다."""
    try:
        start_at = datetime.fromisoformat(start)
    except ValueError:
        raise HTTPException(status_code=400, detail="방문 시작 시각 형식이 올바르지 않습니다")
    if benefit_type in ("home_care", ""):
        base = VISIT_FEES.get(minutes, 0)
    elif benefit_type == "home_nursing":
        try:
            base = benefits.home_nursing_fee(minutes)
        except ValueError:
            base = 0
    else:
        base = 0
    return {
        "amount": benefits.visit_surcharge(base, start_at, minutes, benefits.visit_fee_minutes(benefit_type, minutes)),
        "covered_minutes": benefits.surcharge_minutes(start_at, minutes) if base else 0,
        "holiday_table_missing": benefits.holiday_table_missing(start_at),
        "unconfirmed_holiday": benefits.possible_unconfirmed_holiday(start_at, minutes),
    }

