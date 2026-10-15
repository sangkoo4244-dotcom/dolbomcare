import os
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import admin
from app.api.users import create_access_token
from app.database import Base, get_db
from app.demo_seed import DEMO_CENTER_NAME, DEMO_MANAGER_EMAIL


def auth(uid, email, role="center_manager"):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


OPERATOR = auth(1, "ops@eeum.kr")
REAL_MANAGER = auth(2, "real@center.kr")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATFORM_ADMIN_EMAILS", "ops@eeum.kr")
    engine = create_engine(f"sqlite:///{tmp_path / 'demo.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="운영센터"),
        models.User(id=1, email="ops@eeum.kr", full_name="운영자", role="center_manager", center_id=1),
        models.User(id=2, email="real@center.kr", full_name="실센터장", role="center_manager", center_id=1),
        models.Resident(id=1, center_id=1, name="실제이용자", care_grade=3, client_type="일반"),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(admin.router, prefix="/api/v1/admin")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def test_only_the_operator_can_see_or_reset_the_demo(env):
    _, client = env
    assert client.get("/api/v1/admin/demo/status", headers=REAL_MANAGER).status_code == 403
    assert client.post("/api/v1/admin/demo/reset", headers=REAL_MANAGER).status_code == 403
    assert client.post("/api/v1/admin/demo/reset").status_code in (401, 403)


def test_reset_creates_the_demo_accounts_and_is_repeatable_without_touching_real_data(env):
    db, client = env
    assert client.get("/api/v1/admin/demo/status", headers=OPERATOR).json()["ready"] is False
    first = client.post("/api/v1/admin/demo/reset", headers=OPERATOR).json()
    assert first["residents"] == 3 and first["bills"] == 15 and first["schedules"] == 9 and first["reset"] is False
    status = client.get("/api/v1/admin/demo/status", headers=OPERATOR).json()
    assert status["ready"] is True and all(a["exists"] for a in status["accounts"])
    # 다시 실행하면 초기화 후 같은 모양으로 다시 만들어진다 (이용자·청구가 두 배로 늘지 않는다)
    second = client.post("/api/v1/admin/demo/reset", headers=OPERATOR).json()
    assert second["reset"] is True
    db.expire_all()
    demo = db.query(models.Center).filter_by(name=DEMO_CENTER_NAME).all()
    assert len(demo) == 1
    assert db.query(models.Resident).filter_by(center_id=demo[0].id).count() == 3
    assert db.query(models.BillingRecord).filter_by(center_id=demo[0].id).count() == 15
    # 실제 센터 자료는 그대로
    assert db.query(models.Resident).filter_by(name="실제이용자").count() == 1 and db.query(models.User).filter_by(email="real@center.kr").count() == 1


def test_orphan_demo_guardian_left_by_a_center_delete_does_not_block_a_new_seed(env):
    db, client = env
    client.post("/api/v1/admin/demo/reset", headers=OPERATOR)
    demo_center = db.query(models.Center).filter_by(name=DEMO_CENTER_NAME).one()
    # 운영자 콘솔에서 센터만 지워 보호자 계정(센터 없음)이 남은 상태를 흉내 낸다
    db.query(models.User).filter(models.User.center_id == demo_center.id).delete()
    db.query(models.Schedule).filter_by(center_id=demo_center.id).delete()
    db.query(models.BillingRecord).filter_by(center_id=demo_center.id).delete()
    db.query(models.DailyRecord).delete()
    db.query(models.ResidentMessage).delete()
    db.query(models.Resident).filter_by(center_id=demo_center.id).delete()
    db.delete(demo_center)
    db.commit()
    assert db.query(models.User).filter(models.User.email.like("demo_guardian%")).count() == 1
    assert client.post("/api/v1/admin/demo/reset", headers=OPERATOR).status_code == 200
    assert db.query(models.User).filter_by(email=DEMO_MANAGER_EMAIL).count() == 1
