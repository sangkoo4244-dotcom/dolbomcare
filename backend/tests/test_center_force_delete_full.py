from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import admin
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


OWNER = auth(1, "center_manager", "owner@eeumlogic.com")


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATFORM_ADMIN_EMAILS", "owner@eeumlogic.com")
    engine = create_engine(f"sqlite:///{tmp_path / 'full.db'}")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _):  # 운영 PostgreSQL처럼 외래키를 강제한다
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    app = FastAPI()
    app.include_router(admin.router, prefix="/api/v1/admin")

    def override_get_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.Session = Session
    return client


def center_rows_left(session, center_id):
    """센터 번호(center_id)를 가진 행이 남아 있는 테이블 이름 목록. 이 목록이 비어야 완전 삭제다."""
    leftover = []
    for table in Base.metadata.sorted_tables:
        if "center_id" not in table.c:
            continue
        count = session.execute(
            table.select().with_only_columns(func.count()).where(table.c.center_id == center_id)
        ).scalar()
        if count:
            leftover.append(table.name)
    return leftover


def test_force_delete_removes_every_table_that_points_at_the_center(env):
    session = env.Session()
    session.add(models.User(id=1, email="owner@eeumlogic.com", full_name="운영자", role="center_manager"))
    session.add(models.Center(id=7, name="전체삭제센터"))
    session.add(models.User(id=70, email="mgr7@test.com", full_name="센터장", role="center_manager", center_id=7))
    session.add(models.User(id=71, email="cg7@test.com", full_name="요양사", role="caregiver", center_id=7))
    session.flush()
    session.add(models.Resident(id=70, center_id=7, name="이용자"))
    session.flush()
    session.add_all([
        models.CarePlan(center_id=7, resident_id=70, author_id=70, written_date=date(2026, 10, 1)),
        models.IncidentReport(
            center_id=7, resident_id=70, reporter_id=70, occurred_date=date(2026, 10, 1),
            incident_type="fall", description="넘어짐", action_taken="확인",
        ),
        models.Equipment(center_id=7, name="휠체어"),
        models.LeaveRequest(center_id=7, staff_id=71, leave_date=date(2026, 10, 2), leave_type="annual"),
        models.ResidentLog(center_id=7, resident_id=70, author_id=70, log_date=date(2026, 10, 1), kind="observation", content="관찰"),
    ])
    session.commit()
    assert center_rows_left(session, 7)  # 연결된 자료가 실제로 들어갔는지 먼저 확인
    session.close()

    res = env.request("DELETE", "/api/v1/admin/centers/7/force", headers=OWNER, json={"confirm_name": "전체삭제센터"})
    assert res.status_code == 200, res.text

    session = env.Session()
    assert center_rows_left(session, 7) == []
    assert session.query(models.Center).filter_by(id=7).count() == 0
