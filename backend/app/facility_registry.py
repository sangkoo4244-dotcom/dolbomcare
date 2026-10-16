"""공단 장기요양기관 목록(공공데이터 '장기요양기관 시설별 현황' 엑셀)을 읽어 DB에 넣고, 기관기호·기관명을 대조한다.

엑셀은 내용이 바깥에서 온 데이터이므로 XML을 값으로만 읽는다(수식·외부 참조는 실행하지 않는다).
파일이 커서(수만 행) 시트를 한 줄씩 훑는다. 가져올 때마다 목록을 통째로 바꾼다."""
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from io import BytesIO

from sqlalchemy.orm import Session

from app.models import FacilityRegistry

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RELS_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
GENERAL_SHEET = "일반현황"
TYPE_SHEET = "입소인원"  # 기관유형코드·정원이 있는 시트
MAX_BYTES = 30 * 1024 * 1024
CODE_PATTERN = re.compile(r"^\d{11}$")


class FacilityImportError(Exception):
    pass


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", value or "").lower()


def _sheet_targets(z: zipfile.ZipFile) -> dict:
    """시트 이름 → 파일 경로 (workbook.xml과 rels를 따라간다)."""
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target_by_id = {}
    for rel in rels:
        target = rel.get("Target", "")
        target = target.lstrip("/") if target.startswith("/") else "xl/" + target
        target_by_id[rel.get("Id")] = target
    out = {}
    for sheet in wb.iter(f"{NS}sheet"):
        path = target_by_id.get(sheet.get(f"{RELS_NS}id"))
        if path:
            out[sheet.get("name")] = path
    return out


def _shared_strings(z: zipfile.ZipFile) -> list:
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(f"{NS}t")) for si in root.findall(f"{NS}si")]


def _column_index(ref: str) -> int:
    n = 0
    for ch in re.sub(r"[^A-Z]", "", ref.upper()):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _sheet_rows(z: zipfile.ZipFile, path: str, strings: list):
    """한 시트의 행을 리스트로 하나씩 내준다 (빈 칸은 빈 문자열)."""
    with z.open(path) as f:
        for _, element in ET.iterparse(f, events=("end",)):
            if element.tag != f"{NS}row":
                continue
            cells = {}
            for c in element.findall(f"{NS}c"):
                kind = c.get("t")
                if kind == "inlineStr":
                    value = "".join(t.text or "" for t in c.iter(f"{NS}t"))
                else:
                    v = c.find(f"{NS}v")
                    if v is None or v.text is None:
                        continue
                    value = strings[int(v.text)] if kind == "s" else v.text
                cells[_column_index(c.get("r", ""))] = str(value).strip()
            element.clear()
            width = max(cells) + 1 if cells else 0
            yield [cells.get(i, "") for i in range(width)]


def _header_index(header: list, name: str) -> int:
    if name not in header:
        raise FacilityImportError(f"파일에 '{name}' 열이 없습니다. 공단 '장기요양기관 시설별 현황' 파일인지 확인해 주세요")
    return header.index(name)


def import_workbook(db: Session, data: bytes, source: str) -> dict:
    if len(data) > MAX_BYTES:
        raise FacilityImportError("파일이 너무 큽니다 (30MB까지)")
    try:
        z = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile:
        raise FacilityImportError("엑셀(.xlsx) 파일이 아닙니다")
    with z:
        targets = _sheet_targets(z)
        if GENERAL_SHEET not in targets:
            raise FacilityImportError(f"'{GENERAL_SHEET}' 시트가 없습니다. 공단 '장기요양기관 시설별 현황' 파일인지 확인해 주세요")
        strings = _shared_strings(z)

        types = {}
        if TYPE_SHEET in targets:
            rows = _sheet_rows(z, targets[TYPE_SHEET], strings)
            header = next(rows, [])
            code_i, type_i = _header_index(header, "장기요양기관코드"), _header_index(header, "기관유형코드")
            for row in rows:
                if len(row) > max(code_i, type_i) and row[code_i] and row[type_i]:
                    codes = types.setdefault(row[code_i], [])
                    if row[type_i] not in codes:
                        codes.append(row[type_i])

        rows = _sheet_rows(z, targets[GENERAL_SHEET], strings)
        header = next(rows, [])
        code_i = _header_index(header, "장기요양기관코드")
        name_i = _header_index(header, "장기요양기관이름")
        addr_i = header.index("기관별 상세주소") if "기관별 상세주소" in header else None
        date_i = header.index("지정일자") if "지정일자" in header else None

        now = datetime.now()
        records, seen = [], set()
        for row in rows:
            if len(row) <= max(code_i, name_i):
                continue
            code, name = row[code_i], row[name_i]
            if not CODE_PATTERN.match(code) or not name or code in seen:
                continue
            seen.add(code)
            records.append(FacilityRegistry(
                code=code, name=name,
                address=row[addr_i] if addr_i is not None and addr_i < len(row) else None,
                designated_date=row[date_i] if date_i is not None and date_i < len(row) else None,
                type_codes=",".join(types.get(code, [])) or None,
                source=source, imported_at=now,
            ))

    if not records:
        raise FacilityImportError("읽을 수 있는 기관이 없습니다")
    db.query(FacilityRegistry).delete()
    db.bulk_save_objects(records)
    db.commit()
    return {"count": len(records), "source": source, "imported_at": now.isoformat(timespec="seconds")}


def registry_status(db: Session) -> dict:
    count = db.query(FacilityRegistry).count()
    latest = db.query(FacilityRegistry).order_by(FacilityRegistry.imported_at.desc()).first()
    return {"count": count, "source": latest.source if latest else None,
            "imported_at": latest.imported_at.isoformat(timespec="seconds") if latest else None}


def check_institution(db: Session, code: str, name: str) -> dict:
    """기관기호(11자리)가 공단 목록에 있고, 기관명이 같은지 본다."""
    code = (code or "").strip()
    if not CODE_PATTERN.match(code):
        return {"ok": False, "reason": "invalid_code",
                "message": "장기요양기관기호는 숫자 11자리입니다. 장기요양기관지정서에서 기관기호를 다시 확인해 주세요"}
    row = db.query(FacilityRegistry).filter(FacilityRegistry.code == code).first()
    if not row:
        return {"ok": False, "reason": "not_found",
                "message": "공단 장기요양기관 목록에서 이 기관기호를 찾지 못했습니다. 기관기호를 다시 확인해 주세요. 최근에 지정받은 기관이면 운영자에게 문의해 주세요."}
    if _normalize_name(row.name) != _normalize_name(name):
        return {"ok": False, "reason": "name_mismatch",
                "message": f"기관기호는 맞지만 공단 기관명과 다릅니다. 센터명을 공단 기관명 '{row.name}'대로 적어 주세요."}
    return {"ok": True, "reason": "match", "name": row.name, "code": code, "message": "공단 장기요양기관 목록에서 확인되었습니다"}
