from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_manager
from app.database import get_db
from app.models import DailyRecord, Resident, Schedule, User
from app.sheet_reader import SheetError, read_table, to_datetime

router = APIRouter()

MAX_UPLOAD = 8 * 1024 * 1024


@router.post("/parse")
async def parse_file(file: UploadFile = File(...), manager: User = Depends(require_manager)):
    """공단에서 내려받은 전자태그 전송내역 파일(.xlsx/.csv)을 읽어 제목 줄과 내용을 돌려준다. 파일은 저장하지 않는다."""
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(status_code=400, detail="파일이 너무 큽니다 (8MB까지)")
    try:
        rows = read_table(file.filename, data)
    except SheetError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if len(rows) < 2:
        raise HTTPException(status_code=400, detail="내용이 없습니다. 첫 줄은 제목, 둘째 줄부터 내용이어야 합니다")
    return {"headers": [h.strip() for h in rows[0]], "rows": rows[1:], "row_count": len(rows) - 1}


class CompareRequest(BaseModel):
    rows: list[list[str]]
    resident_col: int
    start_col: int
    end_col: int | None = None
    date_col: int | None = None
    caregiver_col: int | None = None
    tolerance_minutes: int = 30


def _cell(row, idx):
    if idx is None or idx < 0 or idx >= len(row):
        return ""
    return (row[idx] or "").strip()


