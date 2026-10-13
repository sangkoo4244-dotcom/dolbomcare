from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_manager
from app.database import get_db
from app.models import User
from app.visit_precheck import run_precheck

router = APIRouter()


@router.get("")
def get_visit_precheck(days: int = 14, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    """공단 전송(전자태그) 사전점검 - 최근 N일 방문 일정·기록과 이용자 인정기간 점검 (센터장 전용)."""
    return run_precheck(db, actor.center_id, max(1, min(days, 60)))
