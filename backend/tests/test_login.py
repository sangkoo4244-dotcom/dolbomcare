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


def make_staff_client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'staff.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.Center(id=1, name="센터A"))
    db.add(models.Center(id=2, name="센터B"))
    db.add(models.User(id=1, email="manager@test.com", hashed_password=users.get_password_hash("manager-pass-1"), full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="caregiver1@test.com", hashed_password=users.get_password_hash("old-pass-1234"), full_name="요양사1", role="caregiver", center_id=1))
    db.add(models.User(id=3, email="other@test.com", hashed_password=users.get_password_hash("other-pass-1"), full_name="타센터", role="caregiver", center_id=2))
    db.commit()
    db.close()
    app = FastAPI()
    app.include_router(users.router, prefix="/api/v1/users")

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def manager_token():
    from datetime import timedelta
    from app.api.users import create_access_token
    token = create_access_token({"sub": "manager@test.com", "uid": 1, "role": "center_manager"}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


def test_manager_resets_staff_password_and_staff_can_log_in(tmp_path):
    client = make_staff_client(tmp_path)
    reset = client.post("/api/v1/users/2/password", json={"new_password": "brand-new-1234"}, headers=manager_token())
    assert reset.status_code == 200
    assert client.post("/api/v1/users/login", json={"email": "caregiver1@test.com", "password": "old-pass-1234"}).status_code == 401
    assert client.post("/api/v1/users/login", json={"email": "caregiver1@test.com", "password": "brand-new-1234"}).status_code == 200


def test_reset_rejects_short_password(tmp_path):
    client = make_staff_client(tmp_path)
    assert client.post("/api/v1/users/2/password", json={"new_password": "short"}, headers=manager_token()).status_code == 400


def test_reset_rejects_staff_from_another_center(tmp_path):
    client = make_staff_client(tmp_path)
    assert client.post("/api/v1/users/3/password", json={"new_password": "brand-new-1234"}, headers=manager_token()).status_code == 403


def test_caregiver_cannot_reset_passwords(tmp_path):
    from datetime import timedelta
    from app.api.users import create_access_token
    client = make_staff_client(tmp_path)
    token = create_access_token({"sub": "caregiver1@test.com", "uid": 2, "role": "caregiver"}, timedelta(hours=1))
    response = client.post("/api/v1/users/2/password", json={"new_password": "brand-new-1234"}, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