@router.post("/compare")
def compare(body: CompareRequest, db: Session = Depends(get_db), manager: User = Depends(require_manager)):
    """공단 전자태그 전송내역과 돌봄케어의 방문 계획·도착 기록을 이용자·날짜·시간으로 맞춰 본다.
    올린 내용은 저장하지 않고 이 요청 안에서만 쓴다."""
    center = manager.center_id
    residents = db.query(Resident).filter(Resident.center_id == center).all()
    by_name = {}
    for r in residents:
        by_name.setdefault(r.name.strip(), []).append(r)
    caregivers = {u.id: u.full_name for u in db.query(User).filter(User.center_id == center).all()}

    tags, bad_rows = [], []
    for i, row in enumerate(body.rows, start=2):  # 엑셀 줄 번호
        name = _cell(row, body.resident_col)
        date_hint = _cell(row, body.date_col) if body.date_col is not None else None
        start = to_datetime(_cell(row, body.start_col), date_hint)
        end = to_datetime(_cell(row, body.end_col), date_hint) if body.end_col is not None else None
        if not name or start is None:
            if name or any(c.strip() for c in row):
                bad_rows.append({"row": i, "message": "수급자 이름이나 시작 시각을 읽을 수 없습니다"})
            continue
        if end is not None and end < start:
            end = None
        tags.append({"row": i, "name": name, "start": start, "end": end, "caregiver": _cell(row, body.caregiver_col) if body.caregiver_col is not None else ""})
    if not tags:
        raise HTTPException(status_code=400, detail="읽을 수 있는 전송내역이 없습니다. 열 지정을 확인해 주세요")

    first_day = min(t["start"] for t in tags).date()
    last_day = max(t["start"] for t in tags).date()
    day_start = datetime.combine(first_day, datetime.min.time())
    day_end = datetime.combine(last_day, datetime.min.time()) + timedelta(days=1)
    schedules = db.query(Schedule).filter(
        Schedule.center_id == center, Schedule.status == "scheduled",
        Schedule.scheduled_date >= day_start, Schedule.scheduled_date < day_end).all()
    records = db.query(DailyRecord).join(Resident, Resident.id == DailyRecord.resident_id).filter(
        Resident.center_id == center, DailyRecord.recorded_date >= day_start, DailyRecord.recorded_date < day_end).all()
    resident_names = {r.id: r.name for r in residents}

    used = set()
    results = []
    tol = max(1, body.tolerance_minutes)
    for t in sorted(tags, key=lambda x: x["start"]):
        matches = by_name.get(t["name"], [])
        row = {"row": t["row"], "name": t["name"], "tag_start": t["start"].strftime("%Y-%m-%d %H:%M"),
               "tag_end": t["end"].strftime("%H:%M") if t["end"] else None,
               "tag_minutes": int((t["end"] - t["start"]).total_seconds() // 60) if t["end"] else None,
               "plan": None, "arrived": None, "note": ""}
        if not matches:
            row.update(status="unknown_resident", note="돌봄케어에 없는 이름입니다 (이름 표기를 확인하세요)")
            results.append(row)
            continue
        ids = {m.id for m in matches}
        candidates = [s for s in schedules if s.resident_id in ids and s.id not in used and s.scheduled_date.date() == t["start"].date()]
        if not candidates:
            rec = [r for r in records if r.resident_id in ids and r.recorded_date.date() == t["start"].date()]
            if rec:
                row.update(status="no_plan", note="승인된 방문 계획은 없고 방문 기록만 있습니다")
            else:
                row.update(status="no_plan", note="돌봄케어에 방문 계획도 기록도 없습니다")
            results.append(row)
            continue
        best = min(candidates, key=lambda s: abs((s.scheduled_date - t["start"]).total_seconds()))
        used.add(best.id)
        ref = best.arrived_at or best.scheduled_date
        diff = int((t["start"] - ref).total_seconds() // 60)
        row["plan"] = best.scheduled_date.strftime("%H:%M")
        row["arrived"] = best.arrived_at.strftime("%H:%M") if best.arrived_at else None
        row["diff_minutes"] = diff
        row["danger"] = abs(diff) > 60  # 하이케어 안내: 일정계획과 태그 시간 차이가 60분을 넘으면 청구에 쓸 수 없음(일정상이)
        row["plan_minutes"] = best.duration_minutes
        row["caregiver_id"] = best.caregiver_id
        row["caregiver"] = caregivers.get(best.caregiver_id, "")
        notes = []
        status = "ok"
        if abs(diff) > tol:
            status = "time_diff"
            notes.append(f"시작 시각이 {'도착 기록' if best.arrived_at else '계획'}과 {abs(diff)}분 차이")
        if row["tag_minutes"] is not None and best.duration_minutes and abs(row["tag_minutes"] - best.duration_minutes) > tol:
            status = "time_diff"
            notes.append(f"제공 시간 태그 {row['tag_minutes']}분 / 계획 {best.duration_minutes}분")
        if body.end_col is not None and t["end"] is None:
            status = "time_diff"
            notes.append("종료 전송이 없습니다 (자동청구율에서 빠집니다)")
        if t["caregiver"] and caregivers.get(best.caregiver_id) and t["caregiver"] != caregivers[best.caregiver_id]:
            notes.append(f"요양보호사 다름 (태그 {t['caregiver']} / 돌봄케어 {caregivers[best.caregiver_id]})")
            if status == "ok":
                status = "time_diff"
        row.update(status=status, note=", ".join(notes))
        results.append(row)

    now = datetime.now()
    for s in schedules:
        if s.id in used or s.scheduled_date >= now:
            continue
        results.append({"row": None, "name": resident_names.get(s.resident_id, ""), "tag_start": None, "tag_end": None, "tag_minutes": None,
                        "plan": s.scheduled_date.strftime("%Y-%m-%d %H:%M"), "arrived": s.arrived_at.strftime("%H:%M") if s.arrived_at else None,
                        "caregiver_id": s.caregiver_id, "caregiver": caregivers.get(s.caregiver_id, ""),
                        "status": "no_tag", "note": "방문 계획은 있는데 공단 태그 전송내역이 없습니다"})
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    results.sort(key=lambda r: (r["tag_start"] or r["plan"] or ""))
    return {"range": [str(first_day), str(last_day)], "tag_count": len(tags), "counts": counts, "rows": results, "bad_rows": bad_rows[:50],
            "auto_rate": _auto_rate(results, has_end_col=body.end_col is not None),
            "eval_index": _eval_index(results, has_end_col=body.end_col is not None)}


def _auto_rate(results, has_end_col):
    """공단 산식: (총 청구 서비스건수 - (직접 입력건수 + 종료 미전송 건수)) / 총 청구 서비스건수 x 100, 소수점 이하 반올림.
    총 건수는 돌봄케어 방문 계획 중 이미 지난 건(태그와 맞춘 건 + 태그 없는 건). 태그 없는 건은 직접 입력으로 본다.
    자동청구율 75% 이상이면 14일 이내 지급, 아니면 청구일부터 30일 이내."""
    if not has_end_col:
        return None
    matched = [r for r in results if r["row"] is not None and r["plan"]]
    direct = sum(1 for r in results if r["status"] == "no_tag")
    end_missing = sum(1 for r in matched if not r["tag_end"])
    total = len(matched) + direct
    if total == 0:
        return None
    auto = len(matched) - end_missing
    rate = int(auto * 100 / total + 0.5)
    need = max(0, -(-total * 149 // 200) - auto)  # 반올림해서 75가 되는 최소 자동 건수(74.5% 이상)
    return {"total": total, "auto": auto, "direct": direct, "end_missing": end_missing,
            "rate": rate, "meets_75": rate >= 75, "need_more": need}


# 공단 2026 재가급여(방문요양) 평가 매뉴얼 지표 17 '재가급여전자관리시스템(RFID) 활용' (3점): (등급, 점수, 참여율 기준, 청구활용률 기준). 두 기준을 모두 넘어야 그 등급이다.
EVAL_TIERS = [("우수", 3, 95, 90), ("양호", 2.25, 90, 85), ("보통", 1.5, 85, 80)]


def _ceil_percent(percent, total):
    return -(-percent * total // 100)


def _eval_index(results, has_end_col):
    """지표 17의 두 기준을 올린 파일 기간 기준으로 어림한다.
    ① 참여율 = 태그를 한 번이라도 전송한 요양보호사 / 방문 계획이 있는 요양보호사
    ② 청구활용률 = 시작·종료가 모두 전송된 건 / 청구 대상 건 (자동청구율과 같은 건수)
    실제 평가는 공단 전산 자료로 하므로 예상치다."""
    if not has_end_col:
        return None
    stats = {}
    for r in results:
        cid = r.get("caregiver_id")
        if cid is None:
            continue
        s = stats.setdefault(cid, {"name": r.get("caregiver") or "(이름 없음)", "visits": 0, "tagged": 0, "auto": 0, "no_tag": 0, "end_missing": 0})
        s["visits"] += 1
        if r["status"] == "no_tag":
            s["no_tag"] += 1
        else:
            s["tagged"] += 1
            if r["tag_end"]:
                s["auto"] += 1
            else:
                s["end_missing"] += 1
    if not stats:
        return None
    n = len(stats)
    participating = sum(1 for s in stats.values() if s["tagged"])
    total = sum(s["visits"] for s in stats.values())
    auto = sum(s["auto"] for s in stats.values())
    level = next(((label, points) for label, points, part_min, use_min in EVAL_TIERS
                  if participating * 100 >= part_min * n and auto * 100 >= use_min * total), ("미흡", 0))
    tier_labels = [t[0] for t in EVAL_TIERS]
    target = None
    if level[0] != "우수":
        label, points, part_min, use_min = EVAL_TIERS[tier_labels.index(level[0]) - 1] if level[0] in tier_labels else EVAL_TIERS[-1]
        target = {"label": label, "points": points, "part_min": part_min, "use_min": use_min,
                  "need_caregivers": max(0, _ceil_percent(part_min, n) - participating),
                  "need_visits": max(0, _ceil_percent(use_min, total) - auto)}
    caregivers = sorted(stats.values(), key=lambda s: (-(s["no_tag"] + s["end_missing"]), s["name"]))
    return {"caregiver_total": n, "participating": participating, "participation_rate": round(participating * 100 / n, 1),
            "visit_total": total, "auto": auto, "use_rate": round(auto * 100 / total, 1),
            "level": level[0], "points": level[1], "target": target, "caregivers": caregivers}
