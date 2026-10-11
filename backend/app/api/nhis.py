from fastapi import APIRouter, Depends, HTTPException

from app.auth import require_manager
from app.models import User
from app.nhis_ltc import get_general_status, get_staff_status

router = APIRouter()


@router.get("/ltc-institution/{institution_code}")
def lookup_institution(institution_code: str, actor: User = Depends(require_manager)):
    """장기요양기관코드로 공단 일반현황·인력현황을 조회한다 (센터 정보 설정 화면용, 센터장 전용)."""
    general = get_general_status(institution_code)
    staff = get_staff_status(institution_code)
    if not general["ok"] and not staff["ok"]:
        raise HTTPException(status_code=400, detail=general["message"] or staff["message"])
    return {"general": general, "staff": staff}
