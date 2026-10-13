"""직원 교육 기록과 수급자(보호자) 안내 기록.

근거: 공단 2026년 재가급여(방문요양) 평가매뉴얼
- 직원교육(4): 모든 직원에게 운영규정 교육 연 1회 이상, 급여제공지침 교육 연 1회 이상,
  신규직원은 급여제공 시작일(근무시작일)로부터 7일 이내 교육. 필수: 교육일자·교육방법·강사명·참석자명(서명)
- 노인인권보호(13): 모든 직원에게 노인인권교육 반기별 1회 이상(교육일시·강사명·교육내용·교육방법·참석자명(서명)),
  모든 수급자(보호자)에게 8가지 지침(욕창예방·낙상예방·탈수예방·배변도움·관절구축예방·치매예방·감염예방·노인인권보호)
  설명 후 자료 제공
- 직원인권보호(5): 모든 수급자(보호자)에게 연 1회 이상 폭언·폭행·성희롱 예방 및 직원과 수급자의 상호 존중 안내
  (안내일자·안내방법·수급자명·보호자명(관계)), 비대면(우편·문자·이메일)은 발송내역 확인
- 급여제공안내(9): 급여제공범위·급여외행위·직원 인권보호는 시설장(관리자)이 대면으로 안내해야 인정(유선·우편 불인정)
- 질향상노력(7): 요양보호사 역량강화를 위한 인지프로그램 관련 교육 반기별 1회 이상
"""
import json
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_manager
from app.database import get_db
from app.models import Resident, ResidentNotice, TrainingSession, User

router = APIRouter()

# 주기: year=연 1회, half=반기 1회
TOPICS = {
    "operating_rules": {"label": "운영규정 교육", "cadence": "year"},
    "care_guidelines": {"label": "급여제공지침 교육", "cadence": "year"},
    "elder_rights": {"label": "노인인권교육", "cadence": "half"},
    "staff_rights_response": {"label": "직원 인권침해 대응지침 교육", "cadence": "year"},
    "cognitive_program": {"label": "인지프로그램 교육", "cadence": "half"},
}
METHODS = {"self": "자체교육", "external": "외부강사", "online": "온라인"}
NEW_STAFF_TOPICS = ("operating_rules", "care_guidelines")  # 신규직원은 근무 시작 후 7일 이내 교육
NEW_STAFF_DAYS = 7

NOTICE_TYPES = {
    "rights_guide": "노인인권 8가지 지침 제공·설명",
    "staff_respect": "직원 존중(폭언·폭행·성희롱 예방) 안내",
    "service_scope": "급여제공범위·급여외행위·직원 인권보호 안내",
}
NOTICE_METHODS = {"visit": "대면", "mail": "우편", "sms": "문자", "email": "이메일"}
RIGHTS_GUIDE_ITEMS = {
    "pressure_sore": "욕창예방", "fall": "낙상예방", "dehydration": "탈수예방", "toileting": "배변도움",
    "contracture": "관절구축예방", "dementia": "치매예방", "infection": "감염예방", "elder_rights": "노인인권보호",
}
MIN_TEXT = 5


def period_of(topic: str, today: date) -> tuple:
    if TOPICS[topic]["cadence"] == "year":
        return date(today.year, 1, 1), date(today.year, 12, 31)
    return (date(today.year, 1, 1), date(today.year, 6, 30)) if today.month <= 6 else (date(today.year, 7, 1), date(today.year, 12, 31))


def _staff(db: Session, center_id: int) -> List[User]:
    out = []
    for u in db.query(User).filter(User.center_id == center_id, User.role.in_(("center_manager", "caregiver"))).order_by(User.full_name).all():
        if u.is_active is False or (u.employment_status and u.employment_status != "active"):
            continue
        out.append(u)
    return out


class SessionBody(BaseModel):
    topic: str
    session_date: date
    method: str
    instructor: str
    content: str
    attendee_ids: List[int]
    signed_ids: List[int] = []


class NoticeBody(BaseModel):
    resident_id: int
    notice_type: str
    notice_date: date
    method: str
    recipient: str
    items: List[str] = []
    note: Optional[str] = None


def _session_dict(s: TrainingSession, names: dict) -> dict:
    ids = json.loads(s.attendee_ids or "[]")
    signed = set(json.loads(s.signed_ids or "[]"))
    return {
        "id": s.id, "topic": s.topic, "topic_label": TOPICS.get(s.topic, {}).get("label", s.topic),
        "session_date": s.session_date.isoformat(), "method": s.method, "method_label": METHODS.get(s.method, s.method),
        "instructor": s.instructor, "content": s.content,
        "attendees": [{"id": i, "name": names.get(i, "(퇴사)"), "signed": i in signed} for i in ids],
    }


