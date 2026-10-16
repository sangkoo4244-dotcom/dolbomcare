"""공단 기관 목록 가져오기와 체험 신청의 기관기호 대조: 목록에 있고 기관명이 같은 곳만 신청을 받는다."""
import base64
import io
import zipfile
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import admin, center_directory
from app.api.users import create_access_token
from app.database import Base, get_db
from app.facility_registry import check_institution, import_workbook

OPERATOR = {"Authorization": "Bearer " + create_access_token({"sub": "ops@eeum.kr", "uid": 1, "role": "center_manager"}, timedelta(hours=1))}
CODE = "11111000006"


def make_xlsx(sheets: dict) -> bytes:
    """테스트용 최소 엑셀 파일: 시트 이름 → 행 목록(문자열). 실제 공단 파일과 같은 구조(일반 시트·입소인원 시트)."""
    def cell(ref, value):
        return f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>'
    names = list(sheets)
    sheet_xml = []
    for rows in sheets.values():
        body = []
        for r, row in enumerate(rows, start=1):
            cells = "".join(cell(f"{chr(65 + c)}{r}", v) for c, v in enumerate(row))
            body.append(f'<row r="{r}">{cells}</row>')
        sheet_xml.append('<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                         + "".join(body) + "</sheetData></worksheet>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        sheets_tag = "".join(f'<sheet name="{n}" sheetId="{i}" r:id="rId{i}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
                             for i, n in enumerate(names, start=1))
        z.writestr("xl/workbook.xml", f'<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                                      f'<sheets>{sheets_tag}</sheets></workbook>')
        rels = "".join(f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml"/>' for i in range(1, len(names) + 1))
        z.writestr("xl/_rels/workbook.xml.rels", f'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>')
        for i, xml in enumerate(sheet_xml, start=1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", xml)
    return buf.getvalue()


GENERAL = [
    ["장기요양기관코드", "장기요양기관이름", "기관별 상세주소", "지정일자"],
    [CODE, "청운노인요양원", "서울특별시 종로구 구기동", "20080625"],
    ["abc", "잘못된코드", "", ""],
    [CODE, "중복 행", "", ""],
    ["11111000056", "인자인케어센터", "서울특별시 종로구 평창동", "20100701"],
]
TYPES = [
    ["장기요양기관코드", "기관유형코드", "기관유형명", "정원"],
    [CODE, "A03", "노인요양시설(개정법)", "38"],
    [CODE, "B01", "방문요양", ""],
]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("PLATFORM_ADMIN_EMAILS", "ops@eeum.kr")
    engine = create_engine(f"sqlite:///{tmp_path / 'fac.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([models.Center(id=1, name="테스트센터"),
                models.User(id=1, email="ops@eeum.kr", full_name="운영자", role="center_manager", center_id=1)])
    db.commit()
    app = FastAPI()
    app.include_router(admin.router, prefix="/api/v1/admin")
    app.include_router(center_directory.router, prefix="/api/v1/centers")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    return db, TestClient(app)


def test_import_keeps_valid_unique_facilities_with_their_types(env):
    db, _ = env
    result = import_workbook(db, make_xlsx({"일반현황": GENERAL, "입소인원": TYPES}), "시설별 현황.xlsx")
    assert result["count"] == 2  # 잘못된 코드와 중복 행은 뺀다
    row = db.query(models.FacilityRegistry).filter_by(code=CODE).one()
    assert row.name == "청운노인요양원" and row.type_codes == "A03,B01" and row.designated_date == "20080625"


def test_reimport_replaces_the_whole_list(env):
    db, _ = env
    import_workbook(db, make_xlsx({"일반현황": GENERAL, "입소인원": TYPES}), "a.xlsx")
    import_workbook(db, make_xlsx({"일반현황": [GENERAL[0], GENERAL[4]], "입소인원": TYPES}), "b.xlsx")
    assert db.query(models.FacilityRegistry).count() == 1 and db.query(models.FacilityRegistry).one().source == "b.xlsx"


def test_check_institution_accepts_only_a_listed_code_with_the_same_name(env):
    db, _ = env
    import_workbook(db, make_xlsx({"일반현황": GENERAL, "입소인원": TYPES}), "a.xlsx")
    assert check_institution(db, CODE, "청운 노인요양원")["ok"] is True  # 띄어쓰기 차이는 같은 이름
    assert check_institution(db, CODE, "다른센터")["reason"] == "name_mismatch"
    assert check_institution(db, "99999999999", "청운노인요양원")["reason"] == "not_found"
    assert check_institution(db, "1234", "청운노인요양원")["reason"] == "invalid_code"


def test_trial_request_needs_a_listed_facility_and_stores_the_verified_code(env):
    db, client = env
    import_workbook(db, make_xlsx({"일반현황": GENERAL, "입소인원": TYPES}), "a.xlsx")
    base = {"center_name": "청운노인요양원", "manager_name": "홍길동", "email": "boss@example.com",
            "certificate_name": "지정서.pdf", "certificate_type": "application/pdf",
            "certificate_data": base64.b64encode(b"%PDF-1.4 test").decode()}
    refused = client.post("/api/v1/centers/trial-requests", json={**base, "institution_code": "99999999999"})
    assert refused.status_code == 400 and "찾지 못했습니다" in refused.json()["detail"]
    assert db.query(models.TrialRequest).count() == 0
    assert client.post("/api/v1/centers/trial-requests", json={**base, "institution_code": CODE}).status_code == 200
    saved = db.query(models.TrialRequest).one()
    assert saved.institution_code == CODE and saved.institution_verified is True


def test_only_the_operator_can_import_and_non_operators_are_refused(env):
    _, client = env
    files = {"file": ("a.xlsx", make_xlsx({"일반현황": GENERAL, "입소인원": TYPES}), "application/octet-stream")}
    assert client.post("/api/v1/admin/facilities/import", files=files).status_code in (401, 403)
    ok = client.post("/api/v1/admin/facilities/import", files=files, headers=OPERATOR)
    assert ok.status_code == 200 and ok.json()["data"]["count"] == 2
    assert client.get("/api/v1/admin/facilities/status", headers=OPERATOR).json()["data"]["count"] == 2
