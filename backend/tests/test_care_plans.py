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


# ---------------- 보호자 전자서명 / 요양보호사 확인 ----------------

GUARDIAN = auth(9, "guardian", "g@test.com")
OTHER_GUARDIAN = auth(10, "guardian", "g2@test.com")
SIG = "data:image/png;base64," + "A" * 600


@pytest.fixture
def linked(env):
    db, client = env
    db.add(models.User(id=9, email="g@test.com", full_name="김영희", role="guardian", center_id=1))
    db.add(models.User(id=10, email="g2@test.com", full_name="남의보호자", role="guardian", center_id=1))
    resident = db.query(models.Resident).filter(models.Resident.id == 1).first()
    resident.guardian_id = 9
    resident.primary_caregiver_id = 2
    db.commit()
    pid = client.post("/api/v1/care-plans", json=body(), headers=MANAGER).json()["data"]["id"]
    return db, client, pid


def test_guardian_cannot_see_plan_until_shared(linked):
    _, client, pid = linked
    assert client.get("/api/v1/care-plans/guardian", headers=GUARDIAN).json()["plans"] == []
    res = client.post(f"/api/v1/care-plans/{pid}/share", headers=MANAGER)
    assert res.status_code == 200 and res.json()["data"]["shared_at"]
    plans = client.get("/api/v1/care-plans/guardian", headers=GUARDIAN).json()["plans"]
    assert len(plans) == 1 and plans[0]["signed"] is False and "issues" not in plans[0]
    assert client.get("/api/v1/care-plans/guardian", headers=OTHER_GUARDIAN).json()["plans"] == []


def test_share_needs_linked_guardian(env):
    _, client = env
    pid = client.post("/api/v1/care-plans", json=body(), headers=MANAGER).json()["data"]["id"]
    assert client.post(f"/api/v1/care-plans/{pid}/share", headers=MANAGER).status_code == 400


def test_guardian_signs_once_and_manager_is_notified(linked):
    db, client, pid = linked
    client.post(f"/api/v1/care-plans/{pid}/share", headers=MANAGER)
    sign = {"signer_name": "김영희", "relation": "딸", "signature": SIG}
    assert client.post(f"/api/v1/care-plans/{pid}/sign", json={**sign, "signature": "data:image/png;base64,AAA"}, headers=GUARDIAN).status_code == 400  # 빈 서명
    assert client.post(f"/api/v1/care-plans/{pid}/sign", json={**sign, "relation": " "}, headers=GUARDIAN).status_code == 400
    assert client.post(f"/api/v1/care-plans/{pid}/sign", json=sign, headers=OTHER_GUARDIAN).status_code == 404
    ok = client.post(f"/api/v1/care-plans/{pid}/sign", json=sign, headers=GUARDIAN).json()["data"]
    assert ok["signed"] and ok["guardian_signer"] == "김영희(딸)"
    assert client.post(f"/api/v1/care-plans/{pid}/sign", json=sign, headers=GUARDIAN).status_code == 400  # 재서명 불가
    assert db.query(models.Notification).filter(models.Notification.user_id == 1, models.Notification.kind == "care_plan_signed").count() == 1
    manager_view = client.get("/api/v1/care-plans?resident_id=1", headers=MANAGER).json()["plans"][0]
    assert manager_view["signed_via"] == "app" and manager_view["has_signature"] is True
    assert "signature" not in manager_view  # 서명 이미지 자체는 목록에 싣지 않는다


def test_unshared_plan_cannot_be_signed(linked):
    _, client, pid = linked
    assert client.post(f"/api/v1/care-plans/{pid}/sign", json={"signer_name": "김영희", "relation": "딸", "signature": SIG}, headers=GUARDIAN).status_code == 404


def test_caregiver_sees_and_acknowledges_own_residents_plan(linked):
    _, client, pid = linked
    mine = client.get("/api/v1/care-plans/mine", headers=CAREGIVER).json()["plans"]
    assert [p["resident_name"] for p in mine] == ["김이용"] and mine[0]["acknowledged_at"] is None
    before = client.get("/api/v1/care-plans?resident_id=1", headers=MANAGER).json()["plans"][0]
    assert any("요양보호사가 이 계획서를 아직 확인하지 않았습니다" in i for i in before["issues"])
    assert client.post(f"/api/v1/care-plans/{pid}/ack", headers=CAREGIVER).status_code == 200
    assert client.post(f"/api/v1/care-plans/{pid}/ack", headers=CAREGIVER).status_code == 200  # 여러 번 눌러도 한 건
    after = client.get("/api/v1/care-plans?resident_id=1", headers=MANAGER).json()["plans"][0]
    assert after["caregiver_ack"]["acknowledged_at"] and not any("요양보호사가" in i for i in after["issues"])


def test_other_residents_plan_cannot_be_acknowledged_and_roles(linked):
    db, client, pid = linked
    db.query(models.Resident).filter(models.Resident.id == 1).first().primary_caregiver_id = None
    db.commit()
    assert client.post(f"/api/v1/care-plans/{pid}/ack", headers=CAREGIVER).status_code == 404
    assert client.get("/api/v1/care-plans/mine", headers=GUARDIAN).status_code == 403
    assert client.get("/api/v1/care-plans/guardian", headers=CAREGIVER).status_code == 403
    assert client.post(f"/api/v1/care-plans/{pid}/share", headers=CAREGIVER).status_code == 403


def test_manager_can_view_signature_image_only_when_signed(linked):
    _, client, pid = linked
    assert client.get(f"/api/v1/care-plans/{pid}/signature", headers=MANAGER).status_code == 404
    client.post(f"/api/v1/care-plans/{pid}/share", headers=MANAGER)
    client.post(f"/api/v1/care-plans/{pid}/sign", json={"signer_name": "김영희", "relation": "딸", "signature": SIG}, headers=GUARDIAN)
    res = client.get(f"/api/v1/care-plans/{pid}/signature", headers=MANAGER).json()
    assert res["signature"] == SIG and res["signer"] == "김영희(딸)"
    assert client.get(f"/api/v1/care-plans/{pid}/signature", headers=GUARDIAN).status_code == 403


def test_plan_form_returns_print_values_and_hides_other_centers(env):
    db, client = env
    created = client.post("/api/v1/care-plans", json=body(), headers=MANAGER).json()["data"]
    data = client.get(f"/api/v1/care-plans/{created['id']}/form", headers=MANAGER).json()["data"]
    assert data["center_name"] == "센터"
    assert data["resident"]["name"] == "김이용"
    assert data["plan"]["frequency"] == "주 5회"
    assert data["plan"]["duration_minutes"] == 180
    assert data["plan"]["author_name"] == "센터장"
    assert data["plan"]["service_start_date"] == "2026-10-10"
    assert client.get(f"/api/v1/care-plans/{created['id']}/form", headers=CAREGIVER).status_code == 403
    db.add(models.CarePlan(id=99, center_id=2, resident_id=3, author_id=1, written_date=date(2026, 10, 1), goals="x"))
    db.commit()
    assert client.get("/api/v1/care-plans/99/form", headers=MANAGER).status_code == 404
