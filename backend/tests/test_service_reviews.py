from datetime import date, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import service_reviews as sr
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
    db.add(models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1))
    db.add(models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1))
    db.add(models.Resident(id=1, center_id=1, name="김이용", admission_date=datetime(2025, 1, 1)))
    db.add(models.Resident(id=2, center_id=1, name="이이용", admission_date=datetime(2025, 1, 1)))
    db.add(models.Resident(id=3, center_id=1, name="신규", admission_date=datetime(2026, 9, 1)))  # 이번 반기 신규
    db.add(models.Resident(id=4, center_id=2, name="타센터", admission_date=datetime(2025, 1, 1)))
    db.commit()
    app = FastAPI()
    app.include_router(sr.router, prefix="/api/v1/service-reviews")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def ev_body(**kw):
    base = {"resident_id": 1, "evaluated_date": "2026-09-20", "summary": "보행이 불안정해져 방문 시간을 늘릴 필요가 있음", "status_changed": True}
    base.update(kw)
    return base


def test_period_helpers():
    assert sr.half_of(date(2026, 6, 30)) == (2026, 1) and sr.half_of(date(2026, 7, 1)) == (2026, 2)
    assert sr.quarter_range(date(2026, 10, 13)) == (date(2026, 10, 1), date(2026, 12, 31))
    assert sr.quarter_range(date(2026, 2, 5)) == (date(2026, 1, 1), date(2026, 3, 31))


def test_evaluation_requires_summary_and_basis_when_unchanged(env):
    _, client = env
    assert client.post("/api/v1/service-reviews/evaluations", json=ev_body(summary="짧음"), headers=MANAGER).status_code == 400
    assert client.post("/api/v1/service-reviews/evaluations", json=ev_body(status_changed=False), headers=MANAGER).status_code == 400
    ok = client.post("/api/v1/service-reviews/evaluations", json=ev_body(status_changed=False, no_change_basis="지난 평가 때와 보행·인지 상태가 같음"), headers=MANAGER)
    assert ok.status_code == 200 and ok.json()["data"]["follow_up"]["state"] in ("done", "overdue", "pending")


def test_follow_up_states(env):
    db, client = env
    # 상태 변화 있음 + 30일 안에 계획서 재작성 => done
    client.post("/api/v1/service-reviews/evaluations", json=ev_body(evaluated_date="2026-09-20"), headers=MANAGER)
    db.add(models.CarePlan(center_id=1, resident_id=1, written_date=date(2026, 10, 5), author_id=1, goals="g", needs="n", details="d", frequency="주 5회", opinion="o"))
    # 이이용: 평가만 하고 8/1 -> 재작성 없이 기한(8/31) 지남 => overdue
    db.add(models.ServiceEvaluation(center_id=1, resident_id=2, evaluated_date=date(2026, 8, 1), author_id=1, summary="요양 필요도 증가", status_changed=True))
    db.commit()
    evs = {e["resident_name"]: e for e in client.get("/api/v1/service-reviews/evaluations", headers=MANAGER).json()["evaluations"]}
    assert evs["김이용"]["follow_up"]["state"] == "done"
    assert evs["이이용"]["follow_up"]["state"] == "overdue"
    st = sr.evaluation_status(db, 1, TODAY)
    assert st["overdue_follow_up"] == 1


def test_evaluation_status_this_half_and_new_resident_excluded(env):
    db, client = env
    client.post("/api/v1/service-reviews/evaluations", json=ev_body(evaluated_date="2026-08-10", resident_id=1), headers=MANAGER)
    st = sr.evaluation_status(db, 1, TODAY)
    names = {r["name"]: r for r in st["residents"]}
    assert names["김이용"]["done"] and not names["이이용"]["done"]
    assert "신규" not in names and "타센터" not in names     # 이번 반기 신규, 타 센터는 제외
    assert st["missing"] == 1 and st["half"] == 2


