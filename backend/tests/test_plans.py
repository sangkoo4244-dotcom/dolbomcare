from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models, plans
from app.api import admin, center_directory, records, residents, users
from app.api.users import create_access_token
from app.database import Base, get_db
from app.plans import PARTNER_SLOT_LIMIT, TRIAL_DAYS, center_plan_info


def auth(uid, email, role="center_manager"):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


OPERATOR = auth(1, "ops@eeum.kr")
EXPIRED_MGR = auth(2, "exp@c.kr")
TRIAL_MGR = auth(3, "trial@c.kr")
PARTNER_MGR = auth(4, "partner@c.kr")
EXPIRED_CG = auth(5, "cg@c.kr", "caregiver")
NOW = datetime.utcnow()


class C:  # 센터 흉내
    def __init__(self, plan=None, ends=None):
        self.plan, self.trial_ends_at = plan, ends


def test_trial_is_one_month_and_states_follow_the_plan():
    assert TRIAL_DAYS == 30 and PARTNER_SLOT_LIMIT == 30
    assert center_plan_info(C(None, None))["state"] == "paid"                        # 기존 센터: 제한 없음
    assert center_plan_info(C("paid", NOW + timedelta(days=3)))["state"] == "paid"
    trial = center_plan_info(C("trial", NOW + timedelta(days=10, hours=1)))
    assert (trial["state"], trial["days_left"], trial["read_only"]) == ("trial", 11, False)
    assert center_plan_info(C(None, NOW + timedelta(hours=2)))["days_left"] == 1     # plan이 비어 있어도 체험일이 있으면 체험
    expired = center_plan_info(C("trial", NOW - timedelta(seconds=1)))
    assert (expired["state"], expired["read_only"]) == ("trial_expired", True)
    partner = center_plan_info(C("partner", NOW - timedelta(days=400)))              # 파트너는 날짜와 상관없이 계속
    assert (partner["state"], partner["read_only"]) == ("partner", False)


def test_only_writes_outside_the_allow_list_are_blocked_after_trial():
    expired = C("trial", NOW - timedelta(days=1))
    assert plans.is_write_blocked(expired, "GET", "/api/v1/residents/") is False
    assert plans.is_write_blocked(expired, "POST", "/api/v1/records/create") is True
    assert plans.is_write_blocked(expired, "DELETE", "/api/v1/residents/1") is True
    assert plans.is_write_blocked(expired, "PATCH", "/api/v1/users/me") is False
    assert plans.is_write_blocked(expired, "POST", "/api/v1/notifications/read-all") is False
    assert plans.is_write_blocked(C("partner"), "POST", "/api/v1/records/create") is False


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATFORM_ADMIN_EMAILS", "ops@eeum.kr")
    engine = create_engine(f"sqlite:///{tmp_path / 'plans.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="이음", plan="paid"),
        models.Center(id=2, name="만료센터", plan="trial", trial_ends_at=NOW - timedelta(days=2)),
        models.Center(id=3, name="체험센터", plan="trial", trial_ends_at=NOW + timedelta(days=20)),
        models.Center(id=4, name="파트너센터", plan="partner", partner_since=NOW - timedelta(days=100)),
        models.User(id=1, email="ops@eeum.kr", hashed_password="x", full_name="운영자", role="center_manager", center_id=1),
        models.User(id=2, email="exp@c.kr", hashed_password="x", full_name="만료센터장", role="center_manager", center_id=2),
        models.User(id=3, email="trial@c.kr", hashed_password="x", full_name="체험센터장", role="center_manager", center_id=3),
        models.User(id=4, email="partner@c.kr", hashed_password="x", full_name="파트너센터장", role="center_manager", center_id=4),
        models.User(id=5, email="cg@c.kr", hashed_password="x", full_name="만료요양", role="caregiver", center_id=2),
        models.Resident(id=1, center_id=2, name="이용자", care_grade=3, client_type="일반"),
    ])
    db.commit()
    app = FastAPI()
    for name, mod in (("admin", admin), ("users", users), ("centers", center_directory), ("residents", residents), ("records", records)):
        app.include_router(mod.router, prefix=f"/api/v1/{name}")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def test_expired_trial_center_can_read_but_not_write(env):
    db, client = env
    assert client.get("/api/v1/residents/", headers=EXPIRED_MGR).status_code == 200
    body = {"caregiver_id": 5, "resident_id": 1, "service_type": "basic_care", "notes": "x", "duration_minutes": 60}
    r = client.post("/api/v1/records/create", json=body, headers=EXPIRED_CG)
    assert r.status_code == 402 and "내려받" in r.json()["detail"]
    assert db.query(models.DailyRecord).count() == 0
    assert client.post("/api/v1/residents/import", json={"rows": []}, headers=EXPIRED_MGR).status_code == 402
    # 자기 프로필은 계속 고칠 수 있다
    assert client.patch("/api/v1/users/me", json={"phone": "010-0000-0000"}, headers=EXPIRED_MGR).status_code == 200
    # 체험이 남았거나 파트너인 센터는 그대로 쓴다
    assert client.get("/api/v1/users/me", headers=TRIAL_MGR).json()["center_plan"]["state"] == "trial"
    assert client.get("/api/v1/users/me", headers=PARTNER_MGR).json()["center_plan"]["state"] == "partner"
    assert client.get("/api/v1/users/me", headers=EXPIRED_MGR).json()["center_plan"]["read_only"] is True
    assert client.post("/api/v1/residents/import", json={"rows": []}, headers=PARTNER_MGR).status_code != 402


