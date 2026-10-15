# 서비스의 모든 시각은 한국 시간 기준이다. 클라우드 서버는 기본이 세계 표준시(UTC)라 datetime.now()가 9시간 늦게
# 저장·비교되므로, 다른 모듈이 시각을 쓰기 전에 가장 먼저 프로세스 시간대를 서울로 맞춘다 (윈도우 개발 PC에는 tzset이 없어 건너뜀)
import os
import time

if hasattr(time, "tzset"):  # 리눅스(운영 서버)만. 윈도우는 TZ 값을 다르게 해석해 오히려 세계 표준시가 되므로 건드리지 않는다
    os.environ["TZ"] = "Asia/Seoul"
    time.tzset()

from fastapi import FastAPI, Depends
from app.auth import get_current_user
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from app.api import juso
from app.api import rfid_compare
from app.api import claim_helper
from app.api import benefits as benefits_api
from app.api import day_care
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
from app.api import copay
from app.api import risk_assessments
from app.api import audit_prep, visit_precheck, counseling, care_plans, service_reviews, trainings, incidents, handovers, care_sheet, inbox
from app.api import staff_records
from app.api import resident_media
from app.api import centers
from app.api import center_directory
from app.api import nhis
from app.api import admin
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
app.include_router(copay.router, prefix="/api/v1/copay", tags=["copay"], dependencies=[Depends(get_current_user)])
app.include_router(risk_assessments.router, prefix="/api/v1/risk-assessments", tags=["risk_assessments"], dependencies=[Depends(get_current_user)])
app.include_router(audit_prep.router, prefix="/api/v1/audit-prep", tags=["audit_prep"], dependencies=[Depends(get_current_user)])
app.include_router(trainings.router, prefix="/api/v1/trainings", tags=["trainings"], dependencies=[Depends(get_current_user)])
app.include_router(service_reviews.router, prefix="/api/v1/service-reviews", tags=["service_reviews"], dependencies=[Depends(get_current_user)])
app.include_router(care_plans.router, prefix="/api/v1/care-plans", tags=["care_plans"], dependencies=[Depends(get_current_user)])
app.include_router(handovers.router, prefix="/api/v1/handovers", tags=["handovers"], dependencies=[Depends(get_current_user)])
app.include_router(care_sheet.router, prefix="/api/v1/care-sheet", tags=["care-sheet"], dependencies=[Depends(get_current_user)])
app.include_router(inbox.router, prefix="/api/v1/inbox", tags=["inbox"], dependencies=[Depends(get_current_user)])
app.include_router(incidents.router, prefix="/api/v1/incidents", tags=["incidents"], dependencies=[Depends(get_current_user)])
app.include_router(counseling.router, prefix="/api/v1/counseling", tags=["counseling"], dependencies=[Depends(get_current_user)])
app.include_router(visit_precheck.router, prefix="/api/v1/visit-precheck", tags=["visit_precheck"], dependencies=[Depends(get_current_user)])
app.include_router(staff_records.router, prefix="/api/v1/staff-records", tags=["staff_records"], dependencies=[Depends(get_current_user)])
app.include_router(resident_media.router, prefix="/api/v1/resident-media", tags=["resident_media"], dependencies=[Depends(get_current_user)])
app.include_router(centers.router, prefix="/api/v1/centers", tags=["centers"], dependencies=[Depends(get_current_user)])
app.include_router(center_directory.router, prefix="/api/v1/centers", tags=["centers"])
app.include_router(nhis.router, prefix="/api/v1/nhis", tags=["nhis"], dependencies=[Depends(get_current_user)])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(get_current_user)])
app.include_router(rfid_compare.router, prefix="/api/v1/rfid-compare", tags=["rfid_compare"], dependencies=[Depends(get_current_user)])
app.include_router(claim_helper.router, prefix="/api/v1/claim-helper", tags=["claim_helper"], dependencies=[Depends(get_current_user)])
app.include_router(benefits_api.router, prefix="/api/v1/benefits", tags=["benefits"], dependencies=[Depends(get_current_user)])
app.include_router(day_care.router, prefix="/api/v1/day-care", tags=["day_care"], dependencies=[Depends(get_current_user)])
app.include_router(juso.router)

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
