from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.benefits import catalog
from app.database import get_db
from app.models import Center, User

router = APIRouter()


@router.get("")
def my_center_benefits(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """내 센터가 제공하는 급여 종류를 프로그램(가정방문·주야간보호·시설·공생)별로 보여 준다.
    enabled는 센터가 고른 급여, implemented는 돌봄케어에 기능이 만들어졌는지다."""
    center = db.query(Center).filter(Center.id == actor.center_id).first() if actor.center_id else None
    return catalog(center.service_types if center else None)