def test_operator_can_make_and_end_partners_within_the_slot_limit(env):
    db, client = env
    assert client.get("/api/v1/centers/partner-slots").json() == {"limit": 30, "used": 1, "remaining": 29}  # 로그인 없이 볼 수 있다
    assert client.post("/api/v1/admin/centers/3/partner", json={"note": "1호"}, headers=TRIAL_MGR).status_code == 403
    r = client.post("/api/v1/admin/centers/3/partner", json={"note": "오픈 이벤트"}, headers=OPERATOR)
    assert r.status_code == 200 and r.json()["used"] == 2
    db.expire_all()
    c = db.query(models.Center).filter_by(id=3).one()
    assert (c.plan, c.trial_ends_at, c.partner_note) == ("partner", None, "오픈 이벤트") and c.partner_since is not None
    assert client.post("/api/v1/admin/centers/3/partner", json={}, headers=OPERATOR).status_code == 400  # 이미 파트너
    # 자리는 30곳까지만: 이미 2곳이니 28곳 더 지정할 수 있고 그다음은 거절
    for i in range(10, 39):
        db.add(models.Center(id=i, name=f"c{i}", plan="trial", trial_ends_at=NOW + timedelta(days=5)))
    db.commit()
    codes = [client.post(f"/api/v1/admin/centers/{i}/partner", json={}, headers=OPERATOR).status_code for i in range(10, 39)]
    assert codes.count(200) == 28 and codes[-1] == 400
    assert client.get("/api/v1/centers/partner-slots").json()["remaining"] == 0
    # 해제하면 체험 기간으로 돌아가고 자리가 하나 난다
    r = client.post("/api/v1/admin/centers/3/end-partner", json={"days": 30}, headers=OPERATOR)
    assert r.status_code == 200 and r.json()["remaining"] == 1
    db.expire_all()
    assert center_plan_info(db.query(models.Center).filter_by(id=3).one())["state"] == "trial"
    listing = client.get("/api/v1/admin/partners", headers=OPERATOR).json()
    assert listing["used"] == 29 and all(p["center_name"] for p in listing["partners"])


def test_convert_to_paid_ends_the_trial_and_new_centers_get_a_30_day_trial(env):
    db, client = env
    assert client.post("/api/v1/admin/centers/2/convert-to-paid", headers=OPERATOR).status_code == 200
    db.expire_all()
    c = db.query(models.Center).filter_by(id=2).one()
    assert (c.plan, c.trial_ends_at) == ("paid", None)
    assert client.post("/api/v1/residents/import", json={"rows": []}, headers=EXPIRED_MGR).status_code != 402  # 이제 쓰기 가능
    r = client.post("/api/v1/admin/centers", json={"center_name": "새센터", "manager_name": "김센터", "manager_email": "new@c.kr", "manager_password": "password123"}, headers=OPERATOR)
    assert r.status_code == 200
    db.expire_all()
    new = db.query(models.Center).filter_by(name="새센터").one()
    assert new.plan == "trial" and 29 <= (new.trial_ends_at - NOW).days <= 30


