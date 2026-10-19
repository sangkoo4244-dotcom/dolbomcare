from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.schemas import LoginRequest, LoginResponse, UserCreate, UserResponse
from app.models import User, Center, PasswordResetToken
from app.database import get_db
from app.plans import plan_info_with_usage
from app.trial_notice import maybe_notify_trial
from app.auth import SECRET_KEY, get_current_user, require_manager
from app.email_service import send_email
from passlib.context import CryptContext
from datetime import datetime, timedelta, date
from jose import jwt
from typing import Optional
from pydantic import BaseModel
import re
import secrets

from app.visit_benefit import JOB_TYPES

router = APIRouter()

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    hire_date: Optional[date] = None
    position: Optional[str] = None
    emergency_contact: Optional[str] = None
    employment_status: Optional[str] = None
    wage_ratio: Optional[int] = None  # 급여 비율(%) - 요양사가 받는 급여 = 청구액 × 이 비율
    job_type: Optional[str] = None  # 직종: 요양보호사/간호사/간호조무사/치과위생사. 빈 문자열이면 요양보호사
    birth_date: Optional[date] = None  # 직원 생년월일 (보수교육 대상 연도 계산)
    leave_date: Optional[date] = None  # 퇴사일 (경력직 비율)
    career_excluded: Optional[bool] = None  # 경력직 비율 제외 여부로 되돌린다

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 12

