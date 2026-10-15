import os
import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User

SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)
ALGORITHM = "HS256"

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["uid"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="로그인이 만료되었거나 올바르지 않습니다")

    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="로그인이 만료되었거나 올바르지 않습니다")
    return user


def require_manager(user: User = Depends(get_current_user)) -> User:
    if user.role != "center_manager":
        raise HTTPException(status_code=403, detail="센터장만 할 수 있는 작업입니다")
    return user


def require_manager_or_caregiver(user: User = Depends(get_current_user)) -> User:
    if user.role not in ("center_manager", "caregiver"):
        raise HTTPException(status_code=403, detail="센터장 또는 요양사만 할 수 있는 작업입니다")
    return user


def require_platform_admin(user: User = Depends(get_current_user)) -> User:
    """플랫폼 운영진(이음로직) 전용 - 센터장 권한과 별개로, 환경변수 PLATFORM_ADMIN_EMAILS에
    등록된 이메일로 로그인한 계정만 통과한다. 별도의 admin 역할을 만들지 않고 이메일 허용목록으로
    간단히 처리한다 (관리 대상 센터가 아직 소수라 역할 체계를 늘릴 필요가 없다)."""
    admin_emails = {e.strip().lower() for e in os.getenv("PLATFORM_ADMIN_EMAILS", "").split(",") if e.strip()}
    if user.email.lower() not in admin_emails:
        raise HTTPException(status_code=403, detail="운영자만 할 수 있는 작업입니다")
    return user


def assert_self_or_manager(actor: User, caregiver_id: int, db=None) -> None:
    """본인이거나, 같은 센터의 센터장만 통과한다. db를 주면 센터장이 다른 센터 직원의 정보를 보는 것도 막는다."""
    if actor.id == caregiver_id:
        return
    if actor.role != "center_manager":
        raise HTTPException(status_code=403, detail="본인의 정보만 조회할 수 있습니다")
    if db is not None:
        target = db.query(User).filter(User.id == caregiver_id).first()
        if not target or target.center_id != actor.center_id:
            raise HTTPException(status_code=403, detail="우리 센터 직원의 정보만 조회할 수 있습니다")


def assert_my_center(actor: User, center_id) -> None:
    """내 센터의 자료가 아니면 '없음'으로 응답한다(다른 센터 번호를 넣어도 존재 여부를 알 수 없게)."""
    if center_id is None or actor.center_id is None or center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="찾을 수 없습니다")
