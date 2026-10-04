from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from app.api import health
from app.api import users
from app.api import billing
from app.api import records
from app.api import residents
from app.api import salary
from app.api import schedule
from app.database import Base, engine, SessionLocal
import os
from pathlib import Path
from sqlalchemy import text

# Base.metadata.create_all(bind=engine)

# 데이터베이스 마이그레이션 (자동)
ADDITIVE_COLUMNS = [
    ("voice_records", "resident_name", "VARCHAR"),
    ("voice_records", "care_grade", "INTEGER"),
    ("voice_records", "client_type", "VARCHAR"),
    ("billing_records", "resident_name", "VARCHAR"),
    ("billing_records", "care_grade", "INTEGER"),
    ("billing_records", "client_type", "VARCHAR"),
    ("residents", "gender", "VARCHAR"),
    ("residents", "address", "VARCHAR"),
    ("residents", "recognition_number", "VARCHAR"),
    ("residents", "recognition_start", "DATE"),
    ("residents", "recognition_end", "DATE"),
    ("residents", "guardian_name", "VARCHAR"),
    ("residents", "guardian_phone", "VARCHAR"),
    ("daily_records", "care_items", "VARCHAR"),
    ("daily_records", "condition", "VARCHAR"),
    ("daily_records", "duration_minutes", "INTEGER"),
    ("billing_records", "total_cost", "INTEGER"),
]

def run_migrations():
    """자동 마이그레이션: year_month 컬럼 추가 (SQLite & PostgreSQL 호환)"""
    try:
        db = SessionLocal()
        db_url = str(engine.url)

        # SQLite 또는 PostgreSQL 감지
        is_postgres = "postgresql" in db_url

        # year_month 컬럼이 없으면 추가
        if is_postgres:
            # PostgreSQL 문법
            db.execute(text("""
                ALTER TABLE billing_records
                ADD COLUMN IF NOT EXISTS year_month VARCHAR
            """))
            # PostgreSQL에서 year_month 채우기
            db.execute(text("""
                UPDATE billing_records
                SET year_month = TO_CHAR(recorded_date, 'YYYY-MM')
                WHERE year_month IS NULL AND recorded_date IS NOT NULL
            """))
        else:
            # SQLite 문법
            try:
                # SQLite에서 컬럼 존재 여부 확인
                result = db.execute(text("""
                    PRAGMA table_info(billing_records)
                """)).fetchall()

                column_names = [row[1] for row in result]

                if "year_month" not in column_names:
                    db.execute(text("""
                        ALTER TABLE billing_records
                        ADD COLUMN year_month VARCHAR
                    """))

                    # SQLite에서 year_month 채우기
                    db.execute(text("""
                        UPDATE billing_records
                        SET year_month = strftime('%Y-%m', recorded_date)
                        WHERE year_month IS NULL AND recorded_date IS NOT NULL
                    """))
            except Exception as e:
                print(f"⚠️  SQLite 마이그레이션 부분 오류: {e}")

        for table, column, col_type in ADDITIVE_COLUMNS:
            if is_postgres:
                db.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"))
            else:
                existing = [row[1] for row in db.execute(text(f"PRAGMA table_info({table})")).fetchall()]
                if column not in existing:
                    db.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))

        db.commit()
        print("✅ 마이그레이션 완료: year_month 컬럼 추가됨")
    except Exception as e:
        print(f"⚠️  마이그레이션 오류: {e}")
        db.rollback()
    finally:
        db.close()

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
app.include_router(billing.router, prefix="/api/v1/billing", tags=["billing"])
app.include_router(records.router, prefix="/api/v1/records", tags=["records"])
app.include_router(residents.router, prefix="/api/v1/residents", tags=["residents"])
app.include_router(salary.router, prefix="/api/v1/salary", tags=["salary"])
app.include_router(schedule.router, prefix="/api/v1/schedule", tags=["schedule"])

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