def verify_password(plain_password, hashed_password):
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        return False

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@router.post("/register", response_model=UserResponse)
async def register(user_create: UserCreate, db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    """센터장이 같은 센터에 직원 계정을 만든다"""
    if user_create.role not in ("caregiver", "center_manager", "social_worker"):
        raise HTTPException(status_code=400, detail="역할은 요양사, 센터장 또는 사회복지사만 가능합니다")
    if len(user_create.password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 8자 이상이어야 합니다")
    # 대소문자만 다른 이메일(Kim@x.com / kim@x.com)도 같은 계정으로 보고 중복 처리한다
    db_user = db.query(User).filter(func.lower(User.email) == user_create.email.lower()).first()
    if db_user:
        raise HTTPException(status_code=400, detail="이미 등록된 이메일입니다")

    hashed_password = get_password_hash(user_create.password)
    db_user = User(
        email=user_create.email,
        hashed_password=hashed_password,
        full_name=user_create.full_name,
        role=user_create.role,
        center_id=manager.center_id,
        is_active=True,
        care_bonus_registered=bool(user_create.care_bonus_registered) if user_create.role == "social_worker" else False,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

class StaffImportRows(BaseModel):
    rows: list[dict]
    dry_run: bool = True


def _check_staff_row(raw: dict):
    get = lambda k: str(raw.get(k, "") or "").strip()
    name, email = get("이름"), get("이메일").lower()
    if not name:
        return None, "이름이 없습니다"
    if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        return None, "이메일 형식을 확인해 주세요. (예: name@naver.com)"
    job = get("직종") or "요양보호사"
    if job not in JOB_TYPES:
        return None, "직종은 " + ", ".join(JOB_TYPES) + " 중 하나로 적어 주세요"
    hire = get("입사일").replace(".", "-").replace("/", "-")
    hire_date = None
    if hire:
        try:
            hire_date = date.fromisoformat(hire)
        except ValueError:
            return None, "입사일은 2026-01-31 형식으로 적어 주세요"
    return {"full_name": name, "email": email, "phone": get("연락처") or None, "job_type": None if job == "요양보호사" else job, "hire_date": hire_date}, None


@router.post("/import")
def import_staff(body: StaffImportRows, db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    """요양사 계정을 한꺼번에 만든다 (센터장). 문제가 하나도 없을 때만 저장하고, 저장하면 줄마다 임시 비밀번호를
    한 번만 돌려준다(화면에서 안내문으로 내려받아 나눠 주고, 직원은 로그인 뒤 바꾼다)."""
    if not body.rows:
        raise HTTPException(status_code=400, detail="올릴 직원이 없습니다")
    if len(body.rows) > 200:
        raise HTTPException(status_code=400, detail="한 번에 200명까지 올릴 수 있습니다")
    taken = {e.lower() for (e,) in db.query(User.email).all()}
    seen, ok, errors = set(), [], []
    for i, raw in enumerate(body.rows, start=2):
        data, error = _check_staff_row(raw)
        if not error:
            if data["email"] in taken:
                error = "이미 등록된 이메일입니다"
            elif data["email"] in seen:
                error = "파일 안에 같은 이메일이 두 번 있습니다"
            seen.add(data["email"])
        if error:
            errors.append({"row": i, "name": str(raw.get("이름", "") or ""), "message": error})
        else:
            ok.append(data)
    if errors or body.dry_run:
        return {"status": "checked" if not errors else "has_errors", "ok_count": len(ok), "errors": errors, "saved": False, "accounts": []}
    accounts = []
    for data in ok:
        temp_password = secrets.token_urlsafe(8)
        db.add(User(email=data["email"], hashed_password=get_password_hash(temp_password), full_name=data["full_name"], role="caregiver",
                    center_id=manager.center_id, is_active=True, phone=data["phone"], job_type=data["job_type"], hire_date=data["hire_date"]))
        accounts.append({"name": data["full_name"], "email": data["email"], "temp_password": temp_password})
    db.commit()
    return {"status": "saved", "ok_count": len(ok), "errors": [], "saved": True, "accounts": accounts}


@router.post("/login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    from app.demo_seed import DEMO_LOGIN_EMAILS, refresh_demo_if_stale
    if request.email in DEMO_LOGIN_EMAILS:
        try:
            refresh_demo_if_stale(db)  # 체험 계정 로그인이 데모 초기화에 실패해도 로그인은 막지 않는다
        except Exception as e:
            db.rollback()
            print(f"⚠️ 데모 초기화 실패 (로그인은 계속 진행): {e}")
    user = db.query(User).filter(User.email == request.email).first()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    plan_info = None
    if user.center_id:
        try:
            center = db.query(Center).filter(Center.id == user.center_id).first()
            plan_info = plan_info_with_usage(db, center) if center else None
            if center and user.role == "center_manager":
                maybe_notify_trial(db, center)
        except Exception as e:
            # 이용 상태 조회가 실패해도 로그인 자체를 막아서는 안 된다 (체험이 끝나도 로그인은 되고 읽기 전용이 된다).
            # PostgreSQL은 에러난 트랜잭션을 롤백하지 않으면 같은 커넥션의 다음 쿼리까지 막히므로 롤백한다.
            db.rollback()
            print(f"⚠️ 이용 상태 확인 실패 (로그인은 계속 진행): {e}")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email, "uid": user.id, "role": user.role}, expires_delta=access_token_expires
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "center_id": user.center_id,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None
        },
        "center_plan": plan_info,
    }


class ForgotPasswordRequest(BaseModel):
    email: str


RESET_TOKEN_EXPIRE_MINUTES = 60


@router.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """비밀번호 재설정 이메일을 보낸다. 계정이 있든 없든 같은 응답을 줘서 이메일 존재 여부가
    새어나가지 않게 한다 - 실제 발송 여부는 SMTP 설정(app/email_service.py)에 달려있다."""
    user = db.query(User).filter(User.email == request.email.strip()).first()
    if user:
        db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user.id).delete(synchronize_session=False)
        token = secrets.token_urlsafe(32)
        db.add(PasswordResetToken(
            user_id=user.id, token=token,
            expires_at=datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES),
        ))
        db.commit()
        send_email(
            to=user.email,
            subject="[돌봄케어] 비밀번호 재설정 안내",
            body=(
                f"{user.full_name}님, 안녕하세요.\n\n"
                f"비밀번호 재설정을 요청하셨습니다. 아래 링크에서 새 비밀번호를 설정해 주세요.\n"
                f"(이 링크는 {RESET_TOKEN_EXPIRE_MINUTES}분 동안만 유효합니다)\n\n"
                f"https://ieumlogic.co.kr/pages/reset_password.html?token={token}\n\n"
                f"본인이 요청하지 않았다면 이 메일을 무시하셔도 됩니다.\n\n"
                f"이음로직 드림"
            ),
        )
    return {"status": "success", "message": "입력하신 이메일로 가입된 계정이 있다면 재설정 링크를 보내드렸습니다."}


class ResetPasswordWithTokenRequest(BaseModel):
    token: str
    new_password: str


