from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import users
from app.api.users import create_access_token, verify_password
from app.database import Base, get_db


def auth(uid, email, role):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "m@a.kr", "center_manager")
CAREGIVER = auth(2, "c@a.kr", "caregiver")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 's.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A센터"),
        models.User(id=1, email="m@a.kr", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@a.kr", full_name="요양사", role="caregiver", center_id=1),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(users.router, prefix="/api/v1/users")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


ROWS = [
    {"이름": "김요양", "이메일": "Kim@x.kr", "연락처": "010-1", "직종": "", "입사일": "2025.03.01"},
    {"이름": "이간호", "이메일": "lee@x.kr", "직종": "간호사"},
]


def test_check_then_save_creates_caregivers_with_temp_passwords(env):
    db, client = env
    r = client.post("/api/v1/users/import", json={"rows": ROWS, "dry_run": True}, headers=MANAGER).json()
    assert r["ok_count"] == 2 and not r["saved"] and db.query(models.User).count() == 2
    r = client.post("/api/v1/users/import", json={"rows": ROWS, "dry_run": False}, headers=MANAGER).json()
    assert r["saved"] and len(r["accounts"]) == 2
    kim = db.query(models.User).filter(models.User.email == "kim@x.kr").first()
    assert kim.role == "caregiver" and kim.center_id == 1 and kim.job_type is None and str(kim.hire_date) == "2025-03-01"
    assert verify_password(r["accounts"][0]["temp_password"], kim.hashed_password)
    assert db.query(models.User).filter(models.User.email == "lee@x.kr").first().job_type == "간호사"


def test_any_bad_row_blocks_everything(env):
    db, client = env
    rows = ROWS + [{"이름": "중복", "이메일": "c@a.kr"}, {"이름": "형식", "이메일": "nope"}, {"이름": "직종", "이메일": "z@x.kr", "직종": "의사"}]
    r = client.post("/api/v1/users/import", json={"rows": rows, "dry_run": False}, headers=MANAGER).json()
    assert not r["saved"] and [e["row"] for e in r["errors"]] == [4, 5, 6] and db.query(models.User).count() == 2


def test_only_manager_can_import(env):
    _, client = env
    assert client.post("/api/v1/users/import", json={"rows": ROWS, "dry_run": True}, headers=CAREGIVER).status_code == 403
