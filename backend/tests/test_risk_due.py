"""센터 평가 기한 목록: 낙상·욕창·인지 평가를 반기(183일)마다 해야 하며, 한 번도 안 한 것도 기한 초과로 본다."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import risk_assessments
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@t.kr")
SOCIAL = auth(3, "social_worker", "s@t.kr")
CAREGIVER = auth(2, "caregiver", "c@t.kr")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'due.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A센터"),
        models.User(id=1, email="m@t.kr", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@t.kr", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=3, email="s@t.kr", full_name="사회복지사", role="social_worker", center_id=1),
        models.Resident(id=1, center_id=1, name="김이용", age=80, health_status="stable", care_grade=2, client_type="일반"),
        models.Resident(id=2, center_id=1, name="이이용", age=80, health_status="stable", care_grade=2, client_type="일반"),
        # 김이용: 낙상은 어제 함(기한 내), 인지는 400일 전(기한 초과), 욕창은 한 번도 없음
        models.RiskAssessment(resident_id=1, assessment_type="fall_risk", assessed_by=3, assessed_date=datetime.now() - timedelta(days=1), score=20),
        models.RiskAssessment(resident_id=1, assessment_type="cognitive_function", assessed_by=3, assessed_date=datetime.now() - timedelta(days=400), score=18),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(risk_assessments.router, prefix="/api/v1/risk-assessments")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_center_due_lists_overdue_and_never_done(env):
    r = env.get("/api/v1/risk-assessments/center-due", headers=MANAGER)
    assert r.status_code == 200
    items = r.json()["data"]["items"]
    got = {(i["resident_name"], i["type"]) for i in items}
    # 김이용 낙상(기한 내)은 빠지고, 인지(초과)·욕창(미실시)은 들어간다. 이용자 2명은 3종 모두 미실시
    assert ("김이용", "fall_risk") not in got
    assert ("김이용", "cognitive_function") in got
    assert ("김이용", "pressure_sore_risk") in got
    assert ("이이용", "fall_risk") in got
    never = next(i for i in items if i["resident_name"] == "김이용" and i["type"] == "pressure_sore_risk")
    assert never["last_date"] is None and never["due_date"] is None


def test_social_worker_allowed_and_caregiver_refused(env):
    assert env.get("/api/v1/risk-assessments/center-due", headers=SOCIAL).status_code == 200
    assert env.get("/api/v1/risk-assessments/center-due", headers=CAREGIVER).status_code == 403


def test_notify_due_sends_once_per_month_per_item(env):
    db_session = env.app.dependency_overrides[get_db]()
    db = next(db_session)
    r1 = env.post("/api/v1/risk-assessments/center-due/notify", headers=MANAGER)
    assert r1.status_code == 200 and r1.json()["data"]["sent"] > 0
    r2 = env.post("/api/v1/risk-assessments/center-due/notify", headers=MANAGER)
    assert r2.json()["data"]["sent"] == 0  # 같은 달에는 다시 보내지 않는다
    kinds = db.query(models.Notification).filter(models.Notification.kind == "assessment_due").all()
    assert {n.user_id for n in kinds} == {1, 3}  # 센터장과 사회복지사만
    assert env.post("/api/v1/risk-assessments/center-due/notify", headers=CAREGIVER).status_code == 403
