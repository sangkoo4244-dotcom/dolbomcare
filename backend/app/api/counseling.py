"""상담 기록 - 방문상담관리(수급자·보호자 월 1회), 직원 상담관리(요양보호사 월 1회),
담당 요양보호사 변경 후 14일 이내 상담.

근거: 공단 2026년 재가급여(방문요양) 평가매뉴얼 방문요양 2·10·18번 지표.
- 상담은 대면 또는 유선만 인정(문자·SNS 불인정)
- 상담내용이 '특이사항 없음', '지난달과 동일' 처럼 내용이 확인되지 않으면 불인정
- 신규 직원은 급여제공 시작 월의 다음 달부터 월 1회 상담 대상
- 직원 변경 후 상담은 변경일(새 직원의 급여개시일)부터 토요일·공휴일 포함 14일 이내
  (A→B→A처럼 14일 안에 원래 직원으로 돌아오면 상담 불필요)
"""
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_manager, require_social_or_manager
from app.database import get_db
from app.models import Counseling, Resident, Schedule, User

router = APIRouter()

KINDS = {"resident": "수급자(보호자) 방문상담", "staff": "직원 상담"}
METHODS = {"visit": "대면", "phone": "유선"}
REASONS = {"monthly": "정기", "caregiver_change": "담당 요양보호사 변경"}
MIN_CONTENT_LEN = 10
TRIVIAL_CONTENT = {"특이사항없음", "지난달과동일", "지난달동일", "전월과동일", "없음", "동일", "이상없음", "변동없음"}
CHANGE_WINDOW_DAYS = 14


def _normalize(text: str) -> str:
    return "".join((text or "").split()).rstrip(".")


def validate_content(content: str) -> Optional[str]:
    """내용이 평가에서 인정되지 않을 만큼 부실하면 이유를 돌려준다."""
    c = (content or "").strip()
    if _normalize(c) in TRIVIAL_CONTENT:
        return "'특이사항 없음'처럼 내용이 확인되지 않는 문구는 평가에서 인정되지 않습니다. 상태·욕구·건의사항을 구체적으로 적어 주세요"
    if len(c) < MIN_CONTENT_LEN:
        return f"상담 내용을 {MIN_CONTENT_LEN}자 이상 구체적으로 적어 주세요 (상태, 욕구, 건의사항 등)"
    return None


def _to_dict(c: Counseling, names: dict) -> dict:
    return {
        "id": c.id,
        "kind": c.kind,
        "kind_label": KINDS.get(c.kind, c.kind),
        "resident_id": c.resident_id,
        "resident_name": names.get(("r", c.resident_id)),
        "staff_id": c.staff_id,
        "staff_name": names.get(("u", c.staff_id)),
        "counselor_name": names.get(("u", c.counselor_id)),
        "counselee_name": c.counselee_name,
        "counsel_date": c.counsel_date.isoformat() if c.counsel_date else None,
        "method": c.method,
        "method_label": METHODS.get(c.method, c.method),
        "reason": c.reason,
        "reason_label": REASONS.get(c.reason, c.reason),
        "content": c.content,
        "action_needed": bool(c.action_needed),
        "action_note": c.action_note,
        "action_done_date": c.action_done_date.isoformat() if c.action_done_date else None,
    }


def _names(db: Session, center_id: int) -> dict:
    names = {}
    for r in db.query(Resident).filter(Resident.center_id == center_id).all():
        names[("r", r.id)] = r.name
    for u in db.query(User).filter(User.center_id == center_id).all():
        names[("u", u.id)] = u.full_name
    return names


class CounselingBody(BaseModel):
    kind: str
    resident_id: Optional[int] = None
    staff_id: Optional[int] = None
    counselee_name: Optional[str] = None
    counsel_date: date
    method: str = "visit"
    reason: Optional[str] = "monthly"
    content: str
    action_needed: bool = False
    action_note: Optional[str] = None


class ActionBody(BaseModel):
    action_note: Optional[str] = None
    action_done_date: Optional[date] = None


