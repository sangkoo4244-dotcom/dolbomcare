from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import audit_prep
from app.database import Base, get_db
from app.api.users import create_access_token


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    db = Session()
    db.add(models.Center(id=1, name="테스트센터"))
    db.add(models.User(id=1, email="manager@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="caregiver1@test.com", full_name="요양사1", role="caregiver", center_id=1))
    db.add(models.Resident(id=1, center_id=1, name="김이용", care_grade=2, client_type="일반"))
    # 기간 안의 방문기록 (서명 있음) + 기간 밖의 방문기록
    db.add(models.DailyRecord(
        id=1, resident_id=1, caregiver_id=2, recorded_date=datetime(2026, 10, 5),
        service_type="basic_care", duration_minutes=60, signature="data:image/png;base64,xyz",
    ))
    db.add(models.DailyRecord(
        id=2, resident_id=1, caregiver_id=2, recorded_date=datetime(2026, 9, 1),
        service_type="basic_care", duration_minutes=60,
    ))
    db.add(models.NeedsAssessment(
        id=1, resident_id=1, assessed_by=2, assessed_date=datetime(2026, 10, 3), nutrition_status="good",
    ))
    db.add(models.RiskAssessment(
        id=1, resident_id=1, assessment_type="fall_risk", assessed_by=2,
        assessed_date=datetime(2026, 10, 4), score=10, risk_level="low",
    ))
    db.add(models.CopayInvoice(
        id=1, resident_id=1, center_id=1, year_month="2026-10", total_amount=20000, paid_amount=20000, status="paid",
    ))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(audit_prep.router, prefix="/api/v1/audit-prep")

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


MANAGER = auth(1, "center_manager", "manager@test.com")
CAREGIVER = auth(2, "caregiver", "caregiver1@test.com")


def test_packet_only_includes_records_within_date_range(client):
    res = client.get(
        "/api/v1/audit-prep/resident/1?start=2026-10-01&end=2026-10-31", headers=MANAGER,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["resident"]["name"] == "김이용"
    assert data["visits"]["count"] == 1  # 9월 기록은 빠져야 한다
    assert data["visits"]["signed_count"] == 1
    assert len(data["needs_assessments"]) == 1
    assert data["risk_assessments"]["fall_risk"]["records"][0]["score"] == 10
    assert data["risk_assessments"]["pressure_sore_risk"]["records"] == []
    assert len(data["copay"]) == 1
    assert data["copay"][0]["status"] == "paid"


def test_end_date_is_inclusive(client):
    res = client.get(
        "/api/v1/audit-prep/resident/1?start=2026-10-05&end=2026-10-05", headers=MANAGER,
    )
    assert res.status_code == 200
    assert res.json()["visits"]["count"] == 1  # 10/5 기록이 end=10/5 조회에도 포함되어야 한다


def test_caregiver_forbidden(client):
    res = client.get(
        "/api/v1/audit-prep/resident/1?start=2026-10-01&end=2026-10-31", headers=CAREGIVER,
    )
    assert res.status_code == 403
