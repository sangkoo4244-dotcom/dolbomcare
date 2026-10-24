"""센터 데이터 내보내기: 센터장 전용, 같은 센터만, 기간 안의 기록만, 비밀번호 제외."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import data_export
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@test.com")
CAREGIVER = auth(2, "caregiver", "c@test.com")
OTHER_MANAGER = auth(7, "center_manager", "o@test.com")


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'export.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A"), models.Center(id=2, name="B"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1, hashed_password="secret-hash"),
        models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=7, email="o@test.com", full_name="타센터장", role="center_manager", center_id=2),
        models.Resident(id=1, center_id=1, name="김이용", care_grade=2),
        models.Resident(id=9, center_id=2, name="타센터이용", care_grade=2),
        models.DailyRecord(id=1, resident_id=1, caregiver_id=2, recorded_date=datetime(2026, 10, 5, 10), service_type="basic_care",
                           duration_minutes=60, notes="식사 보조"),
        models.DailyRecord(id=2, resident_id=1, caregiver_id=2, recorded_date=datetime(2026, 11, 5, 10), service_type="basic_care",
                           duration_minutes=60, notes="기간 밖"),
        models.DailyRecord(id=3, resident_id=9, caregiver_id=2, recorded_date=datetime(2026, 10, 5, 10), service_type="basic_care",
                           duration_minutes=60, notes="다른 센터"),
    ])
    db.commit()
    db.close()
    app = FastAPI()
    app.include_router(data_export.router, prefix="/api/v1/data-export")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_only_the_center_manager_can_export(client):
    assert client.get("/api/v1/data-export/center?start=2026-10-01&end=2026-10-31", headers=CAREGIVER).status_code == 403


def test_export_contains_only_own_center_and_period(client):
    body = client.get("/api/v1/data-export/center?start=2026-10-01&end=2026-10-31", headers=MANAGER).json()
    assert [r["name"] for r in body["residents"]] == ["김이용"]
    assert [r["notes"] for r in body["daily_records"]] == ["식사 보조"]
    assert body["daily_records"][0]["caregiver_name"] == "요양사"


def test_export_never_includes_password_or_auth_fields(client):
    text = client.get("/api/v1/data-export/center?start=2026-10-01&end=2026-10-31", headers=MANAGER).text
    assert "secret-hash" not in text and "hashed_password" not in text


def test_other_manager_sees_only_their_own_center(client):
    body = client.get("/api/v1/data-export/center?start=2026-10-01&end=2026-10-31", headers=OTHER_MANAGER).json()
    assert [r["name"] for r in body["residents"]] == ["타센터이용"]
    assert [r["notes"] for r in body["daily_records"]] == ["다른 센터"]


def test_invalid_period_is_refused(client):
    assert client.get("/api/v1/data-export/center?start=2026-10-31&end=2026-10-01", headers=MANAGER).status_code == 400
    assert client.get("/api/v1/data-export/center?start=2025-01-01&end=2026-10-01", headers=MANAGER).status_code == 400
