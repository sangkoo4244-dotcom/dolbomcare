from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import trainings as tr
from app.api.users import create_access_token
from app.database import Base, get_db

TODAY = date(2026, 10, 13)


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@test.com")
CAREGIVER = auth(2, "caregiver", "c@test.com")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(models.Center(id=1, name="센터"))
    db.add(models.Center(id=2, name="다른센터"))
    db.add(models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1, hire_date=date(2024, 1, 1)))
    db.add(models.User(id=2, email="c@test.com", full_name="요양사A", role="caregiver", center_id=1, hire_date=date(2025, 1, 1)))
    db.add(models.User(id=3, email="n@test.com", full_name="신규B", role="caregiver", center_id=1, hire_date=date(2026, 10, 1)))
    db.add(models.User(id=4, email="x@test.com", full_name="타센터직원", role="caregiver", center_id=2, hire_date=date(2025, 1, 1)))
    db.add(models.User(id=5, email="o@test.com", full_name="퇴사자", role="caregiver", center_id=1, employment_status="inactive", hire_date=date(2024, 1, 1)))
    db.add(models.Resident(id=1, center_id=1, name="김이용"))
    db.add(models.Resident(id=2, center_id=2, name="타센터"))
    db.commit()
    app = FastAPI()
    app.include_router(tr.router, prefix="/api/v1/trainings")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def session_body(**kw):
    base = {"topic": "operating_rules", "session_date": "2026-10-05", "method": "self", "instructor": "센터장",
            "content": "운영규정 11개 항목 중 이용계약·직원 복지 규정 설명", "attendee_ids": [1, 2], "signed_ids": [1]}
    base.update(kw)
    return base


def test_create_session_and_validation(env):
    _, client = env
    ok = client.post("/api/v1/trainings/sessions", json=session_body(), headers=MANAGER)
    assert ok.status_code == 200
    att = {a["name"]: a["signed"] for a in ok.json()["data"]["attendees"]}
    assert att == {"센터장": True, "요양사A": False}
    for bad in (session_body(topic="x"), session_body(method="sms"), session_body(instructor=" "), session_body(content="짧"),
                session_body(attendee_ids=[]), session_body(attendee_ids=[1, 4])):  # 4번은 다른 센터 직원
        assert client.post("/api/v1/trainings/sessions", json=bad, headers=MANAGER).status_code == 400


def test_period_by_cadence():
    assert tr.period_of("operating_rules", TODAY) == (date(2026, 1, 1), date(2026, 12, 31))
    assert tr.period_of("elder_rights", TODAY) == (date(2026, 7, 1), date(2026, 12, 31))
    assert tr.period_of("elder_rights", date(2026, 3, 1)) == (date(2026, 1, 1), date(2026, 6, 30))


def test_training_status_lists_missing_staff_and_ignores_inactive_and_other_center(env):
    db, client = env
    client.post("/api/v1/trainings/sessions", json=session_body(), headers=MANAGER)
    st = tr.training_status(db, 1, TODAY)
    rules = next(t for t in st["topics"] if t["topic"] == "operating_rules")
    assert [m["name"] for m in rules["missing"]] == ["신규B"]          # 센터장·요양사A는 교육받음, 퇴사자·타센터는 제외
    rights = next(t for t in st["topics"] if t["topic"] == "elder_rights")
    assert {m["name"] for m in rights["missing"]} == {"센터장", "요양사A", "신규B"}
    assert rules["done_count"] == 2 and rules["staff_total"] == 3


def test_new_staff_must_be_trained_within_7_days(env):
    db, client = env
    # 신규B는 10/1 입사: 7일 이내(10/8까지) 교육이 없으면 기한 초과 (오늘 10/13)
    st = tr.training_status(db, 1, TODAY)
    assert {(n["name"], n["topic"], n["state"]) for n in st["new_staff"]} == {("신규B", "operating_rules", "overdue"), ("신규B", "care_guidelines", "overdue")}
    client.post("/api/v1/trainings/sessions", json=session_body(session_date="2026-10-05", attendee_ids=[1, 2, 3]), headers=MANAGER)
    st = tr.training_status(db, 1, TODAY)
    assert {(n["topic"]) for n in st["new_staff"]} == {"care_guidelines"}       # 운영규정은 기한 내 이수
    assert st["new_staff_overdue"] == 1


def notice_body(**kw):
    base = {"resident_id": 1, "notice_type": "staff_respect", "notice_date": "2026-10-05", "method": "sms", "recipient": "김영희(딸)"}
    base.update(kw)
    return base


def test_notice_rules(env):
    _, client = env
    url = "/api/v1/trainings/notices"
    assert client.post(url, json=notice_body(), headers=MANAGER).status_code == 200                      # 비대면 문자 안내는 인정
    assert client.post(url, json=notice_body(notice_type="service_scope", method="mail"), headers=MANAGER).status_code == 400  # 대면만 인정
    assert client.post(url, json=notice_body(notice_type="service_scope", method="visit"), headers=MANAGER).status_code == 200
    assert client.post(url, json=notice_body(notice_type="rights_guide", method="visit", items=["fall"]), headers=MANAGER).status_code == 400  # 8가지 모두 필요
    all8 = list(tr.RIGHTS_GUIDE_ITEMS)
    assert client.post(url, json=notice_body(notice_type="rights_guide", method="visit", items=all8), headers=MANAGER).status_code == 200
    assert client.post(url, json=notice_body(recipient=" "), headers=MANAGER).status_code == 400
    assert client.post(url, json=notice_body(resident_id=2), headers=MANAGER).status_code == 404


def test_notice_status(env):
    db, client = env
    st = tr.notice_status(db, 1, TODAY)
    assert st["residents_missing"] == 1 and len(st["residents"][0]["missing"]) == 3
    client.post("/api/v1/trainings/notices", json=notice_body(), headers=MANAGER)
    st = tr.notice_status(db, 1, TODAY)
    assert {m["type"] for m in st["residents"][0]["missing"]} == {"rights_guide", "service_scope"}


def test_roles(env):
    _, client = env
    assert client.get("/api/v1/trainings/status", headers=CAREGIVER).status_code == 403
    assert client.get("/api/v1/trainings/notices", headers=CAREGIVER).status_code == 403
    assert client.get("/api/v1/trainings/options", headers=MANAGER).status_code == 200