@router.post("/reset-password")
def reset_password_with_token(request: ResetPasswordWithTokenRequest, db: Session = Depends(get_db)):
    """이메일로 받은 토큰으로 비밀번호를 재설정한다 (로그인 불필요)."""
    if len(request.new_password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 최소 8자 이상이어야 합니다")

    reset_token = db.query(PasswordResetToken).filter(PasswordResetToken.token == request.token).first()
    if not reset_token or reset_token.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="링크가 만료되었거나 올바르지 않습니다. 다시 요청해 주세요.")

    user = db.query(User).filter(User.id == reset_token.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="계정을 찾을 수 없습니다")

    user.hashed_password = get_password_hash(request.new_password)
    db.delete(reset_token)
    db.commit()
    return {"status": "success"}


@router.get("/")
async def list_users(
    role: Optional[str] = Query(None),
    center_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """사용자 목록 조회 (선택적으로 역할로 필터링). 항상 로그인한 사람의 센터 직원만 보인다 (이메일·연락처가 있어 다른 센터에는 보이면 안 된다)."""
    if actor.role not in ("caregiver", "center_manager", "social_worker") or not actor.center_id:
        raise HTTPException(status_code=403, detail="직원 목록을 볼 수 있는 권한이 없습니다")
    query = db.query(User).filter(User.center_id == actor.center_id)

    if role:
        query = query.filter(User.role == role)

    users = query.all()

    return {
        "total_users": len(users),
        "users": [
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "phone": u.phone,
                "hire_date": u.hire_date.isoformat() if u.hire_date else None,
                "birth_date": u.birth_date.isoformat() if u.birth_date else None,
                "leave_date": u.leave_date.isoformat() if u.leave_date else None,
                "career_excluded": bool(u.career_excluded),
                "position": u.position,
                "emergency_contact": u.emergency_contact,
                "employment_status": u.employment_status,
                "wage_ratio": u.wage_ratio,
                "job_type": u.job_type or "요양보호사",
                "role": u.role,
                "center_id": u.center_id,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None
            }
            for u in users
        ]
    }

@router.put("/{user_id}")
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(require_manager)
):
    """사용자 정보 수정 (내 센터 직원만)"""
    user = db.query(User).filter(User.id == user_id, User.center_id == actor.center_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user_update.birth_date:
        user.birth_date = user_update.birth_date
    if user_update.leave_date:
        user.leave_date = user_update.leave_date
    if user_update.career_excluded is not None:
        user.career_excluded = user_update.career_excluded
    if user_update.full_name:
        user.full_name = user_update.full_name
    if user_update.email:
        user.email = user_update.email
    if user_update.phone:
        user.phone = user_update.phone
    if user_update.hire_date:
        user.hire_date = user_update.hire_date
    if user_update.position:
        user.position = user_update.position
    if user_update.emergency_contact:
        user.emergency_contact = user_update.emergency_contact
    if user_update.employment_status:
        user.employment_status = user_update.employment_status
    if user_update.wage_ratio is not None:
        if not (0 <= user_update.wage_ratio <= 100):
            raise HTTPException(status_code=400, detail="급여 비율은 0~100 사이여야 합니다")
        user.wage_ratio = user_update.wage_ratio
    if user_update.job_type is not None:
        if user_update.job_type and user_update.job_type not in JOB_TYPES:
            raise HTTPException(status_code=400, detail=f"직종은 {', '.join(JOB_TYPES)} 중에서 골라 주세요")
        user.job_type = user_update.job_type or None

    db.commit()
    db.refresh(user)

    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "hire_date": user.hire_date.isoformat() if user.hire_date else None,
        "birth_date": user.birth_date.isoformat() if user.birth_date else None,
        "position": user.position,
        "emergency_contact": user.emergency_contact,
        "employment_status": user.employment_status,
        "wage_ratio": user.wage_ratio,
        "job_type": user.job_type or "요양보호사",
        "role": user.role,
        "center_id": user.center_id,
        "is_active": user.is_active
    }

class PasswordReset(BaseModel):
    new_password: str

@router.post("/{user_id}/password")
async def reset_password(
    user_id: int,
    body: PasswordReset,
    db: Session = Depends(get_db),
    manager: User = Depends(require_manager)
):
    """센터장이 같은 센터 직원의 비밀번호를 재설정"""
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 8자 이상이어야 합니다")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="직원을 찾을 수 없습니다")
    if user.center_id != manager.center_id:
        raise HTTPException(status_code=403, detail="같은 센터 직원만 재설정할 수 있습니다")
    user.hashed_password = get_password_hash(body.new_password)
    db.commit()
    return {"status": "success", "message": "비밀번호가 재설정되었습니다"}

