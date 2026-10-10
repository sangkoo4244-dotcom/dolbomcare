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


def test_morse_fall_scale_server_computes_score_and_risk(client):
    # 낙상 경험(25) + 보행보조기구 가구짚고이동(30) = 55점 -> 25점 이상이므로 high
    res = client.post("/api/v1/risk-assessments/", headers=CAREGIVER, json={
        "resident_id": 1, "assessment_type": "fall_risk", "tool_name": "morse_fall_scale",
        "item_scores": {
            "history": "yes", "secondary_diagnosis": "no", "ambulatory_aid": "furniture",
            "iv_therapy": "no", "gait": "normal", "mental_status": "aware",
        },
    })
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["score"] == 55
    assert body["risk_level"] == "high"
    assert body["item_scores"]["ambulatory_aid"] == "furniture"


def test_morse_fall_scale_low_risk_below_25(client):
    res = client.post("/api/v1/risk-assessments/", headers=CAREGIVER, json={
        "resident_id": 1, "assessment_type": "fall_risk", "tool_name": "morse_fall_scale",
        "item_scores": {
            "history": "no", "secondary_diagnosis": "no", "ambulatory_aid": "none",
            "iv_therapy": "no", "gait": "normal", "mental_status": "aware",
        },
    })
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["score"] == 0
    assert body["risk_level"] == "low"


def test_braden_scale_server_computes_score_and_risk(client):
    # 모두 최저점: 1+1+1+1+1+1 = 6점 -> 15점 이하이므로 high (최고위험군)
    res = client.post("/api/v1/risk-assessments/", headers=CAREGIVER, json={
        "resident_id": 1, "assessment_type": "pressure_sore_risk", "tool_name": "braden_scale",
        "item_scores": {
            "sensory_perception": "1", "moisture": "1", "activity": "1",
            "mobility": "1", "nutrition": "1", "friction_shear": "1",
        },
    })
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["score"] == 6
    assert body["risk_level"] == "high"


def test_braden_scale_low_risk_above_15(client):
    res = client.post("/api/v1/risk-assessments/", headers=CAREGIVER, json={
        "resident_id": 1, "assessment_type": "pressure_sore_risk", "tool_name": "braden_scale",
        "item_scores": {
            "sensory_perception": "4", "moisture": "4", "activity": "4",
            "mobility": "4", "nutrition": "4", "friction_shear": "3",
        },
    })
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["score"] == 23
    assert body["risk_level"] == "low"


def test_invalid_checklist_choice_rejected(client):
    res = client.post("/api/v1/risk-assessments/", headers=CAREGIVER, json={
        "resident_id": 1, "assessment_type": "fall_risk", "tool_name": "morse_fall_scale",
        "item_scores": {"history": "maybe"},
    })
    assert res.status_code == 400


def test_dementia_diagnosis_alternative_marks_high_risk_without_score(client):
    res = client.post("/api/v1/risk-assessments/", headers=CAREGIVER, json={
        "resident_id": 1, "assessment_type": "cognitive_function", "tool_name": "dementia_dx_medication",
        "notes": "처방전 확인 완료",
    })
    assert res.status_code == 200
    body = res.json()["data"]
    assert body["risk_level"] == "high"
    assert body["score"] is None


def test_options_endpoint_includes_item_definitions(client):
    res = client.get("/api/v1/risk-assessments/options")
    assert res.status_code == 200
    data = res.json()
    assert "ambulatory_aid" in data["morse_fall_items"]
    assert "friction_shear" in data["braden_items"]
    assert "k_mmse" in data["cognitive_tools"]
