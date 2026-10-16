"""기초평가 현황: 마지막 평가 날짜와 경과일로 확인 필요를 표시하고, 요양보호사는 볼 수 없다."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import needs_assessments
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MANAGER = auth(1, "center_manager", "m@test.com")
CAREGIVER = auth(2, "caregiver", "c@test.com")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'na.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1),
        models.Resident(id=1, center_id=1, name="최근이용자"),
        models.Resident(id=2, center_id=1, name="오래된이용자"),
        models.Resident(id=3, center_id=1, name="없는이용자"),
    ])
    db.flush()
    db.add_all([
        models.NeedsAssessment(resident_id=1, assessed_by=1, assessed_date=datetime.now() - timedelta(days=5)),
        models.NeedsAssessment(resident_id=2, assessed_by=1, assessed_date=datetime.now() - timedelta(days=90)),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(needs_assessments.router, prefix="/api/v1/needs-assessments")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_status_marks_recent_old_and_never_assessed(env):
    data = env.get("/api/v1/needs-assessments/status", headers=MANAGER).json()["data"]
    by_name = {i["name"]: i for i in data["items"]}
    assert by_name["최근이용자"]["due"] is False and by_name["최근이용자"]["days_since"] == 5
    assert by_name["오래된이용자"]["due"] is True
    assert by_name["없는이용자"]["last_date"] is None and by_name["없는이용자"]["due"] is True
    assert data["due_count"] == 2


def test_caregiver_cannot_open_the_status(env):
    assert env.get("/api/v1/needs-assessments/status", headers=CAREGIVER).status_code == 403
