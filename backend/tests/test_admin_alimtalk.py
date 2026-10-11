from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import admin
from app.api import users as users_api
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATFORM_ADMIN_EMAILS", "owner@eeumlogic.com")

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")

    # SQLite는 기본적으로 FK 제약을 강제하지 않는다. 운영 DB(PostgreSQL)는 강제하므로,
    # 여기서도 켜서 테스트가 실제 운영에서 터질 FK 위반을 잡아낼 수 있게 한다.
    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    db = Session()
    db.add(models.Center(id=1, name="테스트센터", alimtalk_balance=1000))
    db.add(models.User(id=1, email="owner@eeumlogic.com", full_name="운영자", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="manager@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.commit()
    db.close()

    app = FastAPI()
    app.include_router(admin.router, prefix="/api/v1/admin")
    app.include_router(users_api.router, prefix="/api/v1/users")

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    test_client.Session = Session
    return test_client


def test_non_admin_manager_is_denied(client):
    headers = auth(2, "center_manager", "manager@test.com")
    assert client.get("/api/v1/admin/alimtalk-overview", headers=headers).status_code == 403
    assert client.post("/api/v1/admin/alimtalk-charge", headers=headers, json={"center_id": 1, "amount": 1000}).status_code == 403
    assert client.get("/api/v1/admin/is-admin", headers=headers).status_code == 403


def test_is_admin_true_for_admin_email(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    res = client.get("/api/v1/admin/is-admin", headers=headers)
    assert res.status_code == 200
    assert res.json()["is_admin"] is True


def test_admin_email_can_view_overview(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    res = client.get("/api/v1/admin/alimtalk-overview", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body[0]["center_name"] == "테스트센터"
    assert body[0]["balance"] == 1000


def test_admin_can_charge_balance(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    res = client.post("/api/v1/admin/alimtalk-charge", headers=headers, json={"center_id": 1, "amount": 5000})
    assert res.status_code == 200
    assert res.json()["balance"] == 6000


def test_charge_rejects_zero_amount(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    res = client.post("/api/v1/admin/alimtalk-charge", headers=headers, json={"center_id": 1, "amount": 0})
    assert res.status_code == 400


def test_non_admin_cannot_create_center(client):
    headers = auth(2, "center_manager", "manager@test.com")
    res = client.post("/api/v1/admin/centers", headers=headers, json={
        "center_name": "새 센터", "manager_name": "김센터장",
        "manager_email": "new@test.com", "manager_password": "password123",
    })
    assert res.status_code == 403


def test_admin_can_create_center_and_manager_can_login(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    res = client.post("/api/v1/admin/centers", headers=headers, json={
        "center_name": "새 센터", "manager_name": "김센터장",
        "manager_email": "new@test.com", "manager_password": "password123",
    })
    assert res.status_code == 200
    body = res.json()
    assert body["center_name"] == "새 센터"
    assert body["manager_email"] == "new@test.com"

    overview = client.get("/api/v1/admin/alimtalk-overview", headers=headers).json()
    assert any(r["center_name"] == "새 센터" for r in overview)


def test_create_center_rejects_duplicate_email(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    res = client.post("/api/v1/admin/centers", headers=headers, json={
        "center_name": "다른 센터", "manager_name": "박센터장",
        "manager_email": "manager@test.com", "manager_password": "password123",
    })
    assert res.status_code == 400


def test_create_center_rejects_short_password(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    res = client.post("/api/v1/admin/centers", headers=headers, json={
        "center_name": "다른 센터", "manager_name": "박센터장",
        "manager_email": "short@test.com", "manager_password": "1234",
    })
    assert res.status_code == 400


def test_create_center_rejects_blank_name(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    res = client.post("/api/v1/admin/centers", headers=headers, json={
        "center_name": "   ", "manager_name": "박센터장",
        "manager_email": "blank@test.com", "manager_password": "password123",
    })
    assert res.status_code == 400


def test_non_admin_cannot_delete_center(client):
    headers = auth(2, "center_manager", "manager@test.com")
    assert client.delete("/api/v1/admin/centers/1", headers=headers).status_code == 403


def test_delete_center_blocked_when_residents_exist(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    created = client.post("/api/v1/admin/centers", headers=headers, json={
        "center_name": "이용자있는센터", "manager_name": "정센터장",
        "manager_email": "has-residents@test.com", "manager_password": "password123",
    }).json()
    center_id = created["center_id"]

    session = client.Session()
    session.add(models.Resident(center_id=center_id, name="김어르신"))
    session.commit()
    session.close()

    res = client.delete(f"/api/v1/admin/centers/{center_id}", headers=headers)
    assert res.status_code == 400
    assert "이용자" in res.json()["detail"]


def test_delete_center_blocked_when_extra_staff_exists(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    # 테스트센터(id=1)는 fixture에서 이미 직원 2명(운영자 본인 + 센터장)이 속해 있다
    res = client.delete("/api/v1/admin/centers/1", headers=headers)
    assert res.status_code == 400
    assert "직원" in res.json()["detail"]


def test_delete_empty_center_succeeds_and_manager_cannot_login(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    created = client.post("/api/v1/admin/centers", headers=headers, json={
        "center_name": "삭제될센터", "manager_name": "임시센터장",
        "manager_email": "to-delete@test.com", "manager_password": "password123",
    }).json()
    center_id = created["center_id"]

    overview_before = client.get("/api/v1/admin/alimtalk-overview", headers=headers).json()
    assert any(r["center_id"] == center_id for r in overview_before)

    res = client.delete(f"/api/v1/admin/centers/{center_id}", headers=headers)
    assert res.status_code == 200

    overview_after = client.get("/api/v1/admin/alimtalk-overview", headers=headers).json()
    assert not any(r["center_id"] == center_id for r in overview_after)

    login = client.post("/api/v1/users/login", json={"email": "to-delete@test.com", "password": "password123"})
    assert login.status_code in (401, 404)


def test_non_admin_cannot_force_delete(client):
    headers = auth(2, "center_manager", "manager@test.com")
    res = client.request("DELETE", "/api/v1/admin/centers/1/force", headers=headers, json={"confirm_name": "테스트센터"})
    assert res.status_code == 403


def test_force_delete_requires_exact_name_match(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    res = client.request("DELETE", "/api/v1/admin/centers/1/force", headers=headers, json={"confirm_name": "오타난이름"})
    assert res.status_code == 400
    assert "일치" in res.json()["detail"]


def test_normal_delete_still_blocked_for_center_with_residents(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    created = client.post("/api/v1/admin/centers", headers=headers, json={
        "center_name": "강제삭제대상", "manager_name": "황센터장",
        "manager_email": "force-target@test.com", "manager_password": "password123",
    }).json()
    center_id = created["center_id"]

    session = client.Session()
    session.add(models.Resident(center_id=center_id, name="이어르신"))
    session.commit()
    session.close()

    res = client.delete(f"/api/v1/admin/centers/{center_id}", headers=headers)
    assert res.status_code == 400


def test_force_delete_removes_center_with_full_data(client):
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    created = client.post("/api/v1/admin/centers", headers=headers, json={
        "center_name": "강제삭제대상2", "manager_name": "황센터장",
        "manager_email": "force-target2@test.com", "manager_password": "password123",
    }).json()
    center_id = created["center_id"]

    session = client.Session()
    manager = session.query(models.User).filter(models.User.email == "force-target2@test.com").first()
    caregiver = models.User(
        email="force-caregiver@test.com", hashed_password="x", full_name="요양사",
        role="caregiver", center_id=center_id, is_active=True,
    )
    session.add(caregiver)
    session.flush()

    resident = models.Resident(center_id=center_id, name="박어르신")
    session.add(resident)
    session.flush()

    daily = models.DailyRecord(resident_id=resident.id, caregiver_id=caregiver.id, recorded_date=None)
    session.add(daily)
    session.flush()

    session.add(models.BillingRecord(
        daily_record_id=daily.id, caregiver_id=caregiver.id, resident_id=resident.id,
        center_id=center_id, amount=10000,
    ))
    session.add(models.Notification(user_id=caregiver.id, kind="visit_completed", message="방문 완료"))
    session.add(models.GuardianInvite(
        code="FORCEDEL1", resident_id=resident.id, center_id=center_id,
        expires_at=datetime.utcnow() + timedelta(days=7),
    ))
    session.commit()
    session.close()

    # 데이터가 있으니 일반 삭제는 거부된다
    assert client.delete(f"/api/v1/admin/centers/{center_id}", headers=headers).status_code == 400

    # 강제 삭제는 성공한다
    res = client.request("DELETE", f"/api/v1/admin/centers/{center_id}/force", headers=headers, json={"confirm_name": "강제삭제대상2"})
    assert res.status_code == 200

    overview = client.get("/api/v1/admin/alimtalk-overview", headers=headers).json()
    assert not any(r["center_id"] == center_id for r in overview)

    login = client.post("/api/v1/users/login", json={"email": "force-target2@test.com", "password": "password123"})
    assert login.status_code in (401, 404)


def test_force_delete_works_when_center_manager_id_is_set(client):
    """데모 체험 센터(seed_demo.py)는 Center.manager_id를 센터장 User로 설정해둔다.
    FK를 먼저 끊지 않고 그 User를 지우면 PostgreSQL에서 위반으로 실패하던 버그의 회귀 테스트."""
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    created = client.post("/api/v1/admin/centers", headers=headers, json={
        "center_name": "매니저아이디센터", "manager_name": "데모센터장",
        "manager_email": "manager-id-test@test.com", "manager_password": "password123",
    }).json()
    center_id = created["center_id"]

    session = client.Session()
    manager = session.query(models.User).filter(models.User.email == "manager-id-test@test.com").first()
    center = session.query(models.Center).filter(models.Center.id == center_id).first()
    center.manager_id = manager.id
    session.add(models.Resident(center_id=center_id, name="데모어르신"))
    session.commit()
    session.close()

    res = client.request(
        "DELETE", f"/api/v1/admin/centers/{center_id}/force",
        headers=headers, json={"confirm_name": "매니저아이디센터"},
    )
    assert res.status_code == 200

    overview = client.get("/api/v1/admin/alimtalk-overview", headers=headers).json()
    assert not any(r["center_id"] == center_id for r in overview)


def test_force_delete_removes_guardian_exclusive_to_center(client):
    """seed_demo.py처럼 guardian User는 center_id가 없고 Resident.guardian_id로만 연결된다.
    이걸 놓치면 센터는 지워져도 보호자 계정이 유령으로 남아 같은 이메일을 다시 못 쓰게 되는
    버그(실제로 로컬에서 seed_demo.py 재실행 시 UNIQUE constraint 위반으로 재현됨)의 회귀 테스트."""
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    created = client.post("/api/v1/admin/centers", headers=headers, json={
        "center_name": "보호자있는센터", "manager_name": "보호자센터장",
        "manager_email": "guardian-center@test.com", "manager_password": "password123",
    }).json()
    center_id = created["center_id"]

    session = client.Session()
    guardian = models.User(
        email="exclusive-guardian@test.com", hashed_password="x", full_name="보호자",
        role="guardian", center_id=None, is_active=True,
    )
    session.add(guardian)
    session.flush()
    session.add(models.Resident(center_id=center_id, name="연결된어르신", guardian_id=guardian.id))
    session.commit()
    session.close()

    res = client.request(
        "DELETE", f"/api/v1/admin/centers/{center_id}/force",
        headers=headers, json={"confirm_name": "보호자있는센터"},
    )
    assert res.status_code == 200

    session = client.Session()
    assert session.query(models.User).filter(models.User.email == "exclusive-guardian@test.com").first() is None
    session.close()


def test_force_delete_keeps_guardian_shared_with_other_center(client):
    """보호자가 다른 센터의 이용자와도 연결돼 있으면, 그 센터를 강제 삭제해도 보호자 계정은
    지우지 않는다 (다른 센터에서 여전히 필요한 계정이므로)."""
    headers = auth(1, "center_manager", "owner@eeumlogic.com")
    created = client.post("/api/v1/admin/centers", headers=headers, json={
        "center_name": "공유보호자센터", "manager_name": "공유센터장",
        "manager_email": "shared-guardian-center@test.com", "manager_password": "password123",
    }).json()
    center_id = created["center_id"]

    session = client.Session()
    guardian = models.User(
        email="shared-guardian@test.com", hashed_password="x", full_name="보호자",
        role="guardian", center_id=None, is_active=True,
    )
    session.add(guardian)
    session.flush()
    # 삭제할 센터(center_id)의 이용자 + 다른 센터(id=1, 기존 테스트센터)의 이용자 둘 다 연결
    session.add(models.Resident(center_id=center_id, name="삭제될어르신", guardian_id=guardian.id))
    session.add(models.Resident(center_id=1, name="남아있을어르신", guardian_id=guardian.id))
    session.commit()
    guardian_id = guardian.id
    session.close()

    res = client.request(
        "DELETE", f"/api/v1/admin/centers/{center_id}/force",
        headers=headers, json={"confirm_name": "공유보호자센터"},
    )
    assert res.status_code == 200

    session = client.Session()
    assert session.query(models.User).filter(models.User.id == guardian_id).first() is not None
    session.close()
