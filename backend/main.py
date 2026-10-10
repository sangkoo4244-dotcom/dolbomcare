from fastapi import FastAPI, Depends
from app.auth import get_current_user
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from app.api import health
from app.api import resident_changes
from app.api import users
from app.api import billing
from app.api import records
from app.api import residents
from app.api import salary
from app.api import schedule
from app.api import notifications
from app.api import guardian
from app.api import messages
from app.api import statements
from app.api import certificates
from app.api import needs_assessments
from app.database import Base, engine, SessionLocal
from app.migrations import run_migrations
import os
from pathlib import Path
from sqlalchemy import text

# Base.metadata.create_all(bind=engine)

# 서버 시작 전 마이그레이션 실행
try:
    run_migrations()
except Exception as e:
    print(f"❌ 마이그레이션 실패: {e}")

app = FastAPI(
    title="dolbomcare API",
    description="AI-powered care management platform",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(users.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(billing.router, prefix="/api/v1/billing", tags=["billing"], dependencies=[Depends(get_current_user)])
app.include_router(records.router, prefix="/api/v1/records", tags=["records"], dependencies=[Depends(get_current_user)])
app.include_router(resident_changes.router, prefix="/api/v1/residents", tags=["residents"], dependencies=[Depends(get_current_user)])
app.include_router(residents.router, prefix="/api/v1/residents", tags=["residents"], dependencies=[Depends(get_current_user)])
app.include_router(salary.router, prefix="/api/v1/salary", tags=["salary"], dependencies=[Depends(get_current_user)])
app.include_router(schedule.router, prefix="/api/v1/schedule", tags=["schedule"], dependencies=[Depends(get_current_user)])
app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["notifications"], dependencies=[Depends(get_current_user)])
app.include_router(guardian.router, prefix="/api/v1/guardian", tags=["guardian"])
app.include_router(messages.router, prefix="/api/v1/messages", tags=["messages"], dependencies=[Depends(get_current_user)])
app.include_router(statements.router, prefix="/api/v1/statements", tags=["statements"], dependencies=[Depends(get_current_user)])
app.include_router(certificates.router, prefix="/api/v1/certificates", tags=["certificates"])
app.include_router(needs_assessments.router, prefix="/api/v1/needs-assessments", tags=["needs_assessments"], dependencies=[Depends(get_current_user)])

@app.middleware("http")
async def revalidate_pages(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/pages/") or request.url.path.endswith(".html") or request.url.path.endswith(".js"):
        response.headers["Cache-Control"] = "no-cache"
    return response

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