@router.post("/sessions")
def create_session(body: SessionBody, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    if body.topic not in TOPICS:
        raise HTTPException(status_code=400, detail="교육 종류가 올바르지 않습니다")
    if body.method not in METHODS:
        raise HTTPException(status_code=400, detail="교육 방법이 올바르지 않습니다")
    if not body.instructor.strip():
        raise HTTPException(status_code=400, detail="강사명을 입력해 주세요")
    if len(body.content.strip()) < MIN_TEXT:
        raise HTTPException(status_code=400, detail=f"교육내용을 {MIN_TEXT}자 이상 입력해 주세요")
    staff_ids = {u.id for u in db.query(User).filter(User.center_id == actor.center_id).all()}
    if not body.attendee_ids or any(i not in staff_ids for i in body.attendee_ids):
        raise HTTPException(status_code=400, detail="참석자를 한 명 이상 선택해 주세요 (우리 센터 직원만 선택할 수 있습니다)")
    attendees = sorted(set(body.attendee_ids))
    signed = sorted(set(body.signed_ids) & set(attendees))
    row = TrainingSession(
        center_id=actor.center_id, topic=body.topic, session_date=body.session_date, method=body.method,
        instructor=body.instructor.strip(), content=body.content.strip(),
        attendee_ids=json.dumps(attendees), signed_ids=json.dumps(signed), recorded_by=actor.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    names = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}
    return {"status": "success", "data": _session_dict(row, names)}


@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    rows = db.query(TrainingSession).filter(TrainingSession.center_id == actor.center_id).order_by(
        TrainingSession.session_date.desc(), TrainingSession.id.desc()).limit(100).all()
    names = {u.id: u.full_name for u in db.query(User).filter(User.center_id == actor.center_id).all()}
    return {"sessions": [_session_dict(s, names) for s in rows]}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    row = db.query(TrainingSession).filter(TrainingSession.id == session_id, TrainingSession.center_id == actor.center_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="교육 기록을 찾을 수 없습니다")
    db.delete(row)
    db.commit()
    return {"status": "success"}


def training_status(db: Session, center_id: int, today: date) -> dict:
    """교육 종류별로 이번 주기(연/반기)에 아직 교육받지 않은 직원과, 신규직원 7일 이내 교육 누락을 찾는다."""
    staff = _staff(db, center_id)
    sessions = db.query(TrainingSession).filter(TrainingSession.center_id == center_id).all()
    topics = []
    for code, meta in TOPICS.items():
        start, end = period_of(code, today)
        attended = {}
        for s in sessions:
            if s.topic == code and start <= s.session_date <= end:
                for i in json.loads(s.attendee_ids or "[]"):
                    attended[i] = max(attended.get(i, s.session_date), s.session_date)
        missing = []
        for u in staff:
            hired = u.hire_date or (u.created_at.date() if u.created_at else None)
            if hired and hired > end:
                continue
            if u.id not in attended:
                missing.append({"id": u.id, "name": u.full_name})
        topics.append({"topic": code, "label": meta["label"], "cadence": meta["cadence"],
                       "period_start": start.isoformat(), "period_end": end.isoformat(),
                       "done_count": sum(1 for u in staff if u.id in attended), "staff_total": len(staff), "missing": missing})

    new_staff = []
    for u in staff:
        hired = u.hire_date
        if not hired or today < hired:
            continue
        deadline = hired + timedelta(days=NEW_STAFF_DAYS)
        if today - hired > timedelta(days=90):
            continue  # 입사 90일이 지난 직원은 신규 점검 대상에서 제외
        for code in NEW_STAFF_TOPICS:
            done = any(s.topic == code and hired <= s.session_date <= deadline and u.id in json.loads(s.attendee_ids or "[]") for s in sessions)
            if done:
                continue
            new_staff.append({"id": u.id, "name": u.full_name, "topic": code, "label": TOPICS[code]["label"], "hired": hired.isoformat(),
                              "deadline": deadline.isoformat(), "state": "overdue" if today > deadline else "pending"})
    return {"staff": [{"id": u.id, "name": u.full_name} for u in staff], "topics": topics, "new_staff": new_staff,
            "missing_total": sum(len(t["missing"]) for t in topics), "new_staff_overdue": sum(1 for n in new_staff if n["state"] == "overdue")}


@router.get("/status")
def get_training_status(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    return training_status(db, actor.center_id, date.today())


@router.post("/notices")
def create_notice(body: NoticeBody, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    if body.notice_type not in NOTICE_TYPES:
        raise HTTPException(status_code=400, detail="안내 종류가 올바르지 않습니다")
    if body.method not in NOTICE_METHODS:
        raise HTTPException(status_code=400, detail="안내 방법이 올바르지 않습니다")
    resident = db.query(Resident).filter(Resident.id == body.resident_id).first()
    if not resident or resident.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    if not body.recipient.strip():
        raise HTTPException(status_code=400, detail="안내받은 사람(수급자 본인 또는 보호자명(관계))을 입력해 주세요")
    if body.notice_type == "service_scope" and body.method != "visit":
        raise HTTPException(status_code=400, detail="급여제공범위·급여외행위·직원 인권보호 안내는 대면으로 한 경우만 인정됩니다 (유선·우편 불인정)")
    items = []
    if body.notice_type == "rights_guide":
        items = [i for i in body.items if i in RIGHTS_GUIDE_ITEMS]
        missing = [label for code, label in RIGHTS_GUIDE_ITEMS.items() if code not in items]
        if missing:
            raise HTTPException(status_code=400, detail=f"8가지 지침을 모두 설명하고 자료를 제공해야 인정됩니다 (빠진 항목: {', '.join(missing)})")
    row = ResidentNotice(
        center_id=actor.center_id, resident_id=body.resident_id, notice_type=body.notice_type, notice_date=body.notice_date,
        method=body.method, recipient=body.recipient.strip(), items=json.dumps(items), note=(body.note or "").strip() or None, recorded_by=actor.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"status": "success", "data": _notice_dict(row, {resident.id: resident.name})}


def _notice_dict(n: ResidentNotice, names: dict) -> dict:
    return {"id": n.id, "resident_id": n.resident_id, "resident_name": names.get(n.resident_id),
            "notice_type": n.notice_type, "notice_type_label": NOTICE_TYPES.get(n.notice_type, n.notice_type),
            "notice_date": n.notice_date.isoformat(), "method": n.method, "method_label": NOTICE_METHODS.get(n.method, n.method),
            "recipient": n.recipient, "note": n.note}


@router.get("/notices")
def list_notices(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    rows = db.query(ResidentNotice).filter(ResidentNotice.center_id == actor.center_id).order_by(
        ResidentNotice.notice_date.desc(), ResidentNotice.id.desc()).limit(200).all()
    names = {r.id: r.name for r in db.query(Resident).filter(Resident.center_id == actor.center_id).all()}
    return {"notices": [_notice_dict(n, names) for n in rows]}


@router.delete("/notices/{notice_id}")
def delete_notice(notice_id: int, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    row = db.query(ResidentNotice).filter(ResidentNotice.id == notice_id, ResidentNotice.center_id == actor.center_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="안내 기록을 찾을 수 없습니다")
    db.delete(row)
    db.commit()
    return {"status": "success"}


def notice_status(db: Session, center_id: int, today: date) -> dict:
    """이용자별로 올해 필요한 안내 중 아직 기록이 없는 것을 찾는다 (노인인권 지침·직원 존중 안내: 연 1회, 급여제공범위 안내: 한 번이라도)."""
    year_start = date(today.year, 1, 1)
    notices = db.query(ResidentNotice).filter(ResidentNotice.center_id == center_id).all()
    rows = []
    for r in db.query(Resident).filter(Resident.center_id == center_id).order_by(Resident.name).all():
        mine = [n for n in notices if n.resident_id == r.id]
        missing = []
        for code in ("rights_guide", "staff_respect"):
            if not any(n.notice_type == code and n.notice_date >= year_start for n in mine):
                missing.append({"type": code, "label": NOTICE_TYPES[code]})
        if not any(n.notice_type == "service_scope" for n in mine):
            missing.append({"type": "service_scope", "label": NOTICE_TYPES["service_scope"]})
        rows.append({"id": r.id, "name": r.name, "missing": missing})
    return {"year": today.year, "residents": rows, "residents_missing": sum(1 for r in rows if r["missing"])}


@router.get("/notices/status")
def get_notice_status(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    return notice_status(db, actor.center_id, date.today())


@router.get("/options")
def get_options(actor: User = Depends(require_manager)):
    return {"topics": {k: v["label"] for k, v in TOPICS.items()}, "methods": METHODS, "notice_types": NOTICE_TYPES,
            "notice_methods": NOTICE_METHODS, "rights_guide_items": RIGHTS_GUIDE_ITEMS}
