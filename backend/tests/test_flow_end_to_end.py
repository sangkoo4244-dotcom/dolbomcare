"""방문 기록 → 청구 → 제출 → 승인 → 급여 확정까지, 화면마다 금액이 같은지를 손으로 계산한 값과 대조한다."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import billing, records, salary, statements, value_report
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, email, role):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "m@a.kr", "center_manager")
CG = auth(2, "c@a.kr", "caregiver")
YM = "2026-10"


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'flow.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A센터"),
        models.User(id=1, email="m@a.kr", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@a.kr", full_name="요양사", role="caregiver", center_id=1, wage_ratio=70),
        models.Resident(id=1, center_id=1, name="일반1등급", age=80, health_status="stable", care_grade=1, client_type="일반"),
        models.Resident(id=2, center_id=1, name="차상위3등급", age=80, health_status="stable", care_grade=3, client_type="차상위계층"),
        models.Resident(id=3, center_id=1, name="의료급여인지", age=80, health_status="stable", care_grade=None, client_type="의료급여"),
    ])
    db.commit()
    app = FastAPI()
    for module, prefix in ((billing, "billing"), (records, "records"), (salary, "salary"), (statements, "statements"), (value_report, "value-report")):
        app.include_router(module.router, prefix=f"/api/v1/{prefix}")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def record(client, resident_id, minutes, when):
    r = client.post("/api/v1/records/create", headers=CG, json={
        "caregiver_id": 2, "resident_id": resident_id, "service_type": "basic_care", "duration_minutes": minutes,
        "recorded_date": when,
    })
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_three_visits_show_the_same_money_everywhere(env):
    db, client = env
    # a) 수요일 낮 60분 일반 1등급: 25,320원, 본인부담 15%=3,798→3,790, 공단 21,530, 중증 가산 2,000(별도 지급)
    a = record(client, 1, 60, "2026-10-14T10:00:00")
    # b) 수요일 22:30 시작 120분 차상위 3등급: 야간 30% 가산 전 구간(22:30~00:30) → 43,430×1.3=56,460(가산 13,029→13,030)
    b = record(client, 2, 120, "2026-10-14T22:30:00")
    # c) 일요일 30분 의료급여 인지지원: 17,450×1.3=22,690(가산 5,235→5,240), 본인부담 0
    c = record(client, 3, 30, "2026-10-11T11:00:00")

    rows = {r.id: r for r in db.query(models.BillingRecord).all()}
    got = {k: (rows[v["billing_id"]].total_cost, rows[v["billing_id"]].amount, rows[v["billing_id"]].extra_amount or 0) for k, v in (("a", a), ("b", b), ("c", c))}
    assert got["a"] == (25320, 25320 - 3798, 2000)
    assert got["b"] == (56460, 56460 - 3388, 0)
    assert got["c"] == (22690, 22690, 0)

    # 요양사가 제출 → 센터장이 승인
    for v in (a, b, c):
        assert client.post(f"/api/v1/billing/{v['billing_id']}/submit", headers=CG, json={"user_id": 2, "user_role": "caregiver"}).status_code == 200
    # 승인 전에는 매출·급여 어디에도 잡히지 않는다
    assert client.get(f"/api/v1/billing/monthly/{YM}", headers=MANAGER).json()["approved_amount"] == 0
    for v in (a, b, c):
        assert client.post(f"/api/v1/billing/{v['billing_id']}/approve", headers=MANAGER, json={"user_id": 1, "user_role": "center_manager", "reason": "테스트: 방문 확인 완료"}).status_code == 200

    expected = got["a"][1] + got["b"][1] + got["c"][1]
    monthly = client.get(f"/api/v1/billing/monthly/{YM}", headers=MANAGER).json()
    assert monthly["total_records"] == 3 and monthly["approved_amount"] == expected

    salary_month = client.get(f"/api/v1/salary/monthly/{YM}", params={"caregiver_id": 2}, headers=CG).json()
    assert salary_month["total_amount"] == expected and salary_month["total_records"] == 3

    # 급여 확정: 청구액의 70%가 기준, 확정 뒤 같은 달은 다시 확정할 수 없다
    r = client.post("/api/v1/statements/confirm", headers=MANAGER, json={"caregiver_id": 2, "year_month": YM})
    assert r.status_code == 200, r.text
    st = r.json()["statement"]
    assert st["billing_total"] == expected and st["wage_base"] == round(expected * 0.7)
    assert st["net"] == st["wage_base"] - st["total_deduction"]
    assert client.post("/api/v1/statements/confirm", headers=MANAGER, json={"caregiver_id": 2, "year_month": YM}).status_code == 400
    mine = client.get("/api/v1/statements/mine", headers=CG).json()
    assert (mine["statements"] if isinstance(mine, dict) else mine)[0]["net"] == st["net"]
