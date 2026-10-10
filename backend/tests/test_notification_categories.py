from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import notifications, users
from app.database import Base, get_db
from app.api.users import create_access_token


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def setup(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    db = Session()
    db.add(models.Center(id=1, name="테스트센터"))
    db.add(models.User(
        id=1, email="guardian@test.com", full_name="보호자", role="guardian",
        phone="010-1234-5678", alimtalk_opt_in=True,
    ))
    db.commit()
    db.close()

    # 알림톡 전송 자체는 외부 API라 실제로 부르지 않고, 호출됐는지만 기록한다
    sent = []
    monkeypatch.setattr(notifications, "TEMPLATE_IDS", {"visit_completed": "tpl_1", "message_received": "tpl_2"})
    monkeypatch.setattr(notifications, "send_alimtalk", lambda phone, kind, message: sent.append(kind))

    app = FastAPI()
    app.include_router(notifications.router, prefix="/api/v1/notifications")
    app.include_router(users.router, prefix="/api/v1/users")

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.sent = sent
    client.Session = Session
    return client


GUARDIAN = auth(1, "guardian", "guardian@test.com")


def test_default_categories_null_means_receive_everything(setup):
    session = setup.Session()
    notifications.notify(session, 1, "visit_completed", "방문 완료")
    session.commit()
    assert setup.sent == ["visit_completed"]


def test_opting_into_only_messages_blocks_visit_notifications(setup):
    res = setup.patch("/api/v1/users/me/notification-settings", headers=GUARDIAN, json={
        "alimtalk_opt_in": True, "alimtalk_categories": ["message_received"],
    })
    assert res.status_code == 200
    assert res.json()["alimtalk_categories"] == "message_received"

    session = setup.Session()
    notifications.notify(session, 1, "visit_completed", "방문 완료")
    notifications.notify(session, 1, "message_received", "새 메시지")
    session.commit()
    assert setup.sent == ["message_received"]


def test_selecting_all_categories_resets_to_null(setup):
    setup.patch("/api/v1/users/me/notification-settings", headers=GUARDIAN, json={
        "alimtalk_opt_in": True, "alimtalk_categories": ["visit_completed"],
    })
    res = setup.patch("/api/v1/users/me/notification-settings", headers=GUARDIAN, json={
        "alimtalk_opt_in": True, "alimtalk_categories": ["visit_completed", "message_received"],
    })
    assert res.json()["alimtalk_categories"] is None

    get_res = setup.get("/api/v1/users/me/notification-settings", headers=GUARDIAN)
    assert get_res.json()["alimtalk_categories"] is None


def test_master_switch_off_blocks_all_regardless_of_categories(setup):
    setup.patch("/api/v1/users/me/notification-settings", headers=GUARDIAN, json={"alimtalk_opt_in": False})
    session = setup.Session()
    notifications.notify(session, 1, "visit_completed", "방문 완료")
    session.commit()
    assert setup.sent == []
