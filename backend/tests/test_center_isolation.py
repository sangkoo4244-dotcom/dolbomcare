"""다른 센터의 센터장·요양보호사·보호자가 우리 센터 자료를 보거나 바꾸지 못하는지 확인한다."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import certificates, records, residents, salary, schedule, users
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MGR_A = auth(1, "center_manager", "ma@test.com")   # 가 센터
CG_A = auth(2, "caregiver", "ca@test.com")
MGR_B = auth(11, "center_manager", "mb@test.com")  # 나 센터
CG_B = auth(12, "caregiver", "cb@test.com")
GUARD_B = auth(19, "guardian", "gb@test.com")
NOW = datetime.now().replace(microsecond=0)


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'iso.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="가센터", service_types="방문요양"), models.Center(id=2, name="나센터", service_types="방문요양"),
        models.User(id=1, email="ma@test.com", full_name="가센터장", role="center_manager", center_id=1),
        models.User(id=2, email="ca@test.com", full_name="가요양", role="caregiver", center_id=1, phone="010-1111-2222"),
        models.User(id=11, email="mb@test.com", full_name="나센터장", role="center_manager", center_id=2),
        models.User(id=12, email="cb@test.com", full_name="나요양", role="caregiver", center_id=2),
        models.User(id=19, email="gb@test.com", full_name="나보호자", role="guardian", center_id=2),
        models.Resident(id=1, center_id=1, name="가이용자", care_grade=3, client_type="일반", address="서울 어딘가", guardian_phone="010-9999-0000"),
        models.Resident(id=2, center_id=2, name="나이용자", care_grade=3, client_type="일반", guardian_id=19),
    ])
    db.flush()
    db.add(models.Schedule(id=1, caregiver_id=2, resident_id=1, center_id=1, scheduled_date=NOW + timedelta(hours=2), duration_minutes=60, status="proposed"))
    db.add(models.DailyRecord(id=1, resident_id=1, caregiver_id=2, recorded_date=NOW, duration_minutes=60, notes="비밀 기록"))
    db.commit()
    app = FastAPI()
    for name, mod in (("residents", residents), ("users", users), ("schedule", schedule), ("salary", salary), ("records", records), ("certificates", certificates)):
        app.include_router(mod.router, prefix=f"/api/v1/{name}")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def names(body, key):
    rows = body[key] if isinstance(body, dict) else body
    return {r["name"] if "name" in r else r["full_name"] for r in rows}


def test_resident_lists_and_details_stay_inside_the_center(env):
    _, client = env
    mine = client.get("/api/v1/residents/?center_id=1", headers=MGR_B).json()  # 다른 센터 번호를 넣어도 내 센터 것만
    assert names(mine, "residents") == {"나이용자"}
    assert client.get("/api/v1/residents/", headers=MGR_B).json()["total_residents"] == 1
    assert client.get("/api/v1/residents/center/1", headers=MGR_B).status_code == 404
    assert client.get("/api/v1/residents/1", headers=MGR_B).status_code == 404
    assert client.get("/api/v1/residents/1", headers=CG_B).status_code == 404
    assert client.get("/api/v1/residents/1", headers=GUARD_B).status_code == 404  # 보호자도 연결된 이용자만
    assert client.get("/api/v1/residents/2", headers=GUARD_B).status_code == 200
    assert client.get("/api/v1/residents/1", headers=MGR_A).status_code == 200
    assert client.get("/api/v1/residents/", headers=GUARD_B).status_code == 403


def test_other_center_cannot_edit_a_resident(env):
    db, client = env
    assert client.put("/api/v1/residents/1", json={"address": "바꿈"}, headers=MGR_B).status_code == 404
    assert client.patch("/api/v1/residents/1/care-notes", json={"care_notes": "x"}, headers=CG_B).status_code == 404
    assert client.put("/api/v1/residents/1/update-grade?client_type=기초생활보장&care_grade=1", headers=MGR_B).status_code == 404
    db.expire_all()
    r = db.query(models.Resident).filter_by(id=1).one()
    assert (r.address, r.care_grade, r.client_type) == ("서울 어딘가", 3, "일반")


def test_staff_list_and_delete_are_limited_to_my_center(env):
    db, client = env
    listing = client.get("/api/v1/users/?role=caregiver&center_id=1", headers=MGR_B).json()
    assert names(listing, "users") == {"나요양"}  # 가센터 직원(이메일·전화)은 보이지 않는다
    assert client.get("/api/v1/users/", headers=GUARD_B).status_code == 403
    assert client.delete("/api/v1/users/2", headers=MGR_B).status_code == 404
    assert client.delete("/api/v1/users/11", headers=MGR_B).status_code == 400  # 본인 계정
    assert db.query(models.User).filter_by(id=2).count() == 1


def test_schedule_actions_and_lists_are_limited_to_my_center(env):
    db, client = env
    assert client.get("/api/v1/schedule/?center_id=1", headers=MGR_B).json() == [] or client.get("/api/v1/schedule/?center_id=1", headers=MGR_B).json().get("schedules") == []
    assert client.get("/api/v1/schedule/1", headers=MGR_B).status_code == 404
    assert client.get("/api/v1/schedule/1", headers=MGR_A).status_code == 200
    assert client.post("/api/v1/schedule/1/approve", json={"user_id": 11, "user_role": "center_manager"}, headers=MGR_B).status_code == 404
    assert client.post("/api/v1/schedule/1/reject", json={"user_id": 11, "user_role": "center_manager", "reason": "다른 센터"}, headers=MGR_B).status_code == 404
    assert client.delete("/api/v1/schedule/1", headers=MGR_B).status_code == 404
    assert client.get(f"/api/v1/schedule/caregiver-view?caregiver_id=2&year_month={NOW:%Y-%m}", headers=MGR_B).status_code == 403
    db.expire_all()
    assert db.query(models.Schedule).filter_by(id=1).one().status == "proposed"
    assert client.post("/api/v1/schedule/1/approve", json={"user_id": 1, "user_role": "center_manager"}, headers=MGR_A).status_code == 200


def test_schedule_cannot_be_created_across_centers(env):
    _, client = env
    body = {"caregiver_id": 2, "resident_id": 1, "center_id": 1, "scheduled_date": (NOW + timedelta(days=1)).isoformat(), "duration_minutes": 60}
    assert client.post("/api/v1/schedule/", json=body, headers=MGR_B).status_code in (404, 500)


def test_salary_and_records_of_another_centers_staff_are_closed(env):
    _, client = env
    ym = f"{NOW:%Y-%m}"
    assert client.get("/api/v1/salary/current", params={"caregiver_id": 2}, headers=MGR_B).status_code == 403
    assert client.get("/api/v1/salary/history", params={"caregiver_id": 2}, headers=MGR_B).status_code == 403
    assert client.get(f"/api/v1/salary/monthly/{ym}", params={"caregiver_id": 2}, headers=MGR_B).status_code == 403
    assert client.get("/api/v1/salary/contract", params={"caregiver_id": 2}, headers=MGR_B).status_code == 403
    assert client.get("/api/v1/salary/contract", params={"caregiver_id": 2}, headers=GUARD_B).status_code == 403
    assert client.get("/api/v1/records/all", params={"caregiver_id": 2}, headers=MGR_B).status_code == 403
    assert client.get("/api/v1/records/today", params={"caregiver_id": 2}, headers=MGR_B).status_code == 403
    assert client.get("/api/v1/records/recent", params={"caregiver_id": 2}, headers=MGR_B).status_code == 403
    # 같은 센터의 센터장·본인은 그대로 볼 수 있다
    assert client.get("/api/v1/salary/contract", params={"caregiver_id": 2}, headers=MGR_A).status_code == 200
    assert client.get("/api/v1/salary/contract", params={"caregiver_id": 2}, headers=CG_A).status_code == 200
    assert client.get("/api/v1/records/all", params={"caregiver_id": 2}, headers=MGR_A).status_code == 200


def test_manager_of_another_center_cannot_delete_visit_records(env):
    db, client = env
    assert client.delete("/api/v1/records/daily/1", headers=MGR_B).status_code == 404
    assert client.post("/api/v1/records/batch-delete", json={"record_ids": [1], "user_id": 11, "user_role": "center_manager"}, headers=MGR_B).json()["deleted_count"] == 0
    assert db.query(models.DailyRecord).filter_by(id=1).count() == 1
    assert client.delete("/api/v1/records/daily/1", headers=MGR_A).status_code == 200


def test_center_wide_lists_and_statistics_reject_another_centers_id(env):
    _, client = env
    ym = f"{NOW:%Y-%m}"
    for path in ("/api/v1/records/all/center?center_id=1", "/api/v1/records/today/center?center_id=1",
                 f"/api/v1/records/monthly-summary?center_id=1&year_month={ym}", f"/api/v1/records/monthly-statistics?center_id=1&year={NOW.year}&month={NOW.month}",
                 "/api/v1/schedule/proposals?center_id=1"):
        assert client.get(path, headers=MGR_B).status_code in (403, 404), path
        assert client.get(path, headers=GUARD_B).status_code in (403, 404), path
    assert client.get(f"/api/v1/records/monthly-statistics?center_id=1&year={NOW.year}&month={NOW.month}", headers=MGR_A).status_code == 200
    assert client.get("/api/v1/records/all/center?center_id=1", headers=MGR_A).status_code == 200


def test_record_detail_and_certificates_are_scoped(env):
    db, client = env
    db.add(models.StaffCertificate(user_id=2, name="요양보호사 자격증")) if hasattr(models, "StaffCertificate") else None
    db.commit()
    assert client.get("/api/v1/records/daily/1", headers=MGR_B).status_code == 404
    assert client.get("/api/v1/records/daily/1", headers=MGR_A).status_code == 200
    other = client.get("/api/v1/certificates/?center_id=1", headers=MGR_B).json()["certificates"]
    assert other == []
    assert client.get("/api/v1/certificates/?center_id=1", headers=GUARD_B).status_code == 403
    mine = client.get("/api/v1/certificates/?center_id=1", headers=MGR_A).json()["certificates"]
    assert len(mine) == 1
