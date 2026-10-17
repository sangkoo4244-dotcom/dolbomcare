"""교육 수료증: 센터장이 직원별로 등록하고, 직원은 본인 것만 보며, 파일은 PDF·PNG·JPG 2MB 이하만 받는다."""
import base64
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import training_certs
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@t.kr")
CAREGIVER = auth(2, "caregiver", "c@t.kr")
OTHER_CAREGIVER = auth(4, "caregiver", "d@t.kr")
OTHER_CENTER = auth(7, "center_manager", "o@t.kr")
GUARDIAN = auth(5, "guardian", "g@t.kr")
PDF = "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.4 test").decode()


def body(**kw):
    return {"user_id": 2, "title": "요양보호사 보수교육", "completed_on": date.today().isoformat(), "hours": 3,
            "issuer": "교육기관", "file_name": "cert.pdf", "file_data": PDF, **kw}


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'tc.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A센터"), models.Center(id=2, name="B센터"),
        models.User(id=1, email="m@t.kr", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@t.kr", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=4, email="d@t.kr", full_name="다른요양사", role="caregiver", center_id=1),
        models.User(id=5, email="g@t.kr", full_name="보호자", role="guardian", center_id=1),
        models.User(id=7, email="o@t.kr", full_name="타센터장", role="center_manager", center_id=2),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(training_certs.router, prefix="/api/v1/training-certs")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_manager_registers_and_staff_sees_only_own(env):
    assert env.post("/api/v1/training-certs", json=body(), headers=MANAGER).status_code == 200
    assert env.post("/api/v1/training-certs", json=body(user_id=4), headers=MANAGER).status_code == 200
    mine = env.get("/api/v1/training-certs", headers=CAREGIVER).json()["data"]
    assert len(mine) == 1 and mine[0]["staff_name"] == "요양사" and mine[0]["has_file"] is True
    everyone = env.get("/api/v1/training-certs", headers=MANAGER).json()["data"]
    assert len(everyone) == 2


def test_file_download_only_for_owner_or_manager(env):
    env.post("/api/v1/training-certs", json=body(), headers=MANAGER)
    cid = env.get("/api/v1/training-certs", headers=MANAGER).json()["data"][0]["id"]
    r = env.get(f"/api/v1/training-certs/{cid}/file", headers=CAREGIVER)
    assert r.status_code == 200 and r.content == b"%PDF-1.4 test" and r.headers["content-type"] == "application/pdf"
    assert env.get(f"/api/v1/training-certs/{cid}/file", headers=OTHER_CAREGIVER).status_code == 403
    assert env.get(f"/api/v1/training-certs/{cid}/file", headers=OTHER_CENTER).status_code == 404


def test_file_type_and_size_limits(env):
    assert env.post("/api/v1/training-certs", json=body(file_data="data:text/html;base64,PGh0bWw="), headers=MANAGER).status_code == 400
    big = "data:image/png;base64," + base64.b64encode(b"x" * (2 * 1024 * 1024 + 1)).decode()
    assert env.post("/api/v1/training-certs", json=body(file_data=big), headers=MANAGER).status_code == 400
    assert env.post("/api/v1/training-certs", json=body(file_data=None), headers=MANAGER).status_code == 200


def test_caregiver_and_guardian_cannot_register_or_delete(env):
    assert env.post("/api/v1/training-certs", json=body(), headers=CAREGIVER).status_code == 403
    assert env.post("/api/v1/training-certs", json=body(), headers=GUARDIAN).status_code == 403
    env.post("/api/v1/training-certs", json=body(), headers=MANAGER)
    cid = env.get("/api/v1/training-certs", headers=MANAGER).json()["data"][0]["id"]
    assert env.delete(f"/api/v1/training-certs/{cid}", headers=CAREGIVER).status_code == 403
    assert env.delete(f"/api/v1/training-certs/{cid}", headers=OTHER_CENTER).status_code == 404
    assert env.delete(f"/api/v1/training-certs/{cid}", headers=MANAGER).status_code == 200
