"""센터장 셀프 가입: 공단 기관 확인과 지정서가 맞아야 계정이 생기고, 운영자가 지정서를 확인하기 전까지는 읽기 전용이다."""
import base64
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import facility_registry, models, plans
from app.api import admin, center_directory, users
from app.api.users import create_access_token
from app.database import Base, get_db

CODE = "11111000006"
CERT = base64.b64encode(b"%PDF-1.4 certificate").decode()
FORM = {"center_name": "행복센터", "sido_code": "11", "institution_code": CODE, "manager_name": "김센터장",
        "email": "Boss@Center.kr", "password": "password-1234", "phone": "010-1111-2222", "partner_interest": False,
        "certificate_name": "지정서.pdf", "certificate_type": "application/pdf", "certificate_data": CERT}
OPERATOR = {"Authorization": "Bearer " + create_access_token({"sub": "ops@eeum.kr", "uid": 1, "role": "center_manager"}, timedelta(hours=1))}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATFORM_ADMIN_EMAILS", "ops@eeum.kr")
    monkeypatch.setattr(facility_registry, "search_api", lambda *a: None)
    center_directory._recent_requests.clear()
    engine = create_engine(f"sqlite:///{tmp_path / 'signup.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.FacilityRegistry(code=CODE, name="행복센터", sido_code="11", source="test"),
        models.Center(id=1, name="운영센터"),
        models.User(id=1, email="ops@eeum.kr", full_name="운영자", role="center_manager", center_id=1),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(admin.router, prefix="/api/v1/admin")
    app.include_router(center_directory.router, prefix="/api/v1/centers")
    app.include_router(users.router, prefix="/api/v1/users")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def test_signup_creates_a_pending_center_and_manager_who_can_log_in_but_not_write(env):
    db, client = env
    response = client.post("/api/v1/centers/signup", json=FORM)
    assert response.status_code == 200 and response.json()["status"] == "created"
    center = db.query(models.Center).filter_by(institution_code=CODE).one()
    manager = db.query(models.User).filter_by(email="boss@center.kr").one()
    assert center.verified is False and center.manager_id == manager.id and manager.role == "center_manager"
    assert manager.hashed_password != "password-1234"  # 비밀번호는 해시로 저장
    assert plans.is_write_blocked(center, "POST", "/api/v1/residents/") is True
    assert plans.write_block_message(center) == plans.PENDING_VERIFY_MESSAGE
    assert plans.is_write_blocked(center, "GET", "/api/v1/residents/") is False
    assert client.post("/api/v1/users/login", json={"email": "boss@center.kr", "password": "password-1234"}).status_code == 200
    assert db.query(models.TrialRequest).one().cert_name == "지정서.pdf"  # 운영자가 볼 수 있게 남긴다


def test_signup_refuses_unlisted_facility_duplicate_email_and_duplicate_facility(env):
    db, client = env
    assert client.post("/api/v1/centers/signup", json={**FORM, "institution_code": "99999999999"}).status_code == 400
    assert client.post("/api/v1/centers/signup", json={**FORM, "password": "short"}).status_code == 400
    assert client.post("/api/v1/centers/signup", json={**FORM, "certificate_type": "text/plain"}).status_code == 400
    assert client.post("/api/v1/centers/signup", json=FORM).status_code == 200
    assert client.post("/api/v1/centers/signup", json={**FORM, "email": "boss@center.kr"}).status_code == 400  # 같은 이메일
    assert client.post("/api/v1/centers/signup", json={**FORM, "email": "other@center.kr"}).status_code == 400  # 같은 기관기호
    assert db.query(models.Center).filter_by(institution_code=CODE).count() == 1


def test_operator_confirming_the_certificate_opens_writing(env):
    db, client = env
    client.post("/api/v1/centers/signup", json=FORM)
    request_id = db.query(models.TrialRequest).one().id
    assert client.post(f"/api/v1/admin/trial-requests/{request_id}/handled", headers=OPERATOR).status_code == 200
    db.expire_all()
    center = db.query(models.Center).filter_by(institution_code=CODE).one()
    assert center.verified is True
    assert plans.is_write_blocked(center, "POST", "/api/v1/residents/") is False
