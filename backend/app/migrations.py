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
        primary_caregiver_just_added = False
        for table, column, col_type in ADDITIVE_COLUMNS:
            try:
                if is_postgres:
                    existed_before = db.execute(text(
                        "SELECT 1 FROM information_schema.columns WHERE table_name = :t AND column_name = :c"
                    ), {"t": table, "c": column}).first() is not None
                    db.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"))
                else:
                    existing = [row[1] for row in db.execute(text(f"PRAGMA table_info({table})")).fetchall()]
                    existed_before = column in existing
                    if not existed_before:
                        db.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                db.commit()
                if not existed_before and table == "residents" and column == "primary_caregiver_id":
                    primary_caregiver_just_added = True
            except Exception as e:
                print(f"⚠️  컬럼 추가 건너뜀 ({table}.{column}): {e}")
                db.rollback()

        # primary_caregiver_id는 이 기능을 처음 배포한 직후 전부 NULL이다. 이 상태로 두면 이미 이용자를
        # 방문하던 요양사가 갑자기 "담당 이용자 없음"이 되어 센터장 화면과 어긋나 보인다. 그래서
        # (a) 컬럼이 이번 재시작에 "방금" 생겼거나, (b) 컬럼은 이전 배포에서 이미 생겼지만(이 백필 로직이
        # 그때는 없었다) 시스템 전체에 지정된 값이 단 하나도 없는 "아직 한 번도 안 채워진" 상태라면,
        # Schedule/DailyRecord에 남은 가장 최근 담당자로 1회성 백필한다. 센터장이 이후 명시적으로
        # 배정/해제한 값이 하나라도 생기면(센터 전체에 걸쳐) 다음 재시작부터는 더 이상 건드리지 않는다.
        should_backfill_primary_caregiver = primary_caregiver_just_added
        if not should_backfill_primary_caregiver:
            try:
                from app.models import Resident as _Resident
                has_any_resident = db.query(_Resident).first() is not None
                has_any_assignment = db.query(_Resident).filter(_Resident.primary_caregiver_id.isnot(None)).first() is not None
                should_backfill_primary_caregiver = has_any_resident and not has_any_assignment
            except Exception:
                should_backfill_primary_caregiver = False

        if should_backfill_primary_caregiver:
            try:
                from app.models import DailyRecord, Resident, Schedule
                latest_caregiver_by_resident = {}
                for s in db.query(Schedule.resident_id, Schedule.caregiver_id, Schedule.scheduled_date).filter(Schedule.status != "cancelled").all():
                    prev = latest_caregiver_by_resident.get(s.resident_id)
                    if not prev or (s.scheduled_date and (not prev[1] or s.scheduled_date > prev[1])):
                        latest_caregiver_by_resident[s.resident_id] = (s.caregiver_id, s.scheduled_date)
                for d in db.query(DailyRecord.resident_id, DailyRecord.caregiver_id, DailyRecord.recorded_date).all():
                    prev = latest_caregiver_by_resident.get(d.resident_id)
                    if not prev or (d.recorded_date and (not prev[1] or d.recorded_date > prev[1])):
                        latest_caregiver_by_resident[d.resident_id] = (d.caregiver_id, d.recorded_date)

                filled = 0
                for resident in db.query(Resident).filter(Resident.primary_caregiver_id.is_(None)).all():
                    found = latest_caregiver_by_resident.get(resident.id)
                    if found and found[0]:
                        resident.primary_caregiver_id = found[0]
                        filled += 1
                db.commit()
                print(f"✅ primary_caregiver_id 1회성 백필 완료: {filled}명")
            except Exception as e:
                print(f"⚠️  primary_caregiver_id 백필 건너뜀: {e}")
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
