"""수급자 이용계약서 초안: 표준약관 조항을 싣고, 2026 수가와 본인부담을 시스템 계산으로 채우며, 다른 센터 이용자는 보지 못한다."""
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import contract_terms
from app.billing_rules import VISIT_FEES
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MANAGER = auth(1, "center_manager", "m@test.com")
CAREGIVER = auth(2, "caregiver", "c@test.com")
OTHER_MANAGER = auth(5, "center_manager", "o@test.com")


@pytest.fixture
def client(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'ct.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A센터", institution_code="12345678901"),
        models.Center(id=2, name="B센터"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=5, email="o@test.com", full_name="타센터장", role="center_manager", center_id=2),
        models.Resident(id=1, center_id=1, name="이용자", care_grade=2, client_type="일반",
                        recognition_number="L1234567890", guardian_name="보호자", guardian_phone="010-0000-0000"),
        models.Resident(id=2, center_id=1, name="차상위이용자", care_grade=3, client_type="차상위계층", recognition_number="L9"),
        models.Resident(id=3, center_id=1, name="번호없음", care_grade=4, client_type="일반"),
        models.Resident(id=4, center_id=2, name="타센터이용자", care_grade=2),
    ])
    db.commit()
    db.close()
    app = FastAPI()
    app.include_router(contract_terms.router, prefix="/api/v1/contract-terms")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_draft_carries_all_fifteen_articles_and_the_resident_and_center_values(client):
    data = client.get("/api/v1/contract-terms/draft?resident_id=1", headers=MANAGER).json()["data"]
    assert [t["title"] for t in data["terms"]][0] == "제1조(목적)"
    assert len(data["terms"]) == 15
    assert data["center"]["institution_code"] == "12345678901"
    assert data["resident"]["recognition_number"] == "L1234567890"
    assert data["guardian"]["name"] == "보호자"


def test_fee_rows_use_the_2026_visit_fee_table_and_the_patient_rates(client):
    rows = client.get("/api/v1/contract-terms/draft?resident_id=1", headers=MANAGER).json()["data"]["fee_rows"]
    assert [r["minutes"] for r in rows] == list(VISIT_FEES.keys())
    by_minutes = {r["minutes"]: r for r in rows}
    assert by_minutes[60]["total"] == 25320
    assert by_minutes[60]["patient"]["일반"] == 3798  # 2026 고시 붙임2와 같은 원 단위 반올림
    assert by_minutes[60]["patient"]["기초생활보장"] == 0


def test_low_income_client_gets_six_percent(client):
    data = client.get("/api/v1/contract-terms/draft?resident_id=2", headers=MANAGER).json()["data"]
    assert data["resident"]["client_type"] == "차상위계층"
    assert {r["minutes"]: r for r in data["fee_rows"]}[60]["patient"]["차상위계층"] == 1519


def test_night_surcharge_difference_is_always_flagged(client):
    warnings = client.get("/api/v1/contract-terms/draft?resident_id=1", headers=MANAGER).json()["data"]["warnings"]
    assert any("야간(18~22시) 20%" in w and "심야 30%" in w for w in warnings)


def test_missing_recognition_number_is_flagged(client):
    warnings = client.get("/api/v1/contract-terms/draft?resident_id=3", headers=MANAGER).json()["data"]["warnings"]
    assert any("인정번호" in w for w in warnings)


def test_other_center_resident_is_not_visible(client):
    assert client.get("/api/v1/contract-terms/draft?resident_id=4", headers=MANAGER).status_code == 404
    assert client.get("/api/v1/contract-terms/draft?resident_id=1", headers=OTHER_MANAGER).status_code == 404


def test_caregiver_cannot_open_the_contract_draft(client):
    assert client.get("/api/v1/contract-terms/draft?resident_id=1", headers=CAREGIVER).status_code == 403
