"""급여 지급 대장: 확정된 명세서를 직원별로 모으고 합계를 내며, 미확정 직원은 따로 알려 준다. 센터장만 본다."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import statements
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "m@t.kr")
CAREGIVER = auth(2, "caregiver", "c@t.kr")
OTHER_MANAGER = auth(7, "center_manager", "o@t.kr")


def statement(cid, center, total, net, ym="2026-09"):
    return models.SalaryStatement(center_id=center, caregiver_id=cid, year_month=ym, billing_total=total, wage_ratio=100,
                                  wage_base=total, income_tax=100, pension=200, health=300, employment=40,
                                  total_deduction=640, net=net, confirmed_at=datetime.now())


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'pl.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A센터"), models.Center(id=2, name="B센터"),
        models.User(id=1, email="m@t.kr", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@t.kr", full_name="가요양사", role="caregiver", center_id=1),
        models.User(id=3, email="d@t.kr", full_name="나요양사", role="caregiver", center_id=1),
        models.User(id=4, email="e@t.kr", full_name="다요양사", role="caregiver", center_id=1),
        models.User(id=7, email="o@t.kr", full_name="타센터장", role="center_manager", center_id=2),
        models.User(id=8, email="x@t.kr", full_name="타센터요양사", role="caregiver", center_id=2),
    ])
    db.add_all([statement(2, 1, 100000, 9000), statement(3, 1, 50000, 4000), statement(8, 2, 999999, 1, "2026-09")])
    db.commit()
    app = FastAPI()
    app.include_router(statements.router, prefix="/api/v1/statements")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_ledger_lists_confirmed_rows_with_totals(env):
    data = env.get("/api/v1/statements/ledger/2026-09", headers=MANAGER).json()["data"]
    assert [r["caregiver_name"] for r in data["rows"]] == ["가요양사", "나요양사"]
    assert data["totals"]["billing_total"] == 150000
    assert data["totals"]["net"] == 13000
    assert data["totals"]["total_deduction"] == 1280


def test_ledger_lists_caregivers_not_yet_confirmed(env):
    data = env.get("/api/v1/statements/ledger/2026-09", headers=MANAGER).json()["data"]
    assert data["unconfirmed"] == ["다요양사"]


def test_other_center_is_excluded_and_empty_month_is_empty(env):
    assert env.get("/api/v1/statements/ledger/2026-09", headers=OTHER_MANAGER).json()["data"]["rows"][0]["caregiver_name"] == "타센터요양사"
    empty = env.get("/api/v1/statements/ledger/2026-08", headers=MANAGER).json()["data"]
    assert empty["rows"] == [] and empty["totals"]["net"] == 0


def test_only_manager_and_valid_month(env):
    assert env.get("/api/v1/statements/ledger/2026-09", headers=CAREGIVER).status_code == 403
    assert env.get("/api/v1/statements/ledger/2026-13", headers=MANAGER).status_code == 400