class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    profile_image: Optional[str] = None  # base64 data URL. 빈 문자열이면 사진 제거로 본다


@router.get("/me")
async def get_my_profile(actor: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """본인 프로필 조회 (역할 공통 - 요양사·센터장·보호자 모두)."""
    plan_info = None
    if actor.center_id:
        try:
            center = db.query(Center).filter(Center.id == actor.center_id).first()
            plan_info = plan_info_with_usage(db, center) if center else None
            if center and actor.role == "center_manager":
                maybe_notify_trial(db, center)
        except Exception:
            db.rollback()
    return {
        "center_plan": plan_info,
        "id": actor.id,
        "email": actor.email,
        "full_name": actor.full_name,
        "phone": actor.phone,
        "role": actor.role,
        "profile_image": actor.profile_image,
        "wage_ratio": actor.wage_ratio,
        "job_type": actor.job_type or "요양보호사",
    }


@router.patch("/me")
async def update_my_profile(
    body: ProfileUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
):
    """본인 프로필 수정 (이름·연락처·사진). 이메일·역할은 본인이 바꿀 수 없다."""
    if body.full_name is not None:
        if not body.full_name.strip():
            raise HTTPException(status_code=400, detail="이름은 비울 수 없습니다")
        actor.full_name = body.full_name.strip()
    if body.phone is not None:
        actor.phone = body.phone.strip() or None
    if body.profile_image is not None:
        actor.profile_image = body.profile_image or None

    db.commit()
    db.refresh(actor)
    return {
        "status": "success",
        "data": {
            "id": actor.id, "full_name": actor.full_name, "phone": actor.phone,
            "role": actor.role, "profile_image": actor.profile_image,
        },
    }


# 보호자가 받는 알림 종류 (notify()의 kind와 맞춘다). 새 종류가 생기면 여기만 추가하면 된다.
GUARDIAN_NOTIFY_CATEGORIES = {"visit_completed": "방문완료 알림", "message_received": "메시지 알림"}

class NotificationSettingsUpdate(BaseModel):
    alimtalk_opt_in: bool
    alimtalk_categories: Optional[list[str]] = None  # None이면 "전체" 유지 (생략 가능)

@router.get("/me/notification-settings")
async def get_my_notification_settings(actor: User = Depends(get_current_user)):
    """본인의 알림톡 수신 설정 조회. alimtalk_categories가 비어있으면(null) 전체 종류를 받는 것이다."""
    categories = actor.alimtalk_categories.split(",") if actor.alimtalk_categories else None
    return {
        "alimtalk_opt_in": bool(actor.alimtalk_opt_in),
        "has_phone": bool(actor.phone),
        "alimtalk_categories": categories,
        "available_categories": GUARDIAN_NOTIFY_CATEGORIES,
    }

@router.patch("/me/notification-settings")
async def update_my_notification_settings(
    body: NotificationSettingsUpdate,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user)
):
    """본인의 알림톡 수신 여부와 종류별 수신 여부를 설정한다 (인앱 알림은 이 설정과 무관하게 항상 온다)"""
    actor.alimtalk_opt_in = body.alimtalk_opt_in
    if body.alimtalk_categories is not None:
        valid = [c for c in body.alimtalk_categories if c in GUARDIAN_NOTIFY_CATEGORIES]
        # 전체 종류를 다 선택했으면 "전체"를 뜻하는 null로 저장한다 (새 종류가 추가돼도 자동으로 받도록)
        actor.alimtalk_categories = None if len(valid) == len(GUARDIAN_NOTIFY_CATEGORIES) else ",".join(valid)
    db.commit()
    return {"status": "success", "alimtalk_opt_in": actor.alimtalk_opt_in, "alimtalk_categories": actor.alimtalk_categories}

@router.delete("/{user_id}")
async def delete_user(user_id: int, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    """사용자 삭제 (내 센터 직원만, 본인 계정은 불가)"""
    user = db.query(User).filter(User.id == user_id, User.center_id == actor.center_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == actor.id:
        raise HTTPException(status_code=400, detail="본인 계정은 삭제할 수 없습니다")

    db.delete(user)
    db.commit()

    return {"message": "User deleted successfully"}
