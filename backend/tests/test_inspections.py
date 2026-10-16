"""점검 기록: 항목은 종류별로 정해진 것만, 값은 ok/fail/na, 센터장과 요양보호사만 기록한다."""
from datetime import date, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import inspections
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MANAGER = auth(1, "center_manager", "m@test.com")
CG = auth(2, "caregiver", "c@test.com")
GUARDIAN = auth(9, "guardian", "g@test.com")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'insp.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=9, email="g@test.com", full_name="보호자", role="guardian", center_id=None),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(inspections.router, prefix="/api/v1/inspections")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def test_caregiver_records_and_manager_reads_bath_tub_check(env):
    _, client = env
    body = {"kind": "bath_tub", "check_date": date.today().isoformat(),
            "results": {"욕조 세척·소독": "ok", "배수 상태": "fail"}, "note": "배수 불량, 수리 요청"}
    assert client.post("/api/v1/inspections", json=body, headers=CG).status_code == 200
    rows = client.get("/api/v1/inspections", params={"kind": "bath_tub"}, headers=MANAGER).json()["data"]
    assert rows[0]["results"]["배수 상태"] == "fail" and rows[0]["inspector"] == "요양사"


def test_unknown_item_and_value_are_refused_and_guardian_cannot_record(env):
    _, client = env
    base = {"kind": "vehicle", "check_date": date.today().isoformat()}
    assert client.post("/api/v1/inspections", json={**base, "results": {"없는 항목": "ok"}}, headers=CG).status_code == 400
    assert client.post("/api/v1/inspections", json={**base, "results": {"응급 키트": "maybe"}}, headers=CG).status_code == 400
    assert client.post("/api/v1/inspections", json={**base, "results": {"응급 키트": "ok"}}, headers=GUARDIAN).status_code == 403
    assert client.get("/api/v1/inspections", headers=CG).status_code == 403
