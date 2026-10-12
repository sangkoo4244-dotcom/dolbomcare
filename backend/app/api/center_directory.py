from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.centers import _to_directory_dict
from app.database import get_db
from app.models import Center

router = APIRouter()


@router.get("/directory")
def list_public_centers(q: Optional[str] = None, db: Session = Depends(get_db)):
    """센터를 못 정한 예비 보호자용 공개 디렉토리 (로그인 불필요, find_center.html이 쓴다).
    centers.router는 전체에 로그인 필수 의존성이 걸려 있어 이 엔드포인트만 별도 라우터로 분리했다."""
    query = db.query(Center).filter(Center.is_public_listed == True)  # noqa: E712
    if q:
        like = f"%{q.strip()}%"
        query = query.filter((Center.name.like(like)) | (Center.address.like(like)))
    centers = query.order_by(Center.name).all()
    return {"centers": [_to_directory_dict(c) for c in centers]}
