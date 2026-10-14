"""공단에서 내려받은 표 파일(.xlsx, .csv)을 줄·칸 목록으로 읽는다. 외부 라이브러리 없이 표준 라이브러리만 쓴다.
파일은 저장하지 않는다 (호출한 쪽이 결과만 쓰고 버린다)."""
import csv
import io
import re
import zipfile
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

MAX_ROWS = 5000
MAX_UNZIPPED = 30 * 1024 * 1024  # 압축 폭탄 방지
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


class SheetError(ValueError):
    pass


def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group(0)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def read_xlsx(data: bytes) -> list[list[str]]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise SheetError("엑셀(.xlsx) 파일이 아닙니다")
    if sum(i.file_size for i in zf.infolist()) > MAX_UNZIPPED:
        raise SheetError("파일이 너무 큽니다")
    names = zf.namelist()
    sheets = sorted(n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
    if not sheets:
        raise SheetError("시트를 찾을 수 없습니다")
    shared = []
    if "xl/sharedStrings.xml" in names:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
        for si in root.findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
    root = ET.fromstring(zf.read(sheets[0]))
    rows = []
    for row in root.iter("{%s}row" % NS["m"]):
        cells = {}
        for c in row.findall("m:c", NS):
            idx = _col_index(c.get("r"))
            kind = c.get("t")
            v = c.find("m:v", NS)
            if kind == "s" and v is not None:
                text = shared[int(v.text)] if int(v.text) < len(shared) else ""
            elif kind == "inlineStr":
                text = "".join(t.text or "" for t in c.iter("{%s}t" % NS["m"]))
            else:
                text = v.text if v is not None and v.text is not None else ""
            cells[idx] = text
        if cells:
            width = max(cells) + 1
            rows.append([cells.get(i, "") for i in range(width)])
        if len(rows) > MAX_ROWS + 1:
            raise SheetError(f"{MAX_ROWS}줄을 넘는 파일은 올릴 수 없습니다")
    return rows


def read_csv(data: bytes) -> list[list[str]]:
    for enc in ("utf-8-sig", "cp949"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise SheetError("글자 형식(인코딩)을 읽을 수 없습니다. CSV UTF-8로 저장해 주세요")
    rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
    if len(rows) > MAX_ROWS + 1:
        raise SheetError(f"{MAX_ROWS}줄을 넘는 파일은 올릴 수 없습니다")
    return rows


def read_table(filename: str, data: bytes) -> list[list[str]]:
    name = (filename or "").lower()
    if name.endswith(".xlsx") or data[:2] == b"PK":
        return read_xlsx(data)
    if name.endswith(".csv") or name.endswith(".txt"):
        return read_csv(data)
    raise SheetError("엑셀(.xlsx) 또는 CSV 파일만 올릴 수 있습니다")


_EXCEL_EPOCH = datetime(1899, 12, 30)


def to_datetime(value: str, date_hint: str | None = None):
    """엑셀 칸 값을 날짜·시각으로 바꾼다. 문자열(2026-10-14 09:00, 20261014 0900, 09:00), 엑셀 일련번호를 받는다.
    시각만 있으면 date_hint(같은 줄의 날짜 칸 값)와 합친다. 못 읽으면 None."""
    v = (value or "").strip()
    if not v:
        return None
    # 엑셀 일련번호(날짜 또는 날짜+시각), 시각만(0.375 = 09:00)
    if re.fullmatch(r"\d+(\.\d+)?", v) and not re.fullmatch(r"\d{8,14}", v):
        num = float(v)
        if num >= 20000:
            return _EXCEL_EPOCH + timedelta(days=num)
        if 0 <= num < 1:
            base = to_datetime(date_hint) if date_hint else None
            if base is None:
                return None
            return datetime(base.year, base.month, base.day) + timedelta(days=num)
    digits = re.sub(r"\D", "", v)
    if re.fullmatch(r"\d{8}", digits) and not re.search(r"[:]", v) and len(v) in (8, 10):
        try:
            return datetime(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
        except ValueError:
            return None
    m = re.match(r"^(\d{4})[-./](\d{1,2})[-./](\d{1,2})(?:[ T]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?", v)
    if m:
        y, mo, d, hh, mm, ss = m.groups()
        try:
            return datetime(int(y), int(mo), int(d), int(hh or 0), int(mm or 0), int(ss or 0))
        except ValueError:
            return None
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", v)
    if m and date_hint:
        base = to_datetime(date_hint)
        if base:
            return datetime(base.year, base.month, base.day, int(m.group(1)), int(m.group(2)))
    m = re.match(r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})?$", digits) if re.fullmatch(r"\d{12,14}", digits) else None
    if m:
        y, mo, d, hh, mm, ss = m.groups()
        try:
            return datetime(int(y), int(mo), int(d), int(hh), int(mm), int(ss or 0))
        except ValueError:
            return None
    return None
