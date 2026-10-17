"""공개 본인부담금 계산기: 로그인 없이 쓰고, 방문 1회와 월 합계를 기존 규칙으로 계산하며, 월 한도 초과분은 전액 본인부담이다."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import copay_estimate


def client():
    app = FastAPI()
    app.include_router(copay_estimate.router, prefix="/api/v1/public/copay")
    return TestClient(app)


def test_public_without_login_and_one_visit():
    r = client().get("/api/v1/public/copay/estimate?grade=3&client_type=일반&minutes=60&visits_per_month=1")
    assert r.status_code == 200
    v = r.json()["data"]["per_visit"]
    assert v == {"minutes": 60, "total": 25320, "patient": 3790, "insurer": 21530}


def test_monthly_within_limit_uses_rate_on_total():
    m = client().get("/api/v1/public/copay/estimate?grade=3&client_type=일반&minutes=60&visits_per_month=8").json()["data"]["month"]
    assert m["total"] == 25320 * 8 and m["over_limit"] == 0
    assert m["patient"] == 30320  # 회당 3,790원 x 8회


def test_over_monthly_limit_excess_is_all_patient():
    # 5등급 한도 1,208,900원. 240분 18회 = 1,261,440원 → 초과 52,540원은 전액 본인부담
    m = client().get("/api/v1/public/copay/estimate?grade=5&client_type=일반&minutes=240&visits_per_month=18").json()["data"]["month"]
    assert m["limit"] == 1208900 and m["total"] == 70080 * 18
    assert m["over_limit"] == 52540
    # 한도 안: 17회 온전(회당 10,510원) + 마지막 회의 한도 안쪽 17,540원의 15%(2,630원)
    assert m["patient"] == 17 * 10510 + 2630 + 52540 == 233840


def test_basic_livelihood_pays_nothing_on_covered_part():
    m = client().get("/api/v1/public/copay/estimate?grade=2&client_type=기초생활보장&minutes=30&visits_per_month=4").json()["data"]["month"]
    assert m["patient"] == 0 and m["insurer"] == 17450 * 4


def test_bad_inputs_refused():
    c = client()
    assert c.get("/api/v1/public/copay/estimate?grade=9&minutes=60").status_code == 400
    assert c.get("/api/v1/public/copay/estimate?grade=1&client_type=외계인&minutes=60").status_code == 400
    assert c.get("/api/v1/public/copay/estimate?grade=1&minutes=45").status_code == 400
    assert c.get("/api/v1/public/copay/estimate?grade=1&minutes=60&visits_per_month=40").status_code == 422


def test_notes_say_it_is_reference_only():
    notes = client().get("/api/v1/public/copay/estimate?grade=1&minutes=60").json()["data"]["notes"]
    assert any("참고용" in n for n in notes) and any("중증 가산" in n for n in notes)
    assert any("상한제" in n for n in notes) and any("복지용구" in n for n in notes)