def _month_range(month: str):
    try:
        start = datetime.strptime(month + "-01", "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="월 형식이 올바르지 않습니다 (YYYY-MM)")
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start, end


@router.post("")
def create_counseling(body: CounselingBody, db: Session = Depends(get_db), actor: User = Depends(require_social_or_manager)):
    if body.kind not in KINDS:
        raise HTTPException(status_code=400, detail="상담 종류가 올바르지 않습니다")
    if body.method not in METHODS:
        raise HTTPException(status_code=400, detail="상담 방법은 대면 또는 유선만 인정됩니다")
    if body.reason and body.reason not in REASONS:
        raise HTTPException(status_code=400, detail="상담 사유가 올바르지 않습니다")
    problem = validate_content(body.content)
    if problem:
        raise HTTPException(status_code=400, detail=problem)

    if body.kind == "resident":
        resident = db.query(Resident).filter(Resident.id == body.resident_id).first()
        if not resident or resident.center_id != actor.center_id:
            raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
        if not (body.counselee_name or "").strip():
            raise HTTPException(status_code=400, detail="상담대상자명(관계)을 입력해 주세요 (예: 김영희(딸))")
    else:
        staff = db.query(User).filter(User.id == body.staff_id).first()
        if not staff or staff.center_id != actor.center_id or staff.role != "caregiver":
            raise HTTPException(status_code=404, detail="요양보호사를 찾을 수 없습니다")

    row = Counseling(
        center_id=actor.center_id,
        kind=body.kind,
        resident_id=body.resident_id if body.kind == "resident" else None,
        staff_id=body.staff_id if body.kind == "staff" else None,
        counselor_id=actor.id,
        counselee_name=(body.counselee_name or "").strip() or None,
        counsel_date=body.counsel_date,
        method=body.method,
        reason=body.reason,
        content=body.content.strip(),
        action_needed=body.action_needed,
        action_note=body.action_note,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"status": "success", "data": _to_dict(row, _names(db, actor.center_id))}


@router.get("")
def list_counselings(
    kind: Optional[str] = None,
    month: Optional[str] = None,
    resident_id: Optional[int] = None,
    db: Session = Depends(get_db),
    actor: User = Depends(require_social_or_manager),
):
    q = db.query(Counseling).filter(Counseling.center_id == actor.center_id)
    if kind:
        q = q.filter(Counseling.kind == kind)
    if resident_id:
        q = q.filter(Counseling.resident_id == resident_id)
    if month:
        start, end = _month_range(month)
        q = q.filter(Counseling.counsel_date >= start, Counseling.counsel_date < end)
    rows = q.order_by(Counseling.counsel_date.desc(), Counseling.id.desc()).limit(300).all()
    names = _names(db, actor.center_id)
    return {"counselings": [_to_dict(r, names) for r in rows]}


@router.put("/{counseling_id}/action")
def record_action(counseling_id: int, body: ActionBody, db: Session = Depends(get_db), actor: User = Depends(require_social_or_manager)):
    """조치가 필요했던 상담에 조치 내용과 반영일을 남긴다 (직원 상담결과는 반기별 1회 이상 기관운영 등에 반영해야 함)."""
    row = db.query(Counseling).filter(Counseling.id == counseling_id, Counseling.center_id == actor.center_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="상담 기록을 찾을 수 없습니다")
    row.action_note = body.action_note
    row.action_done_date = body.action_done_date
    db.commit()
    return {"status": "success", "data": _to_dict(row, _names(db, actor.center_id))}


@router.delete("/{counseling_id}")
def delete_counseling(counseling_id: int, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    row = db.query(Counseling).filter(Counseling.id == counseling_id, Counseling.center_id == actor.center_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="상담 기록을 찾을 수 없습니다")
    db.delete(row)
    db.commit()
    return {"status": "success"}


def monthly_status(db: Session, center_id: int, month: str) -> dict:
    """그 달에 상담이 한 번이라도 있는 수급자·요양보호사와 아직 없는 대상을 나눠 돌려준다."""
    start, end = _month_range(month)
    rows = db.query(Counseling).filter(
        Counseling.center_id == center_id, Counseling.counsel_date >= start, Counseling.counsel_date < end
    ).all()
    resident_done = {}
    staff_done = {}
    for c in rows:
        if c.kind == "resident" and c.resident_id:
            resident_done[c.resident_id] = max(resident_done.get(c.resident_id, c.counsel_date), c.counsel_date)
        if c.kind == "staff" and c.staff_id:
            staff_done[c.staff_id] = max(staff_done.get(c.staff_id, c.counsel_date), c.counsel_date)

    residents = [
        {"id": r.id, "name": r.name, "done": r.id in resident_done,
         "last_date": resident_done[r.id].isoformat() if r.id in resident_done else None}
        for r in db.query(Resident).filter(Resident.center_id == center_id).order_by(Resident.name).all()
    ]
    staff = []
    for u in db.query(User).filter(User.center_id == center_id, User.role == "caregiver").order_by(User.full_name).all():
        if u.is_active is False or (u.employment_status and u.employment_status != "active"):
            continue
        started = u.hire_date or (u.created_at.date() if u.created_at else None)
        if started and started >= start:  # 신규 직원은 시작 월의 다음 달부터
            continue
        staff.append({"id": u.id, "name": u.full_name, "done": u.id in staff_done,
                      "last_date": staff_done[u.id].isoformat() if u.id in staff_done else None})
    return {"month": month, "residents": residents, "staff": staff,
            "residents_missing": sum(1 for r in residents if not r["done"]),
            "staff_missing": sum(1 for s in staff if not s["done"])}


@router.get("/status")
def get_status(month: Optional[str] = None, db: Session = Depends(get_db), actor: User = Depends(require_social_or_manager)):
    return monthly_status(db, actor.center_id, month or date.today().strftime("%Y-%m"))


def detect_caregiver_changes(db: Session, center_id: int, today: date, lookback_days: int = 90) -> list:
    """수급자별 일정에서 담당 요양보호사가 바뀐 시점을 찾아, 14일 이내 상담 여부를 판정한다."""
    since = datetime.combine(today - timedelta(days=lookback_days + CHANGE_WINDOW_DAYS), datetime.min.time())
    until = datetime.combine(today + timedelta(days=1), datetime.min.time())
    schedules = db.query(Schedule).filter(
        Schedule.center_id == center_id, Schedule.scheduled_date >= since, Schedule.scheduled_date < until,
        Schedule.status.in_(("scheduled", "completed")),
    ).order_by(Schedule.resident_id, Schedule.scheduled_date).all()
    names = _names(db, center_id)
    counsels = db.query(Counseling).filter(Counseling.center_id == center_id, Counseling.kind == "resident").all()

    by_resident = {}
    for s in schedules:
        by_resident.setdefault(s.resident_id, []).append(s)

    results = []
    for rid, items in by_resident.items():
        runs = []  # [(caregiver_id, 시작일)]
        for s in items:
            if not runs or runs[-1][0] != s.caregiver_id:
                runs.append((s.caregiver_id, s.scheduled_date.date()))
        for i in range(1, len(runs)):
            cg, start = runs[i]
            if start < today - timedelta(days=lookback_days):
                continue
            deadline = start + timedelta(days=CHANGE_WINDOW_DAYS)
            # 14일 안에 원래 직원으로 돌아온 경우는 상담하지 않아도 된다
            if i + 1 < len(runs) and runs[i + 1][0] == runs[i - 1][0] and (runs[i + 1][1] - start).days < CHANGE_WINDOW_DAYS:
                continue
            # 14일 안에 직전 직원이 아니라 그 앞의 원래 직원으로 재교체된 경우도 상담하지 않아도 된다
            if i >= 2 and runs[i][0] == runs[i - 2][0] and (start - runs[i - 1][1]).days < CHANGE_WINDOW_DAYS:
                continue
            done = any(c.resident_id == rid and start <= c.counsel_date <= deadline for c in counsels)
            if done:
                status = "done"
            elif today > deadline:
                status = "overdue"
            else:
                status = "pending"
            results.append({
                "resident_id": rid, "resident_name": names.get(("r", rid)),
                "from_caregiver": names.get(("u", runs[i - 1][0])), "to_caregiver": names.get(("u", cg)),
                "changed_on": start.isoformat(), "deadline": deadline.isoformat(),
                "days_left": (deadline - today).days, "status": status,
            })
    results.sort(key=lambda r: r["deadline"])
    return results


@router.get("/caregiver-changes")
def get_caregiver_changes(db: Session = Depends(get_db), actor: User = Depends(require_social_or_manager)):
    changes = detect_caregiver_changes(db, actor.center_id, date.today())
    return {"changes": changes, "overdue": sum(1 for c in changes if c["status"] == "overdue"),
            "pending": sum(1 for c in changes if c["status"] == "pending")}
