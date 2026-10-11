from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import nhis_ltc
from app.api import nhis
from app.api.users import create_access_token


def auth(uid, role, email):
    token = create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}


MANAGER = auth(1, "center_manager", "manager@test.com")
CAREGIVER = auth(2, "caregiver", "caregiver1@test.com")

SUCCESS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response><header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE.</resultMsg></header>
<body><items><item><insttNm>사랑요양센터</insttNm><addr>서울시 강남구</addr><telno>02-1234-5678</telno></item></items></body>
</response>"""

EMPTY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response><header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE.</resultMsg></header><body/></response>"""

ERROR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<response><header><resultCode>30</resultCode><resultMsg>SERVICE KEY IS NOT REGISTERED ERROR.</resultMsg></header></response>"""


def test_call_without_service_key_fails_gracefully(monkeypatch):
    monkeypatch.setattr(nhis_ltc, "NHIS_LTC_SERVICE_KEY", None)
    result = nhis_ltc.get_general_status("14139000308")
    assert result["ok"] is False
    assert "NHIS_LTC_SERVICE_KEY" in result["message"]


def test_call_parses_item_fields_on_success(monkeypatch):
    monkeypatch.setattr(nhis_ltc, "NHIS_LTC_SERVICE_KEY", "dummy-key")
    monkeypatch.setattr(nhis_ltc.httpx, "get", lambda *a, **k: SimpleNamespace(
        text=SUCCESS_XML, raise_for_status=lambda: None,
    ))
    result = nhis_ltc.get_general_status("14139000308")
    assert result["ok"] is True
    assert result["fields"]["insttNm"] == "사랑요양센터"
    assert result["fields"]["addr"] == "서울시 강남구"


def test_call_handles_empty_body(monkeypatch):
    monkeypatch.setattr(nhis_ltc, "NHIS_LTC_SERVICE_KEY", "dummy-key")
    monkeypatch.setattr(nhis_ltc.httpx, "get", lambda *a, **k: SimpleNamespace(
        text=EMPTY_XML, raise_for_status=lambda: None,
    ))
    result = nhis_ltc.get_general_status("00000000000")
    assert result["ok"] is False
    assert "없습니다" in result["message"]


def test_call_handles_api_error_result_code(monkeypatch):
    monkeypatch.setattr(nhis_ltc, "NHIS_LTC_SERVICE_KEY", "dummy-key")
    monkeypatch.setattr(nhis_ltc.httpx, "get", lambda *a, **k: SimpleNamespace(
        text=ERROR_XML, raise_for_status=lambda: None,
    ))
    result = nhis_ltc.get_general_status("14139000308")
    assert result["ok"] is False
    assert "SERVICE KEY" in result["message"]


def test_call_without_institution_code():
    result = nhis_ltc.get_general_status("")
    assert result["ok"] is False


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(nhis.router, prefix="/api/v1/nhis")
    return TestClient(app)


def test_endpoint_requires_manager(client):
    res = client.get("/api/v1/nhis/ltc-institution/14139000308", headers=CAREGIVER)
    assert res.status_code == 403


def test_endpoint_returns_both_general_and_staff(client, monkeypatch):
    monkeypatch.setattr(nhis, "get_general_status", lambda code: {"ok": True, "message": "OK", "fields": {"insttNm": "사랑요양센터"}})
    monkeypatch.setattr(nhis, "get_staff_status", lambda code: {"ok": True, "message": "OK", "fields": {"careWorkerCnt": "5"}})
    res = client.get("/api/v1/nhis/ltc-institution/14139000308", headers=MANAGER)
    assert res.status_code == 200
    body = res.json()
    assert body["general"]["fields"]["insttNm"] == "사랑요양센터"
    assert body["staff"]["fields"]["careWorkerCnt"] == "5"


def test_endpoint_returns_400_when_both_fail(client, monkeypatch):
    monkeypatch.setattr(nhis, "get_general_status", lambda code: {"ok": False, "message": "조회 실패", "fields": {}})
    monkeypatch.setattr(nhis, "get_staff_status", lambda code: {"ok": False, "message": "조회 실패", "fields": {}})
    res = client.get("/api/v1/nhis/ltc-institution/00000000000", headers=MANAGER)
    assert res.status_code == 400
