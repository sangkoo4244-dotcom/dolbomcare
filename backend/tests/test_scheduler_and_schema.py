"""정기 작업 스케줄러와 운영 DB 점검 도구: 다음 실행 시각 계산, 센터별 알림 발송과 중복 방지, 빠진 컬럼 탐지."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app import models, scheduler, schema_check
from app.database import Base


def test_seconds_until_same_day_and_next_day():
    assert scheduler.seconds_until(7, now=datetime(2026, 10, 17, 6, 0, 0)) == 3600
    assert scheduler.seconds_until(7, now=datetime(2026, 10, 17, 8, 0, 0)) == 23 * 3600
    assert scheduler.seconds_until(7, now=datetime(2026, 10, 17, 7, 0, 0)) == 24 * 3600


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'sch.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    s.add_all([
        models.Center(id=1, name="A센터"), models.Center(id=2, name="B센터"),
        models.User(id=1, email="m@t.kr", full_name="센터장A", role="center_manager", center_id=1),
        models.User(id=2, email="m2@t.kr", full_name="센터장B", role="center_manager", center_id=2),
        models.Resident(id=1, center_id=1, name="김이용", age=80, health_status="stable", care_grade=2, client_type="일반"),
        models.Resident(id=2, center_id=2, name="이이용", age=80, health_status="stable", care_grade=2, client_type="일반"),
    ])
    s.commit()
    yield s
    s.close()


def test_daily_job_notifies_each_center_once(db):
    first = scheduler.run_daily_jobs(db)
    assert first["centers"] == 2
    # 평가가 한 번도 없으므로 이용자 2명 x 3종 = 6건, 센터장 2명 중 각 센터장에게 3건씩
    assert first["assessment_due_sent"] == 6
    again = scheduler.run_daily_jobs(db)
    assert again["assessment_due_sent"] == 0  # 같은 달에는 다시 보내지 않는다


def test_schema_check_detects_dropped_column_and_passes_when_complete(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schema.db'}")
    Base.metadata.create_all(bind=engine)
    assert schema_check.missing_schema(engine) == {"missing_tables": [], "missing_columns": []}
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE daily_records DROP COLUMN review_note"))
    result = schema_check.missing_schema(engine)
    assert ("daily_records", "review_note") in result["missing_columns"]
    assert result["missing_tables"] == []


def test_scheduler_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("SCHEDULER_ENABLED", "0")
    assert scheduler.start(lambda: None) is None
