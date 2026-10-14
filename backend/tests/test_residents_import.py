from datetime import timedelta

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
    engine = create_engine(f"sqlite:///{tmp_path / 'imp.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A"), models.Center(id=2, name="B"),
        models.User(id=1, email="m@e.com", hashed_password="x", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@e.com", hashed_password="x", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=3, email="m2@e.com", hashed_password="x", full_name="타센터장", role="center_manager", center_id=2),
        models.Resident(center_id=1, name="김기존", birth_date=__import__("datetime").date(1940, 5, 1), age=86, health_status="stable", care_grade=3, client_type="일반"),
        models.Resident(center_id=2, name="타센터이용자", birth_date=__import__("datetime").date(1941, 1, 2), age=85, health_status="stable", care_grade=3, client_type="일반"),
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
GOOD = {"이름": "박신규", "성별": "여", "생년월일": "1945.03.02", "요양등급": "3", "소득분류": "", "인정시작": "2026-01-01", "인정종료": "2027-12-31", "주소": "서울시", "보호자": "박자녀", "보호자연락처": "010-1111-2222"}


def post(client, rows, dry=True, headers=MGR):
    return client.post("/api/v1/residents/import", json={"rows": rows, "dry_run": dry}, headers=headers)


def test_dry_run_checks_without_saving_and_save_creates_in_own_center(ctx):
    client, Session = ctx
    r = post(client, [GOOD]).json()
    assert r["status"] == "checked" and r["ok_count"] == 1 and r["saved"] is False
    assert Session().query(models.Resident).filter_by(name="박신규").first() is None
    assert post(client, [GOOD], dry=False).json()["saved"] is True
    saved = Session().query(models.Resident).filter_by(name="박신규").one()
    assert (saved.center_id, saved.care_grade, saved.client_type, saved.age) == (1, 3, "일반", saved.age) and saved.age >= 80
    assert str(saved.birth_date) == "1945-03-02" and saved.guardian_phone == "010-1111-2222"


def test_errors_are_reported_per_row_and_nothing_is_saved(ctx):
    client, Session = ctx
    bad = [GOOD, {**GOOD, "이름": ""}, {**GOOD, "이름": "등급오류", "요양등급": "9"}, {**GOOD, "이름": "김기존", "생년월일": "1940-05-01"},
           {**GOOD, "이름": "날짜오류", "생년월일": "abc"}, {**GOOD}]
    r = post(client, bad, dry=False).json()
    assert r["saved"] is False and r["ok_count"] == 1
    assert {e["row"] for e in r["errors"]} == {3, 4, 5, 6, 7}
    assert Session().query(models.Resident).filter_by(name="박신규").first() is None


def test_same_name_in_other_center_is_allowed_and_caregiver_blocked(ctx):
    client, _ = ctx
    assert post(client, [{**GOOD, "이름": "타센터이용자", "생년월일": "1941-01-02"}]).json()["ok_count"] == 1
    assert post(client, [GOOD], headers=auth(2, "caregiver", "c@e.com")).status_code == 403


def test_create_resident_is_limited_to_own_center(ctx):
    client, _ = ctx
    body = {"name": "신규", "age": 80, "health_status": "stable", "care_grade": 2, "client_type": "일반", "center_id": 2}
    assert client.post("/api/v1/residents/", json=body, headers=MGR).status_code == 403
    assert client.post("/api/v1/residents/", json={**body, "center_id": 1}, headers=MGR).status_code == 200
    # 다른 센터에 같은 이름·생년월일이 있어도 등록할 수 있다
    other = {**body, "center_id": 1, "name": "타센터이용자", "birth_date": "1941-01-02"}
    assert client.post("/api/v1/residents/", json=other, headers=MGR).status_code == 200
