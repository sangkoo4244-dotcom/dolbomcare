"""직원 본인 화면: 내 건강검진·보수교육·연차 상태와 고충 접수. 센터장은 전체 현황과 고충 처리를 맡는다."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_manager
from app.database import get_db
from app.education import status_for
from app.api.notifications import notify
from app.models import Notification, StaffRecord, User

router = APIRouter()
SELF_TYPES = {"health_checkup": "건강검진", "continuing_education": "보수교육", "annual_leave": "연차·유급휴일"}
PRIVATE_NOTE = "퇴직적립금은 개인 정산 자료라 이 화면에 보여 주지 않습니다"


class GrievanceBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    detail: Optional[str] = Field(None, max_length=2000)


class StatusBody(BaseModel):
    status: str  # open / resolved


def _item(r: StaffRecord) -> dict:
    return {"id": r.id, "record_date": r.record_date.isoformat() if r.record_date else None, "title": r.title,
            "detail": r.detail, "status": r.status, "amount": r.amount}


def _is_caregiver_for_education(u: User) -> bool:
    return (u.job_type or "요양보호사") == "요양보호사" and u.role == "caregiver"


def _remind_due(db: Session, user: User, st: Optional[dict]) -> None:
    """이수 기한이 올해인 요양보호사에게 한 번만 알림을 남긴다 (같은 해 같은 문구는 중복 저장하지 않음)."""
    if not st or st.get("state") != "due" or not st.get("due_year"):
        return
    msg = f"{st['due_year']}년 보수교육 이수가 필요합니다. 센터 교육 일정을 확인해 주세요."
    exists = db.query(Notification).filter(Notification.user_id == user.id, Notification.kind == "education_due", Notification.message == msg).first()
    if not exists:
        notify(db, user.id, "education_due", msg)
        db.commit()


def _education(u: User, db: Session, today: date) -> Optional[dict]:
    if not _is_caregiver_for_education(u):
        return None
    rows = db.query(StaffRecord).filter(StaffRecord.staff_id == u.id, StaffRecord.record_type == "continuing_education").all()
    exempt = any((r.status or "") == "exempt" for r in rows)
    dates = [r.record_date for r in rows if r.record_date and (r.status or "") != "exempt"]
    return status_for(u.birth_date, u.hire_date, dates, exempt, today)


@router.get("/me")
def my_records(db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role not in ("caregiver", "social_worker") or not actor.center_id:
        raise HTTPException(status_code=403, detail="직원만 볼 수 있습니다")
    rows = db.query(StaffRecord).filter(StaffRecord.staff_id == actor.id).order_by(StaffRecord.record_date.desc(), StaffRecord.id.desc()).all()
    out = {code: [] for code in SELF_TYPES}
    grievances = []
    for r in rows:
        if r.record_type in out:
            out[r.record_type].append(_item(r))
        elif r.record_type == "grievance":
            grievances.append(_item(r))
    today = date.today()
    edu = _education(actor, db, today)
    _remind_due(db, actor, edu)
    return {"status": "success", "data": {
        "education": edu,
        "records": {code: {"label": label, "items": out[code]} for code, label in SELF_TYPES.items()},
        "grievances": grievances,
        "note": PRIVATE_NOTE,
    }}


@router.post("/grievance")
def submit_grievance(body: GrievanceBody, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    if actor.role not in ("caregiver", "social_worker") or not actor.center_id:
        raise HTTPException(status_code=403, detail="직원만 고충을 접수할 수 있습니다")
    row = StaffRecord(staff_id=actor.id, record_type="grievance", record_date=date.today(), title=body.title.strip(),
                      detail=(body.detail or "").strip() or None, status="open", recorded_by=actor.id)
    db.add(row)
    db.commit()
    return {"status": "success", "data": _item(row)}


@router.get("/education-status")
def center_education_status(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    """센터장: 보수교육 대상 요양보호사별 상태와 이수 필요 명단."""
    today = date.today()
    staff = db.query(User).filter(User.center_id == actor.center_id, User.role == "caregiver").all()
    rows = []
    for u in staff:
        st = _education(u, db, today)
        if st is None:
            continue
        _remind_due(db, u, st)
        rows.append({"staff_id": u.id, "name": u.full_name, **st})
    return {"status": "success", "data": {
        "staff": rows,
        "needs_action": [r for r in rows if r["state"] in ("due", "birth_missing")],
    }}


@router.put("/grievance/{record_id}/status")
def update_grievance(record_id: int, body: StatusBody, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    if body.status not in ("open", "resolved"):
        raise HTTPException(status_code=400, detail="상태는 open 또는 resolved 입니다")
    row = db.query(StaffRecord).filter(StaffRecord.id == record_id, StaffRecord.record_type == "grievance").first()
    staff = db.query(User).filter(User.id == row.staff_id, User.center_id == actor.center_id).first() if row else None
    if not row or not staff:
        raise HTTPException(status_code=404, detail="고충을 찾을 수 없습니다")
    row.status = body.status
    db.commit()
    return {"status": "success", "data": _item(row)}


@router.get("/grievances")
def center_grievances(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    """센터장: 우리 센터 직원이 접수한 고충 전체 (접수 순서 최신순)."""
    rows = db.query(StaffRecord).filter(StaffRecord.record_type == "grievance").order_by(StaffRecord.id.desc()).all()
    names = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}
    return {"status": "success", "data": [
        {**_item(r), "staff_name": names[r.staff_id]} for r in rows if r.staff_id in names
    ]}


@router.get("/career-ratio")
def career_ratio(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    """센터장: 경력직 비율 (지표적용기간 2023.1~2025.12). 근무 월은 입·퇴사일과 요양보호사의 실제 급여제공 월로 산정."""
    from app.career import compute, employment_months, WINDOW_START, WINDOW_END
    from app.models import DailyRecord, Center
    staff = db.query(User).filter(User.center_id == actor.center_id, User.role.in_(("caregiver", "center_manager", "social_worker"))).all()
    service_months = {}
    for r in db.query(DailyRecord).join(User, User.id == DailyRecord.caregiver_id).filter(User.center_id == actor.center_id).all():
        service_months.setdefault(r.caregiver_id, set()).add((r.recorded_date.year, r.recorded_date.month))
    rows = []
    for u in staff:
        if u.role == "caregiver" and (u.job_type or "요양보호사") == "요양보호사":
            months = service_months.get(u.id, set())  # 급여제공 직원은 실제 급여제공 월만
        else:
            months = employment_months(u.hire_date, u.leave_date)
        rows.append({"name": u.full_name, "months": months, "excluded": bool(u.career_excluded)})
    firsts = [min(ms) for ms in service_months.values() if ms]
    first = min(firsts) if firsts else None
    operated = 0
    if first:
        operated = (WINDOW_END[0] - first[0]) * 12 + (WINDOW_END[1] - first[1]) + 1
    return {"status": "success", "data": compute(rows, operated)}


@router.get("/publication-check")
def publication_check(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    """인력현황 게시 점검 (2026 방문요양 평가 '기관정보 게시' 지표). 센터 정보로 확인되는 항목은 자동 표시, 나머지는 센터장이 직접 확인."""
    from app.models import Center
    center = db.query(Center).filter(Center.id == actor.center_id).first()
    staff_count = db.query(User).filter(User.center_id == actor.center_id, User.role.in_(("caregiver", "center_manager", "social_worker"))).count()
    types = (center.service_types or "") if center else ""
    items = [
        {"group": "내부 게시 (현장)", "name": "운영규정 개요", "auto": False},
        {"group": "내부 게시 (현장)", "name": "직원 근무체계 (인력현황표)", "auto": staff_count > 0, "value": f"직원 {staff_count}명"},
        {"group": "내부 게시 (현장)", "name": "제공하는 장기요양급여 종류", "auto": bool(types), "value": types},
        {"group": "내부 게시 (현장)", "name": "노인학대 신고기관", "auto": False},
        {"group": "내부 게시 (현장)", "name": "전문인 배상책임보험 증서 사본", "auto": False},
        {"group": "내부 게시 (현장)", "name": "최종 장기요양기관 평가결과", "auto": False},
        {"group": "공단 홈페이지 (시군구 신고 항목)", "name": "주소", "auto": bool(center and center.address), "value": center.address if center else None},
        {"group": "공단 홈페이지 (시군구 신고 항목)", "name": "전화번호", "auto": bool(center and center.phone), "value": center.phone if center else None},
        {"group": "공단 홈페이지 (시군구 신고 항목)", "name": "인력현황", "auto": staff_count > 0, "value": f"직원 {staff_count}명"},
        {"group": "공단 홈페이지 (시군구 신고 항목)", "name": "시설현황", "auto": False},
        {"group": "공단 홈페이지 (시군구 신고 항목)", "name": "급여종류", "auto": bool(types), "value": types},
        {"group": "공단 홈페이지 (등록 항목)", "name": "장기요양급여 이용계약 관련 사항", "auto": False},
        {"group": "공단 홈페이지 (등록 항목)", "name": "사진", "auto": bool(center and center.logo_image)},
        {"group": "공단 홈페이지 (등록 항목)", "name": "홈페이지 주소", "auto": False},
        {"group": "공단 홈페이지 (등록 항목)", "name": "교통편·주차시설", "auto": False},
        {"group": "공단 홈페이지 (등록 항목)", "name": "보험가입 여부", "auto": False},
    ]
    return {"status": "success", "data": {
        "items": items,
        "rule": "직원·주소·급여종류가 바뀌면 지체 없이 공단 홈페이지도 수정해야 합니다 (기관정보 변경 시 즉시 수정).",
        "note": "자동 표시는 센터 정보 기준입니다. '직접 확인'은 현장 서류와 공단 홈페이지 게시 상태를 센터장이 확인해 주세요.",
    }}
