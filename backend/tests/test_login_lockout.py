"""로그인 시도 제한: 5번 틀리면 15분 잠금, 성공하면 기록이 지워지고, 잠금 확인이 고장나도 로그인은 막히지 않는다."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import login_guard, models
from app.api import users
from app.database import Base, get_db

EMAIL = "lock@test.com"
PASSWORD = "correct-pass-1"


@pytest.fixture
def client(tmp_path):
    login_guard.reset_all()
    engine = create_engine(f"sqlite:///{tmp_path / 'login.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.User(id=1, email=EMAIL, full_name="센터장", role="center_manager", center_id=None,
                       hashed_password=users.get_password_hash(PASSWORD)))
    db.commit()
    db.close()
    app = FastAPI()
    app.include_router(users.router, prefix="/api/v1/users")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    login_guard.reset_all()


def login(client, password):
    return client.post("/api/v1/users/login", json={"email": EMAIL, "password": password})


def test_five_wrong_passwords_lock_the_account_even_for_the_right_password(client):
    for _ in range(5):
        assert login(client, "wrong-pass").status_code == 401
    locked = login(client, PASSWORD)
    assert locked.status_code == 429
    assert "다시 시도" in locked.json()["detail"]


def test_lock_ends_after_the_wait(client, monkeypatch):
    for _ in range(5):
        login(client, "wrong-pass")
    assert login(client, PASSWORD).status_code == 429
    login_guard._locked_until[EMAIL] = datetime.now() - timedelta(seconds=1)  # 잠금 시간이 지난 것처럼
    assert login(client, PASSWORD).status_code == 200


def test_a_successful_login_clears_earlier_failures(client):
    for _ in range(4):
        login(client, "wrong-pass")
    assert login(client, PASSWORD).status_code == 200
    for _ in range(4):
        assert login(client, "wrong-pass").status_code == 401  # 성공 뒤라 아직 잠기지 않는다


def test_a_broken_lock_check_does_not_block_login(client, monkeypatch):
    def broken(_email, now=None):
        raise RuntimeError("잠금 확인 고장")

    monkeypatch.setattr(login_guard, "seconds_until_unlocked", broken)
    assert login(client, PASSWORD).status_code == 200


def test_failure_counting_window_expires(client):
    now = datetime.now()
    for i in range(4):
        login_guard.record_failure(EMAIL, now=now - timedelta(minutes=30 + i))  # 10분 창 밖의 실패들
    login(client, "wrong-pass")
    assert login_guard.seconds_until_unlocked(EMAIL) == 0
