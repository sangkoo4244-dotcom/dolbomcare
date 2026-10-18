"""수급자 정보의 새 항목이 다른 화면으로 제대로 넘어가는지 본다: 추가 보호자 문자 발송, 계약통보서, 청구 목록의 청구지 주소.
사회복지사와 센터장이 같은 값을 보는지 확인한다."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import billing, contract_notice, residents, sms
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MANAGER = auth(1, "center_manager", "m@test.com")
SOCIAL = auth(3, "social_worker", "s@test.com")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'conn.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A센터", institution_code="L1234"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=3, email="s@test.com", full_name="사회복지사", role="social_worker", center_id=1),
        models.Resident(id=1, center_id=1, name="이용자", care_grade=2, client_type="일반",
                        guardian_name="주보호자", guardian_phone="010-1000-0000",
                        service_start_date=datetime(2026, 4, 1).date(), billing_address="서울 강남구 1"),
    ])
    db.flush()
    db.add(models.ResidentGuardian(resident_id=1, name="김자녀", relation="자녀", phone="010-2000-0000"))
    db.add(models.ResidentGuardian(resident_id=1, name="김형제", relation="형제", phone="010-1000-0000"))  # 주 보호자와 같은 번호
    db.add(models.DailyRecord(resident_id=1, caregiver_id=2, recorded_date=datetime(2026, 10, 10, 9), duration_minutes=60,
                              service_type="basic_care", benefit_type="home_care"))
    db.flush()
    db.add(models.BillingRecord(daily_record_id=1, caregiver_id=2, resident_id=1, center_id=1, resident_name="이용자",
                                service_type="basic_care", benefit_type="home_care", amount=20000, total_cost=30000,
                                recorded_date=datetime(2026, 10, 10, 9), year_month="2026-10", approval_status="approved"))
    db.commit()
    db.close()
    app = FastAPI()
    app.include_router(sms.router, prefix="/api/v1/sms")
    app.include_router(contract_notice.router, prefix="/api/v1/contract-notice")
    app.include_router(billing.router, prefix="/api/v1/billing")
    app.include_router(residents.router, prefix="/api/v1/residents")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    client = TestClient(app)
    client.Session = Session
    return client


def test_sms_goes_to_primary_and_additional_guardians_once_per_number(env, monkeypatch):
    sent = []
    monkeypatch.setattr(sms, "sms_configured", lambda: True)
    monkeypatch.setattr(sms, "reserve_send", lambda db, center_id: True)
    monkeypatch.setattr(sms, "send_sms", lambda phone, text: sent.append(phone) or True)
    r = env.post("/api/v1/sms/send", headers=MANAGER, json={"resident_ids": [1], "text": "안내"})
    assert r.status_code == 200, r.text
    assert sent == ["010-1000-0000", "010-2000-0000"]  # 주 보호자, 추가 보호자 자녀. 같은 번호 형제는 뺀다
    assert r.json()["data"] == {"sent": 2, "failed": 0, "no_phone": 0, "blocked": 0}
    history = env.get("/api/v1/sms/history", headers=MANAGER).json()["data"]
    assert sorted(h["phone"] for h in history) == ["010-1000-0000", "010-2000-0000"]


def test_contract_notice_shows_start_date_billing_address_and_additional_guardians_to_manager_and_social_worker(env):
    for headers in (MANAGER, SOCIAL):
        d = env.get("/api/v1/contract-notice/draft", params={"resident_id": 1, "benefit_type": "home_care", "year_month": "2026-10"},
                    headers=headers).json()["data"]
        assert d["resident"]["service_start_date"] == "2026-04-01"
        assert d["resident"]["billing_address"] == "서울 강남구 1"
        assert [g["name"] for g in d["additional_guardians"]] == ["김자녀", "김형제"]


def test_billing_list_carries_the_claim_address_for_the_manager(env):
    rows = env.get("/api/v1/billing/", headers=MANAGER).json()
    rows = rows if isinstance(rows, list) else rows.get("data", rows.get("records", []))
    assert rows and rows[0]["billing_address"] == "서울 강남구 1"


def test_resident_detail_shows_the_new_fields_to_the_social_worker_too(env):
    # 사회복지사는 수급자 관리 화면에서 같은 정보를 본다 (읽기 권한은 센터장과 같이 상세 조회로 확인)
    d = env.get("/api/v1/residents/1", headers=SOCIAL).json()
    assert d["service_start_date"] == "2026-04-01"
    assert d["billing_address"] == "서울 강남구 1"
    assert [g["name"] for g in d["additional_guardians"]] == ["김자녀", "김형제"]


def test_same_number_with_different_dashes_is_sent_once(env, monkeypatch):
    sent = []
    monkeypatch.setattr(sms, "sms_configured", lambda: True)
    monkeypatch.setattr(sms, "reserve_send", lambda db, center_id: True)
    monkeypatch.setattr(sms, "send_sms", lambda phone, text: sent.append(phone) or True)
    db = env.Session()
    db.add(models.ResidentGuardian(resident_id=1, name="중복형제", relation="형제", phone="01020000000"))  # 010-2000-0000과 같은 번호
    db.commit()
    db.close()
    env.post("/api/v1/sms/send", headers=MANAGER, json={"resident_ids": [1], "text": "안내"})
    assert sent == ["010-1000-0000", "010-2000-0000"]


def test_empty_service_start_date_string_does_not_fail(env):
    r = env.put("/api/v1/residents/1", headers=MANAGER, json={"service_start_date": "   "})
    assert r.status_code == 200, r.text
    assert env.get("/api/v1/residents/1", headers=MANAGER).json()["service_start_date"] is None
