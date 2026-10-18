"""보호자 메시지와 알림의 연결: 대화를 열어 읽으면 그 이용자의 메시지 알림도 같이 읽음 처리되어야 한다.
다른 이용자의 알림과 다른 사람의 알림은 건드리지 않는다."""
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import messages, notifications
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MANAGER = auth(1, "center_manager", "m@test.com")
GUARDIAN = auth(5, "guardian", "g@test.com")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'msg.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=5, email="g@test.com", full_name="보호자", role="guardian"),
        models.Resident(id=1, center_id=1, name="김복동", care_grade=2, guardian_id=5),
        models.Resident(id=2, center_id=1, name="김복동2", care_grade=2, guardian_id=5),
    ])
    db.commit()
    db.add_all([
        models.Notification(user_id=1, kind="message_received", message="김복동 보호자 메시지: 안녕하세요", is_read=False),
        models.Notification(user_id=1, kind="message_received", message="김복동2 보호자 메시지: 다른 이용자", is_read=False),
        models.Notification(user_id=1, kind="visit_completed", message="김복동 방문 완료", is_read=False),
        models.Notification(user_id=5, kind="message_received", message="김복동 센터 메시지: 답장", is_read=False),
    ])
    db.commit()
    db.close()
    app = FastAPI()
    app.include_router(messages.router, prefix="/api/v1/messages")
    app.include_router(notifications.router, prefix="/api/v1/notifications")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    client = TestClient(app)
    client.Session = Session
    return client


def unread(env, user_id, kind=None):
    db = env.Session()
    q = db.query(models.Notification).filter(models.Notification.user_id == user_id, models.Notification.is_read == False)  # noqa: E712
    if kind:
        q = q.filter(models.Notification.kind == kind)
    n = q.count()
    db.close()
    return n


def test_opening_a_thread_reads_only_that_residents_message_notifications(env):
    assert unread(env, 1) == 3
    assert env.post("/api/v1/messages/residents/1/read", headers=MANAGER).status_code == 200
    assert unread(env, 1, "message_received") == 1  # 김복동2 메시지는 남는다 (이름 앞부분만 같은 다른 이용자)
    assert unread(env, 1, "visit_completed") == 1  # 방문 알림은 메시지 대화와 무관하다
    assert unread(env, 5) == 1  # 보호자 쪽 알림은 보호자가 읽어야 한다


def test_bell_count_matches_after_thread_is_read(env):
    before = env.get("/api/v1/notifications/mine", headers=MANAGER).json()["unread_count"]
    env.post("/api/v1/messages/residents/1/read", headers=MANAGER)
    after = env.get("/api/v1/notifications/mine", headers=MANAGER).json()["unread_count"]
    assert before - after == 1
