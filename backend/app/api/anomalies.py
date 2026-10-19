"""센터장용 이상 패턴 목록 (최근 14일)."""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.anomaly import find_anomalies
from app.auth import require_manager
from app.database import get_db
from app.models import User

router = APIRouter()


@router.get("")
def list_anomalies(db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    return {"findings": find_anomalies(db, manager.center_id, datetime.now())}
