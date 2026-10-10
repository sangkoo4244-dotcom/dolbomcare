from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import risk_assessments
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
    db.add(models.Resident(id=1, center_id=1, name="김이용"))
    db.add(models.Resident(id=2, center_id=2, name="타센터이용자"))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(risk_assessments.router, prefix="/api/v1/risk-assessments")

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


def test_resident_with_no_history_is_overdue_for_all_types(client):
    res = client.get("/api/v1/risk-assessments/resident/1", headers=MANAGER)
    assert res.status_code == 200
    data = res.json()["assessments"]
    assert set(data.keys()) == {"fall_risk", "pressure_sore_risk", "cognitive_function"}
    for item in data.values():
        assert item["latest"] is None
        assert item["is_overdue"] is True
        assert item["next_due_date"] is None


def test_create_and_read_back(client):
    res = client.post("/api/v1/risk-assessments/", headers=CAREGIVER, json={
        "resident_id": 1, "assessment_type": "fall_risk", "score": 17, "risk_level": "high", "notes": "최근 낙상 1회",
    })
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["risk_level"] == "high"
    assert body["assessed_by_name"] == "요양사1"

    res = client.get("/api/v1/risk-assessments/resident/1", headers=MANAGER)
    fall = res.json()["assessments"]["fall_risk"]
    assert fall["latest"]["score"] == 17
    assert fall["is_overdue"] is False
    assert len(fall["history"]) == 1
    # 다른 종류는 여전히 미실시 상태여야 한다
    assert res.json()["assessments"]["pressure_sore_risk"]["latest"] is None


def test_overdue_after_cadence_passes(client):
    db_cls = client.app.dependency_overrides[get_db]
    session = next(db_cls())
    session.add(models.RiskAssessment(
        resident_id=1, assessment_type="cognitive_function", assessed_by=2,
        assessed_date=datetime.utcnow() - timedelta(days=200), score=22, risk_level="low",
    ))
    session.commit()
    session.close()

    res = client.get("/api/v1/risk-assessments/resident/1", headers=MANAGER)
    cog = res.json()["assessments"]["cognitive_function"]
    assert cog["latest"] is not None
    assert cog["is_overdue"] is True  # 200일 전 평가, 반기(183일) 주기를 넘김


def test_invalid_assessment_type_rejected(client):
    res = client.post("/api/v1/risk-assessments/", headers=CAREGIVER, json={
        "resident_id": 1, "assessment_type": "made_up_type", "score": 10,
    })
    assert res.status_code == 400


def test_cannot_access_other_centers_resident(client):
    res = client.get("/api/v1/risk-assessments/resident/2", headers=MANAGER)
    assert res.status_code == 404
