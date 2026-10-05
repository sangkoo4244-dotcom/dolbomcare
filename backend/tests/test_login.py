from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import billing, users
from app.database import Base, get_db


def make_client(tmp_path, email, stored_hash):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.User(id=1, email=email, hashed_password=stored_hash, full_name="테스트", role="caregiver"))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(users.router, prefix="/api/v1/users")
    app.include_router(billing.router, prefix="/api/v1/billing")

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_test_domain_account_needs_correct_password(tmp_path):
    hashed = users.get_password_hash("correct-pass")
    client = make_client(tmp_path, "caregiver1@test.com", hashed)
    wrong = client.post("/api/v1/users/login", json={"email": "caregiver1@test.com", "password": "anything"})
    assert wrong.status_code == 401
    right = client.post("/api/v1/users/login", json={"email": "caregiver1@test.com", "password": "correct-pass"})
    assert right.status_code == 200


def test_account_with_non_bcrypt_stored_hash_gets_401_not_500(tmp_path):
    client = make_client(tmp_path, "caregiver1@test.com", "plain-text-not-a-hash")
    response = client.post("/api/v1/users/login", json={"email": "caregiver1@test.com", "password": "x"})
    assert response.status_code == 401


def test_unauthenticated_billing_state_routes_are_gone(tmp_path):
    client = make_client(tmp_path, "caregiver1@test.com", users.get_password_hash("p"))
    assert client.put("/api/v1/billing/1/submit").status_code in (404, 405)
    assert client.put("/api/v1/billing/1/pay").status_code in (404, 405)
