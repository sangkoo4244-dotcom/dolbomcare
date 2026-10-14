from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import residents
from app.api.users import create_access_token
from app.database import Base, get_db


@pytest.fixture
def ctx(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'rd.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A"), models.Center(id=2, name="B"),
        models.User(id=1, email="m@e.com", hashed_password="x", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@e.com", hashed_password="x", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=3, email="m2@e.com", hashed_password="x", full_name="타센터장", role="center_manager", center_id=2),
        models.Resident(id=1, center_id=1, name="빈이용자", age=80, health_status="stable", care_grade=1, client_type="일반"),
        models.Resident(id=2, center_id=1, name="기록있음", age=80, health_status="stable", care_grade=1, client_type="일반"),
        models.Schedule(caregiver_id=2, resident_id=2, center_id=1, scheduled_date=datetime.now() + timedelta(days=1), status="scheduled"),
        models.DailyRecord(resident_id=2, caregiver_id=2, recorded_date=datetime.now(), service_type="basic_care", condition="good", duration_minutes=60),
    ])
    db.commit()
    db.close()
    app = FastAPI()
    app.include_router(residents.router, prefix="/api/v1/residents")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app), Session


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MGR = auth(1, "center_manager", "m@e.com")


def test_manager_deletes_resident_without_records_with_no_extra_params(ctx):
    client, Session = ctx
    assert client.delete("/api/v1/residents/1", headers=MGR).status_code == 200  # 화면은 user_role 같은 값을 보내지 않는다
    assert Session().query(models.Resident).filter_by(id=1).first() is None


def test_resident_with_records_asks_before_deleting_everything(ctx):
    client, Session = ctx
    r = client.delete("/api/v1/residents/2", headers=MGR)
    assert r.status_code == 409
    assert "방문 기록 1건" in r.json()["detail"]["message"] and "방문 일정 1건" in r.json()["detail"]["message"]
    assert Session().query(models.Resident).filter_by(id=2).first() is not None
    assert client.delete("/api/v1/residents/2?force=true", headers=MGR).status_code == 200
    db = Session()
    assert db.query(models.Resident).filter_by(id=2).first() is None
    assert db.query(models.DailyRecord).count() == 0 and db.query(models.Schedule).count() == 0


def test_other_center_and_caregiver_cannot_delete(ctx):
    client, _ = ctx
    assert client.delete("/api/v1/residents/1", headers=auth(3, "center_manager", "m2@e.com")).status_code == 404
    assert client.delete("/api/v1/residents/1", headers=auth(2, "caregiver", "c@e.com")).status_code == 403
