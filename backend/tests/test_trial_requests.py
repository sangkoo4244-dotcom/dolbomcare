from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import admin, center_directory
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, email):
    token = create_access_token({"sub": email, "uid": uid, "role": "center_manager"}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


OPERATOR = auth(1, "ops@eeum.kr")
OTHER = auth(2, "real@center.kr")
FORM = {"center_name": "행복센터", "institution_code": "11111000006", "manager_name": "김센터", "email": "Kim@Center.kr", "phone": "010-1111-2222", "partner_interest": True}
FACILITY = {"code": "11111000006", "name": "행복센터", "address": "서울", "designated_date": "20080625", "type_codes": "A03", "source": "test", "imported_at": None}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATFORM_ADMIN_EMAILS", "ops@eeum.kr")
    center_directory._recent_requests.clear()
    engine = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.FacilityRegistry(**FACILITY),
        models.Center(id=1, name="운영센터"),
        models.User(id=1, email="ops@eeum.kr", full_name="운영자", role="center_manager", center_id=1),
        models.User(id=2, email="real@center.kr", full_name="실센터장", role="center_manager", center_id=1),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(admin.router, prefix="/api/v1/admin")
    app.include_router(center_directory.router, prefix="/api/v1/centers")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def test_submit_is_saved_and_operator_is_notified(env):
    db, client = env
    assert client.post("/api/v1/centers/trial-requests", json=FORM).status_code == 200
    rows = client.get("/api/v1/admin/trial-requests", headers=OPERATOR).json()
    assert rows["new_count"] == 1 and rows["requests"][0]["email"] == "kim@center.kr" and rows["requests"][0]["partner_interest"]
    assert db.query(models.Notification).filter(models.Notification.user_id == 1, models.Notification.kind == "trial_request").count() == 1
    assert db.query(models.Notification).filter(models.Notification.user_id == 2).count() == 0


def test_same_email_within_a_day_is_not_duplicated(env):
    _, client = env
    client.post("/api/v1/centers/trial-requests", json=FORM)
    client.post("/api/v1/centers/trial-requests", json={**FORM, "manager_name": "박담당"})
    rows = client.get("/api/v1/admin/trial-requests", headers=OPERATOR).json()["requests"]
    assert len(rows) == 1 and rows[0]["manager_name"] == "박담당"


def test_bad_input_honeypot_and_rate_limit(env):
    _, client = env
    assert client.post("/api/v1/centers/trial-requests", json={**FORM, "email": "nope"}).status_code == 400
    assert client.post("/api/v1/centers/trial-requests", json={**FORM, "center_name": "  "}).status_code == 400
    assert client.post("/api/v1/centers/trial-requests", json={**FORM, "website": "http://spam"}).status_code == 200
    assert client.get("/api/v1/admin/trial-requests", headers=OPERATOR).json()["requests"] == []
    for i in range(center_directory.REQUEST_LIMIT_PER_HOUR):
        assert client.post("/api/v1/centers/trial-requests", json={**FORM, "email": f"a{i}@x.kr"}).status_code == 200
    assert client.post("/api/v1/centers/trial-requests", json={**FORM, "email": "z@x.kr"}).status_code == 429


def test_only_operator_can_list_or_handle(env):
    _, client = env
    client.post("/api/v1/centers/trial-requests", json=FORM)
    assert client.get("/api/v1/admin/trial-requests", headers=OTHER).status_code == 403
    assert client.post("/api/v1/admin/trial-requests/1/handled", headers=OTHER).status_code == 403
    assert client.post("/api/v1/admin/trial-requests/1/handled", headers=OPERATOR).status_code == 200
    assert client.get("/api/v1/admin/trial-requests", headers=OPERATOR).json()["new_count"] == 0
    assert client.post("/api/v1/admin/trial-requests/99/handled", headers=OPERATOR).status_code == 404
