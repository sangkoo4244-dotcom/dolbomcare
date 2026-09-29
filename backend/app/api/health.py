from fastapi import APIRouter
from datetime import datetime

router = APIRouter()

@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "dolbomcare-api"
    }

@router.get("/health/db")
async def health_check_db():
    return {
        "status": "checking",
        "database": "postgresql",
        "message": "Database connection will be checked after setup"
    }
