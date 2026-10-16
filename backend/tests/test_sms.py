"""보호자 문자: 설정이 없으면 보내지 않고, 전화번호가 없으면 건너뛰고, 한도가 없으면 막고, 모든 시도를 기록한다."""
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.alimtalk_billing import FREE_QUOTA_PER_MONTH
from app.api import sms
from app.api.users import create_access_token
from app.database import Base, get_db

MANAGER = {"Authorization": "Bearer " + create_access_token({"sub": "m@test.com", "uid": 1, "role": "center_manager"}, timedelta(hours=1))}
CAREGIVER = {"Authorization": "Bearer " + create_access_token({"sub": "c@test.com", "uid": 2, "role": "caregiver"}, timedelta(hours=1))}


@pytest.fixture
def env(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(sms, "sms_configured", lambda: True)
    monkeypatch.setattr(sms, "send_sms", lambda phone, text: (sent.append((phone, text)) or True))
    engine = create_engine(f"sqlite:///{tmp_path / 'sms.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1),
        models.Resident(id=1, center_id=1, name="이용자1", guardian_phone="010-1111-1111"),
        models.Resident(id=2, center_id=1, name="이용자2", guardian_phone=None),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(sms.router, prefix="/api/v1/sms")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    return TestClient(app), sent, Session


def test_sends_to_guardians_with_a_phone_and_logs_every_attempt(env):
    client, sent, Session = env
    body = {"resident_ids": [1, 2], "text": "이번 달 방문 안내입니다."}
    data = client.post("/api/v1/sms/send", json=body, headers=MANAGER).json()["data"]
    assert data == {"sent": 1, "failed": 0, "no_phone": 1, "blocked": 0}
    assert sent == [("010-1111-1111", "이번 달 방문 안내입니다.")]
    db = Session()
    assert db.query(models.SmsLog).count() == 2  # 번호 없는 이용자도 기록에 남긴다
    db.close()
    history = client.get("/api/v1/sms/history", headers=MANAGER).json()["data"]
    assert len(history) == 2 and history[0]["text"] == "이번 달 방문 안내입니다."


def test_nothing_is_sent_or_counted_when_sms_is_not_set_up(env, monkeypatch):
    client, sent, Session = env
    monkeypatch.setattr(sms, "sms_configured", lambda: False)
    assert client.post("/api/v1/sms/send", json={"resident_ids": [1], "text": "안내"}, headers=MANAGER).status_code == 503
    assert sent == []


def test_caregiver_cannot_send_and_quota_blocks_extra_messages(env):
    client, sent, Session = env
    assert client.post("/api/v1/sms/send", json={"resident_ids": [1], "text": "안내"}, headers=CAREGIVER).status_code == 403
    db = Session()
    db.add(models.AlimtalkUsage(center_id=1, year_month=__import__("app.alimtalk_billing", fromlist=["x"])._current_year_month(), free_sent=FREE_QUOTA_PER_MONTH))
    db.commit()
    db.close()
    data = client.post("/api/v1/sms/send", json={"resident_ids": [1], "text": "안내"}, headers=MANAGER).json()["data"]
    assert data["blocked"] == 1 and sent == []
