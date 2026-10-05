from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from app.schemas import LoginRequest, LoginResponse, UserCreate, UserResponse
from app.models import User
from app.database import get_db
from app.auth import SECRET_KEY, get_current_user, require_manager
from passlib.context import CryptContext
from datetime import datetime, timedelta, date
from jose import jwt
from typing import Optional
from pydantic import BaseModel

router = APIRouter()

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    hire_date: Optional[date] = None
    position: Optional[str] = None
    emergency_contact: Optional[str] = None
    employment_status: Optional[str] = None

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
async def register(user_create: UserCreate, db: Session = Depends(get_db), _: User = Depends(require_manager)):
    db_user = db.query(User).filter(User.email == user_create.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = get_password_hash(user_create.password)
    db_user = User(
        email=user_create.email,
        hashed_password=hashed_password,
        full_name=user_create.full_name,
        role=user_create.role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@router.post("/login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

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
        }
    }

@router.get("/")
async def list_users(
    role: Optional[str] = Query(None),
    center_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user)
):
    """사용자 목록 조회 (선택적으로 역할, 센터로 필터링)"""
    query = db.query(User)

    if role:
        query = query.filter(User.role == role)

    if center_id:
        query = query.filter(User.center_id == center_id)

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
                "position": u.position,
                "emergency_contact": u.emergency_contact,
                "employment_status": u.employment_status,
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
    _: User = Depends(require_manager)
):
    """사용자 정보 수정"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

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

    db.commit()
    db.refresh(user)

    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "phone": user.phone,
        "hire_date": user.hire_date.isoformat() if user.hire_date else None,
        "position": user.position,
        "emergency_contact": user.emergency_contact,
        "employment_status": user.employment_status,
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

@router.delete("/{user_id}")
async def delete_user(user_id: int, db: Session = Depends(get_db), _: User = Depends(require_manager)):
    """사용자 삭제"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()

    return {"message": "User deleted successfully"}
