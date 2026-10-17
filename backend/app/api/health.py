import os
from fastapi import APIRouter
from datetime import datetime

router = APIRouter()

@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "local_timestamp": datetime.now().isoformat(),  # 서버 시간대가 한국 시간으로 맞는지 확인용
        "service": "dolbomcare-api",
        "version": os.getenv("RENDER_GIT_COMMIT", "unknown")[:7],  # Render가 배포 커밋을 넣어 준다 (배포 확인용)
    }

@router.get("/health/db")
async def health_check_db():
    return {
        "status": "checking",
        "database": "postgresql",
        "message": "Database connection will be checked after setup"
    }