def test_partner_centers_can_register_up_to_30_residents_only(env):
    db, client = env
    # 파트너 센터(id=4)에 이용자 99명을 미리 넣고, 100번째까지만 허용
    for i in range(99):
        db.add(models.Resident(center_id=4, name=f"이용자{i}", care_grade=3, client_type="일반"))
    db.commit()
    body = {"center_id": 4, "name": "서른번째", "birth_date": "1940-01-01", "age": 85, "care_grade": 3, "client_type": "일반", "health_status": "stable", "gender": "여"}
    assert client.post("/api/v1/residents/", json=body, headers=PARTNER_MGR).status_code == 200
    r = client.post("/api/v1/residents/", json={**body, "name": "서른한번째", "birth_date": "1941-01-01"}, headers=PARTNER_MGR)
    assert r.status_code == 400 and "100명" in r.json()["detail"]
    assert db.query(models.Resident).filter_by(center_id=4).count() == 100
    # 엑셀 일괄 등록도 상한 안에서만 (검사만 하는 dry_run은 통과해도 저장은 거절)
    rows = [{"이름": "일괄1", "성별": "여", "생년월일": "1942-02-02", "요양등급": "3", "소득분류": ""}]
    saved = client.post("/api/v1/residents/import", json={"rows": rows, "dry_run": False}, headers=PARTNER_MGR)
    assert saved.status_code == 400 and db.query(models.Resident).filter_by(center_id=4).count() == 100
    # 파트너가 아닌 센터는 상한이 없다
    assert plans.resident_limit(db.query(models.Center).filter_by(id=3).one()) is None
    # 상태 응답에 사용량이 담긴다(사이드바 표시용)
    plan = client.get("/api/v1/users/me", headers=PARTNER_MGR).json()["center_plan"]
    assert (plan["state"], plan["resident_limit"], plan["resident_count"]) == ("partner", 100, 100)
    assert "resident_limit" not in client.get("/api/v1/users/me", headers=TRIAL_MGR).json()["center_plan"]


def test_operator_sees_the_service_mix_and_resident_counts_of_partners(env):
    db, client = env
    db.query(models.Center).filter_by(id=4).update({"service_types": "방문요양,방문목욕"})
    db.add(models.Center(id=7, name="주야간파트너", plan="partner", partner_since=NOW, service_types="주야간보호"))
    db.add(models.Resident(center_id=7, name="가", care_grade=3, client_type="일반"))
    db.commit()
    data = client.get("/api/v1/admin/partners", headers=OPERATOR).json()
    assert data["resident_limit"] == 100 and data["service_mix"] == {"방문요양": 1, "방문목욕": 1, "주야간보호": 1}
    by_name = {p["center_name"]: p for p in data["partners"]}
    assert by_name["주야간파트너"]["resident_count"] == 1 and by_name["파트너센터"]["services"] == ["방문요양", "방문목욕"]


def test_partner_and_trial_centers_cannot_use_any_operator_console_api(env):
    _, client = env
    for headers in (PARTNER_MGR, TRIAL_MGR, EXPIRED_MGR, EXPIRED_CG):
        assert client.get("/api/v1/admin/is-admin", headers=headers).status_code == 403
        assert client.get("/api/v1/admin/partners", headers=headers).status_code == 403
        assert client.get("/api/v1/admin/demo/status", headers=headers).status_code == 403
        assert client.post("/api/v1/admin/demo/reset", headers=headers).status_code == 403
        assert client.post("/api/v1/admin/centers/3/partner", json={}, headers=headers).status_code == 403
        assert client.post("/api/v1/admin/centers/4/end-partner", json={}, headers=headers).status_code == 403
        assert client.post("/api/v1/admin/centers/2/convert-to-paid", headers=headers).status_code == 403
    assert client.get("/api/v1/admin/is-admin", headers=OPERATOR).status_code == 200


def test_trial_ending_notices_are_sent_once_per_stage_to_the_manager_only(env):
    db, client = env

    def notices(user_id):
        db.expire_all()
        return sorted(n.kind for n in db.query(models.Notification).filter_by(user_id=user_id).all())

    # 체험이 20일 남았으면 아직 안내하지 않는다
    client.get("/api/v1/users/me", headers=TRIAL_MGR)
    assert notices(3) == []
    # 7일 이내가 되면 한 번만(화면을 몇 번 열어도 중복 없음)
    db.query(models.Center).filter_by(id=3).update({"trial_ends_at": NOW + timedelta(days=5, hours=1)})
    db.commit()
    for _ in range(3):
        client.get("/api/v1/users/me", headers=TRIAL_MGR)
    assert notices(3) == ["trial_d7"]
    # 하루 전, 그리고 끝난 뒤에는 각각 한 번씩
    db.query(models.Center).filter_by(id=3).update({"trial_ends_at": NOW + timedelta(hours=10)})
    db.commit()
    client.get("/api/v1/users/me", headers=TRIAL_MGR)
    client.get("/api/v1/users/me", headers=TRIAL_MGR)
    assert notices(3) == ["trial_d1", "trial_d7"]
    # 이미 끝난 센터: 센터장에게만 '끝났다'는 안내가 가고, 요양보호사에게는 가지 않는다
    client.get("/api/v1/users/me", headers=EXPIRED_MGR)
    client.get("/api/v1/users/me", headers=EXPIRED_CG)
    assert notices(2) == ["trial_expired"] and notices(5) == []
    # 파트너·정식 센터는 안내가 없다
    client.get("/api/v1/users/me", headers=PARTNER_MGR)
    assert notices(4) == []
