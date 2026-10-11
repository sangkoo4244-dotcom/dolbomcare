from app.database import engine, SessionLocal
from app.models import (
    StaffCertificate, SalaryStatement, GuardianInvite, Notification,
    ResidentMessage, ResidentThreadRead, NeedsAssessment, CopayInvoice,
    RiskAssessment, StaffRecord, ResidentMedia,
)
from sqlalchemy import text

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
    ("schedules", "duration_minutes", "INTEGER"),
    ("schedules", "planned_items", "VARCHAR"),
    ("schedules", "arrived_at", "TIMESTAMP"),
    ("schedules", "left_at", "TIMESTAMP"),
    ("schedules", "review_note", "VARCHAR"),
    ("daily_records", "schedule_id", "INTEGER"),
    ("billing_records", "review_note", "VARCHAR"),
    ("daily_records", "signature", "TEXT"),
    ("users", "alimtalk_opt_in", "BOOLEAN DEFAULT TRUE"),
    ("users", "alimtalk_categories", "VARCHAR"),
    ("risk_assessments", "tool_name", "VARCHAR"),
    ("risk_assessments", "item_scores", "TEXT"),
    ("residents", "primary_caregiver_id", "INTEGER"),
]


def run_migrations():
    """자동 마이그레이션: year_month 컬럼 추가 (SQLite & PostgreSQL 호환)

    PostgreSQL은 트랜잭션 중 문장 하나가 실패하면 그 트랜잭션 전체가 "중단(aborted)" 상태가 되어
    이후 모든 문장이 연쇄적으로 실패한다. 그래서 테이블 생성과 컬럼 추가는 각각 독립된 트랜잭션으로
    실행하고, 하나가 실패해도 롤백 후 다음 것을 계속 시도한다 (한 항목의 실패가 나머지를 막지 않는다).
    """
    for table_cls in (StaffCertificate, SalaryStatement, GuardianInvite, Notification,
                       ResidentMessage, ResidentThreadRead, NeedsAssessment, CopayInvoice,
                       RiskAssessment, StaffRecord, ResidentMedia):
        try:
            table_cls.__table__.create(bind=engine, checkfirst=True)
        except Exception as e:
            print(f"⚠️  테이블 생성 건너뜀 ({table_cls.__tablename__}): {e}")

    db = SessionLocal()
    try:
        db_url = str(engine.url)
        is_postgres = "postgresql" in db_url

        # year_month 컬럼이 없으면 추가 (독립 트랜잭션 - 실패해도 아래 단계들을 막지 않는다)
        try:
            if is_postgres:
                db.execute(text("ALTER TABLE billing_records ADD COLUMN IF NOT EXISTS year_month VARCHAR"))
                db.execute(text("""
                    UPDATE billing_records
                    SET year_month = TO_CHAR(recorded_date, 'YYYY-MM')
                    WHERE year_month IS NULL AND recorded_date IS NOT NULL
                """))
            else:
                column_names = [row[1] for row in db.execute(text("PRAGMA table_info(billing_records)")).fetchall()]
                if "year_month" not in column_names:
                    db.execute(text("ALTER TABLE billing_records ADD COLUMN year_month VARCHAR"))
                    db.execute(text("""
                        UPDATE billing_records
                        SET year_month = strftime('%Y-%m', recorded_date)
                        WHERE year_month IS NULL AND recorded_date IS NOT NULL
                    """))
            db.commit()
        except Exception as e:
            print(f"⚠️  year_month 마이그레이션 건너뜀: {e}")
            db.rollback()

        # 추가 컬럼들: 한 컬럼 실패가 나머지 컬럼 추가를 막지 않도록 각각 독립적으로 커밋한다
        for table, column, col_type in ADDITIVE_COLUMNS:
            try:
                if is_postgres:
                    db.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"))
                else:
                    existing = [row[1] for row in db.execute(text(f"PRAGMA table_info({table})")).fetchall()]
                    if column not in existing:
                        db.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                db.commit()
            except Exception as e:
                print(f"⚠️  컬럼 추가 건너뜀 ({table}.{column}): {e}")
                db.rollback()

        try:
            db.execute(text("""
                UPDATE billing_records SET
                    resident_name = (SELECT name FROM residents WHERE residents.id = billing_records.resident_id),
                    care_grade = (SELECT care_grade FROM residents WHERE residents.id = billing_records.resident_id),
                    client_type = (SELECT client_type FROM residents WHERE residents.id = billing_records.resident_id)
                WHERE resident_name IS NULL
            """))
            db.commit()
            print("✅ 마이그레이션 완료")
        except Exception as e:
            print(f"⚠️  billing_records 백필 건너뜀: {e}")
            db.rollback()
    finally:
        db.close()
