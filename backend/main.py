from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api import health
from app.api import users
from app.api import billing
from app.api import records
from app.api import residents
from app.api import salary
from app.api import schedule
from app.database import Base, engine
import os
from pathlib import Path

# Base.metadata.create_all(bind=engine)  # PostgreSQL 연결 실패 시 서버 시작 불가 → 비활성화

app = FastAPI(
    title="dolbomcare API",
    description="AI-powered care management platform",
    version="0.1.0"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 포함 (StaticFiles 전에 등록해야 우선순위 획득)
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
app.include_router(users.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(billing.router, prefix="/api/v1/billing", tags=["billing"])
app.include_router(records.router, prefix="/api/v1/records", tags=["records"])
app.include_router(residents.router, prefix="/api/v1/residents", tags=["residents"])
app.include_router(salary.router, prefix="/api/v1/salary", tags=["salary"])
app.include_router(schedule.router, prefix="/api/v1/schedule", tags=["schedule"])

# API 문서 라우트도 보호
app.openapi()
app.setup()

# 정적 파일 마운트 - 모든 HTML, CSS, JS를 /에서 제공
# (StaticFiles는 마지막에 마운트하여 API 라우터에 영향 없음)
scratchpad_path = str(Path(__file__).parent.parent / "scratchpad")
if Path(scratchpad_path).exists():
    app.mount("/", StaticFiles(directory=scratchpad_path, html=True), name="scratchpad")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
