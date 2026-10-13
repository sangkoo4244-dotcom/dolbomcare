from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import care_plans
from app.api.users import create_access_token
from app.database import Base, get_db


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
    db.add(models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1))
    db.add(models.Resident(id=1, center_id=1, name="김이용"))
    db.add(models.Resident(id=2, center_id=1, name="이이용"))
    db.add(models.Resident(id=3, center_id=2, name="타센터"))
    db.commit()
    app = FastAPI()
    app.include_router(care_plans.router, prefix="/api/v1/care-plans")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def body(**kw):
    base = {"resident_id": 1, "plan_type": "regular", "written_date": "2026-10-05", "service_start_date": "2026-10-10",
            "goals": "낙상 없이 일상생활 유지", "needs": "보행 보조와 식사 준비", "details": "신체활동 지원, 식사 준비, 청소",
            "frequency": "주 5회", "duration_minutes": 180, "opinion": "허리 통증으로 보행 시 부축이 필요함"}
    base.update(kw)
    return base


def add_assessments(db, when):
    db.add(models.NeedsAssessment(resident_id=1, assessed_by=1, assessed_date=when))
    for t in ("fall_risk", "pressure_sore_risk", "cognitive_function"):
        db.add(models.RiskAssessment(resident_id=1, assessment_type=t, assessed_by=1, assessed_date=when))
    db.commit()


def test_create_attaches_assessments_done_before_plan(env):
    db, client = env
    add_assessments(db, datetime(2026, 10, 1))
    res = client.post("/api/v1/care-plans", json=body(), headers=MANAGER).json()["data"]
    assert all(res["assessments"].values())
    assert res["plan_type_label"] == "신규·정기"
    # 평가는 갖췄지만 서명·통보가 아직이므로 이 두 가지만 지적된다
    assert [i for i in res["issues"] if "평가" in i] == []
    assert any("확인서명" in i for i in res["issues"]) and any("공단 통보일" in i for i in res["issues"])


def test_assessments_done_after_plan_date_do_not_count(env):
    db, client = env
    add_assessments(db, datetime(2026, 10, 8))   # 계획서(10/5)보다 늦게 실시
    res = client.post("/api/v1/care-plans", json=body(), headers=MANAGER).json()["data"]
    assert not any(res["assessments"].values())
    assert sum("평가" in i or "욕구사정" in i for i in res["issues"]) == 4


def test_required_fields_and_change_rules(env):
    _, client = env
    assert client.post("/api/v1/care-plans", json=body(opinion=" "), headers=MANAGER).status_code == 400
    assert client.post("/api/v1/care-plans", json=body(plan_type="change", change_reason="x"), headers=MANAGER).status_code == 400  # 기존 계획서 없음
    client.post("/api/v1/care-plans", json=body(), headers=MANAGER)
    assert client.post("/api/v1/care-plans", json=body(plan_type="change"), headers=MANAGER).status_code == 400  # 변경 사유 없음
    ok = client.post("/api/v1/care-plans", json=body(plan_type="change", change_reason="기능상태 악화로 방문 시간 연장", written_date="2026-10-12"), headers=MANAGER)
    assert ok.status_code == 200 and ok.json()["data"]["parent_id"] is not None


def test_progress_and_timing_issues(env):
    db, client = env
    add_assessments(db, datetime(2026, 10, 1))
    pid = client.post("/api/v1/care-plans", json=body(), headers=MANAGER).json()["data"]["id"]
    res = client.put(f"/api/v1/care-plans/{pid}/progress", json={"guardian_signed_date": "2026-10-06", "guardian_signer": "김영희(딸)", "nhis_notified_date": "2026-10-08"}, headers=MANAGER).json()["data"]
    assert res["issues"] == []
    late = client.put(f"/api/v1/care-plans/{pid}/progress", json={"nhis_notified_date": "2026-10-11"}, headers=MANAGER).json()["data"]
    assert any("늦었습니다" in i for i in late["issues"])


def test_status_flags_residents_without_plan_this_year(env):
    db, client = env
    client.post("/api/v1/care-plans", json=body(), headers=MANAGER)
    st = care_plans.center_plan_status(db, 1, date(2026, 10, 13))
    by = {r["resident_name"]: r for r in st["residents"]}
    assert by["김이용"]["has_plan_this_year"] and not by["이이용"]["has_plan_this_year"]
    assert st["no_plan_this_year"] == 1 and "타센터" not in by
    # 작년 계획서만 있으면 올해는 없는 것으로 본다
    db.add(models.CarePlan(center_id=1, resident_id=2, written_date=date(2025, 11, 1), author_id=1, goals="g", needs="n", details="d", frequency="주 3회", opinion="o"))
    db.commit()
    assert not {r["resident_name"]: r for r in care_plans.center_plan_status(db, 1, date(2026, 10, 13))["residents"]}["이이용"]["has_plan_this_year"]


def test_tenant_isolation_and_roles(env):
    _, client = env
    assert client.post("/api/v1/care-plans", json=body(resident_id=3), headers=MANAGER).status_code == 404
    assert client.get("/api/v1/care-plans?resident_id=3", headers=MANAGER).status_code == 404
    assert client.get("/api/v1/care-plans?resident_id=1", headers=CAREGIVER).status_code == 403


def test_cannot_delete_plan_that_has_change_plan(env):
    _, client = env
    first = client.post("/api/v1/care-plans", json=body(), headers=MANAGER).json()["data"]["id"]
    client.post("/api/v1/care-plans", json=body(plan_type="change", change_reason="욕구 변화", written_date="2026-10-12"), headers=MANAGER)
    assert client.delete(f"/api/v1/care-plans/{first}", headers=MANAGER).status_code == 400