def attendees(n=3, with_head=True, opinion="의견 있음"):
    people = [{"name": "센터장", "role": "시설장" if with_head else "사회복지사", "opinion": opinion, "signed": True},
              {"name": "박요양", "role": "요양보호사", "opinion": opinion, "signed": True},
              {"name": "이복지", "role": "사회복지사", "opinion": opinion, "signed": False},
              {"name": "최요양", "role": "요양보호사", "opinion": opinion, "signed": True}]
    return people[:n]


def conf_body(**kw):
    base = {"resident_id": 1, "conference_date": "2026-10-02", "reason": "낙상 위험이 높아져 방문 환경 점검이 필요함",
            "content": "집 안 환경과 보행 상태를 함께 논의함", "plan": "욕실 안전손잡이 설치 안내 및 보행 훈련 병행", "attendees": attendees()}
    base.update(kw)
    return base


def test_conference_rules(env):
    _, client = env
    url = "/api/v1/service-reviews/conferences"
    assert client.post(url, json=conf_body(attendees=attendees(2)), headers=MANAGER).status_code == 400          # 3인 미만
    assert client.post(url, json=conf_body(attendees=attendees(with_head=False)), headers=MANAGER).status_code == 400  # 시설장 없음
    assert client.post(url, json=conf_body(attendees=attendees(opinion=" ")), headers=MANAGER).status_code == 400  # 의견 비어 있음
    dup = attendees(); dup[1]["name"] = "센터장"
    assert client.post(url, json=conf_body(attendees=dup), headers=MANAGER).status_code == 400
    assert client.post(url, json=conf_body(attendees=attendees(opinion="의견없음")), headers=MANAGER).status_code == 200


def test_conference_follow_up_flow(env):
    db, client = env
    url = "/api/v1/service-reviews/conferences"
    cid = client.post(url, json=conf_body(), headers=MANAGER).json()["data"]["id"]
    assert client.put(f"{url}/{cid}/follow-up", json={"reflected_date": "2026-10-02"}, headers=MANAGER).status_code == 400   # 회의 당일은 불인정
    ok = client.put(f"{url}/{cid}/follow-up", json={"reflected_date": "2026-10-10", "reflected_note": "급여제공계획서 변경"}, headers=MANAGER).json()["data"]
    assert ok["follow_up"]["state"] in ("pending", "overdue")
    assert client.put(f"{url}/{cid}/follow-up", json={"evaluated_date": "2026-10-20"}, headers=MANAGER).status_code == 400   # 해결 여부 없음
    assert client.put(f"{url}/{cid}/follow-up", json={"evaluated_date": "2026-10-20", "resolved": False}, headers=MANAGER).status_code == 400  # 추가 조치 없음
    done = client.put(f"{url}/{cid}/follow-up", json={"evaluated_date": "2026-10-20", "resolved": False, "next_action": "다음 달 재평가 후 환경 개선 재논의"}, headers=MANAGER).json()["data"]
    assert done["follow_up"]["state"] == "done" and done["evaluator_name"] == "센터장"


def test_conference_status_and_overdue(env):
    db, client = env
    db.add(models.CaseConference(center_id=1, resident_id=1, conference_date=date(2026, 8, 1), author_id=1, reason="r", content="c", plan="p", attendees="[]"))
    db.commit()
    st = sr.conference_status(db, 1, TODAY)
    assert st["count_this_quarter"] == 0 and not st["quarter_done"] and st["overdue_follow_up"] == 1
    client.post("/api/v1/service-reviews/conferences", json=conf_body(), headers=MANAGER)
    assert sr.conference_status(db, 1, TODAY)["quarter_done"]


def test_roles_and_isolation(env):
    _, client = env
    assert client.post("/api/v1/service-reviews/evaluations", json=ev_body(resident_id=4), headers=MANAGER).status_code == 404
    assert client.post("/api/v1/service-reviews/conferences", json=conf_body(resident_id=4), headers=MANAGER).status_code == 404
    assert client.get("/api/v1/service-reviews/evaluations", headers=CAREGIVER).status_code == 403
    assert client.get("/api/v1/service-reviews/conferences/status", headers=CAREGIVER).status_code == 403
