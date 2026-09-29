from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime, timedelta

router = APIRouter()

class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user_id: str

@router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    if not request.email or not request.password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    return {
        "access_token": "mock-token-will-be-replaced",
        "token_type": "bearer",
        "user_id": "user-123"
    }

@router.post("/auth/logout")
async def logout():
    return {"message": "Successfully logged out"}
