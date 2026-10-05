from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import guardian
from app.api.users import create_access_token
from app.database import Base, get_db


@pytest.fixture
def setup(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.Center(id=1, name="테스트센터"))
    db.add(models.User(id=1, email="manager@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="caregiver1@test.com", full_name="요양사1", role="caregiver", center_id=1))
    db.add(models.Resident(id=1, center_id=1, name="김1", age=80, health_status="stable", care_grade=1, client_type="일반"))
    db.add(models.Resident(id=2, center_id=1, name="이2", age=82, health_status="stable", care_grade=2, client_type="일반"))
    db.add(models.DailyRecord(
        id=1, caregiver_id=2, resident_id=1, recorded_date=datetime(2026, 10, 5, 9, 30),
        care_items="meal_assist,bath", condition="good", notes="식사를 잘 드셨습니다", duration_minutes=60,
    ))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(guardian.router, prefix="/api/v1/guardian")

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.Session = Session
    return client


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "manager@test.com")
CAREGIVER = auth(2, "caregiver", "caregiver1@test.com")


def issue_code(client, resident_id=1):
    response = client.post("/api/v1/guardian/invites", json={"resident_id": resident_id}, headers=MANAGER)
    assert response.status_code == 200
    return response.json()["code"]


def signup(client, code, email="guardian@test.com"):
    return client.post("/api/v1/guardian/signup", json={
        "email": email, "password": "GuardianPass1", "full_name": "김보호", "phone": "010-1111-2222", "invite_code": code,
    })


def approve_latest(client):
    request_id = client.get("/api/v1/guardian/requests", headers=MANAGER).json()["requests"][0]["id"]
    return client.post(f"/api/v1/guardian/requests/{request_id}/approve", headers=MANAGER)


def test_manager_issues_invite_and_guardian_signs_up_with_it(setup):
    code = issue_code(setup)
    response = signup(setup, code)
    assert response.status_code == 200
    db = setup.Session()
    user = db.query(models.User).filter(models.User.email == "guardian@test.com").first()
    assert user.role == "guardian"
    assert user.center_id == 1
    db.close()


def test_signup_rejects_unknown_or_reused_code(setup):
    assert signup(setup, "NOPE0000").status_code == 400
    code = issue_code(setup)
    assert signup(setup, code, email="a@test.com").status_code == 200
    assert signup(setup, code, email="b@test.com").status_code == 400


def test_signup_cannot_choose_a_role(setup):
    code = issue_code(setup)
    response = setup.post("/api/v1/guardian/signup", json={
        "email": "g@test.com", "password": "GuardianPass1", "full_name": "김보호", "phone": "010-1111-2222",
        "invite_code": code, "role": "center_manager",
    })
    db = setup.Session()
    user = db.query(models.User).filter(models.User.email == "g@test.com").first()
    assert user.role == "guardian"
    db.close()


def test_guardian_sees_nothing_before_manager_approves(setup):
    code = issue_code(setup)
    signup(setup, code)
    db = setup.Session()
    guardian_id = db.query(models.User).filter(models.User.email == "guardian@test.com").first().id
    db.close()
    headers = auth(guardian_id, "guardian", "guardian@test.com")
    assert setup.get("/api/v1/guardian/my-residents", headers=headers).json()["residents"] == []
    assert setup.get("/api/v1/guardian/residents/1/visits", headers=headers).status_code == 403


def test_approved_guardian_sees_own_resident_visits_without_money(setup):
    code = issue_code(setup)
    signup(setup, code)
    assert approve_latest(setup).status_code == 200
    db = setup.Session()
    guardian_id = db.query(models.User).filter(models.User.email == "guardian@test.com").first().id
    db.close()
    headers = auth(guardian_id, "guardian", "guardian@test.com")

    residents = setup.get("/api/v1/guardian/my-residents", headers=headers).json()["residents"]
    assert [r["id"] for r in residents] == [1]

    body = setup.get("/api/v1/guardian/residents/1/visits", headers=headers, params={"days": 365}).json()
    assert body["visits"][0]["care_items"] == ["식사 보조", "목욕·세면"]
    assert body["visits"][0]["condition"] == "좋음"
    assert body["visits"][0]["notes"] == "식사를 잘 드셨습니다"
    assert "amount" not in str(body)


def test_guardian_cannot_see_another_residents_visits(setup):
    code = issue_code(setup)
    signup(setup, code)
    approve_latest(setup)
    db = setup.Session()
    guardian_id = db.query(models.User).filter(models.User.email == "guardian@test.com").first().id
    db.close()
    headers = auth(guardian_id, "guardian", "guardian@test.com")
    assert setup.get("/api/v1/guardian/residents/2/visits", headers=headers).status_code == 403


def test_caregiver_cannot_use_guardian_views_or_approve(setup):
    code = issue_code(setup)
    signup(setup, code)
    assert setup.get("/api/v1/guardian/requests", headers=CAREGIVER).status_code == 403
    request_id = setup.get("/api/v1/guardian/requests", headers=MANAGER).json()["requests"][0]["id"]
    assert setup.post(f"/api/v1/guardian/requests/{request_id}/approve", headers=CAREGIVER).status_code == 403
