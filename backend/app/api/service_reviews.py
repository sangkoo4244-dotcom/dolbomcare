"""급여제공 결과평가(반기별)와 사례관리 회의(분기별).

근거: 공단 2026년 재가급여(방문요양) 평가매뉴얼 방문요양 23(급여제공 결과평가)·22(사례관리).

[결과평가]
- 수급자별 급여제공계획에 따른 결과를 반기(1~6월, 7~12월)마다 1회 이상 평가, 필수사항: 일자·총평(종합소견)·작성자명
- 신규수급자는 급여제공 시작일이 속한 반기는 확인하지 않고 다음 반기부터 확인
- 평가결과를 반영해 평가일 후 30일 이내에 급여제공계획서를 재작성. 수급자 상태 변화가 없으면 총평에
  '상태가 동일하다는 판단근거'를 적고 재작성하지 않아도 예외로 인정

[사례관리 회의]
- 분기별 1회 이상. 필수사항: 일자·수급자명·선정사유·회의내용(참가 직원별 의견 필수)·사례관리 계획·참석자명(서명)
- 시설장 및 직종별 1인 이상, 총 3인 이상 참여 (요양보호사만 있는 센터는 시설장+요양보호사 2인 이상)
- 회의 다음날부터 30일 이내에 급여 등에 반영하고 평가(평가일자·작성자명·선정사유 해결여부·미해결 시 추가 조치 계획)
"""
import json
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import require_manager
from app.database import get_db
from app.models import CarePlan, CaseConference, Resident, ServiceEvaluation, User

router = APIRouter()

FOLLOW_UP_DAYS = 30
MIN_ATTENDEES = 3
MIN_TEXT = 5


def half_of(d: date) -> tuple:
    return (d.year, 1 if d.month <= 6 else 2)


def half_range(year: int, half: int) -> tuple:
    return (date(year, 1, 1), date(year, 6, 30)) if half == 1 else (date(year, 7, 1), date(year, 12, 31))


def quarter_range(d: date) -> tuple:
    q = (d.month - 1) // 3
    start = date(d.year, q * 3 + 1, 1)
    end = date(d.year + (1 if q == 3 else 0), 1 if q == 3 else q * 3 + 4, 1) - timedelta(days=1)
    return start, end


def _need_text(label: str, value: Optional[str]):
    if len((value or "").strip()) < MIN_TEXT:
        raise HTTPException(status_code=400, detail=f"{label}을(를) {MIN_TEXT}자 이상 구체적으로 입력해 주세요")


# ---------------- 급여제공 결과평가 ----------------

class EvaluationBody(BaseModel):
    resident_id: int
    evaluated_date: date
    summary: str
    status_changed: bool = True
    no_change_basis: Optional[str] = None


def _follow_up(db: Session, ev: ServiceEvaluation, today: date) -> dict:
    """평가일 후 30일 이내에 급여제공계획서를 재작성했는지(또는 상태 동일 근거를 적었는지) 판정한다."""
    deadline = ev.evaluated_date + timedelta(days=FOLLOW_UP_DAYS)
    plan = db.query(CarePlan).filter(
        CarePlan.resident_id == ev.resident_id, CarePlan.written_date >= ev.evaluated_date, CarePlan.written_date <= deadline,
    ).order_by(CarePlan.written_date).first()
    if plan:
        state, label = "done", f"{plan.written_date} 계획서 재작성"
    elif not ev.status_changed and (ev.no_change_basis or "").strip():
        state, label = "done", "상태 변화 없음(판단 근거 기록)"
    elif today > deadline:
        state, label = "overdue", f"재작성 기한({deadline}) 초과"
    else:
        state, label = "pending", f"재작성 기한 {deadline} (D-{(deadline - today).days})"
    return {"state": state, "label": label, "deadline": deadline.isoformat()}


def _ev_dict(ev: ServiceEvaluation, db: Session, names: dict, today: date) -> dict:
    return {
        "id": ev.id, "resident_id": ev.resident_id, "resident_name": names.get(("r", ev.resident_id)),
        "evaluated_date": ev.evaluated_date.isoformat(), "author_name": names.get(("u", ev.author_id)),
        "summary": ev.summary, "status_changed": bool(ev.status_changed), "no_change_basis": ev.no_change_basis,
        "follow_up": _follow_up(db, ev, today),
    }


def _names(db: Session, center_id: int) -> dict:
    names = {}
    for r in db.query(Resident).filter(Resident.center_id == center_id).all():
        names[("r", r.id)] = r.name
    for u in db.query(User).filter(User.center_id == center_id).all():
        names[("u", u.id)] = u.full_name
    return names


@router.post("/evaluations")
def create_evaluation(body: EvaluationBody, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    resident = db.query(Resident).filter(Resident.id == body.resident_id).first()
    if not resident or resident.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    _need_text("총평(종합소견)", body.summary)
    if not body.status_changed:
        _need_text("상태가 동일하다고 판단한 근거", body.no_change_basis)
    ev = ServiceEvaluation(
        center_id=actor.center_id, resident_id=body.resident_id, evaluated_date=body.evaluated_date, author_id=actor.id,
        summary=body.summary.strip(), status_changed=body.status_changed,
        no_change_basis=(body.no_change_basis or "").strip() or None,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return {"status": "success", "data": _ev_dict(ev, db, _names(db, actor.center_id), date.today())}


@router.get("/evaluations")
def list_evaluations(resident_id: Optional[int] = None, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    q = db.query(ServiceEvaluation).filter(ServiceEvaluation.center_id == actor.center_id)
    if resident_id:
        q = q.filter(ServiceEvaluation.resident_id == resident_id)
    rows = q.order_by(ServiceEvaluation.evaluated_date.desc(), ServiceEvaluation.id.desc()).limit(200).all()
    names = _names(db, actor.center_id)
    return {"evaluations": [_ev_dict(e, db, names, date.today()) for e in rows]}


@router.delete("/evaluations/{ev_id}")
def delete_evaluation(ev_id: int, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    ev = db.query(ServiceEvaluation).filter(ServiceEvaluation.id == ev_id, ServiceEvaluation.center_id == actor.center_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail="평가 기록을 찾을 수 없습니다")
    db.delete(ev)
    db.commit()
    return {"status": "success"}


def evaluation_status(db: Session, center_id: int, today: date) -> dict:
    """이번 반기에 결과평가를 실시했는지(수급자별)와 재작성 기한이 지난 평가를 돌려준다."""
    year, half = half_of(today)
    start, end = half_range(year, half)
    evs = db.query(ServiceEvaluation).filter(ServiceEvaluation.center_id == center_id).all()
    done = {}
    for e in evs:
        if start <= e.evaluated_date <= end:
            done[e.resident_id] = max(done.get(e.resident_id, e.evaluated_date), e.evaluated_date)
    residents = []
    for r in db.query(Resident).filter(Resident.center_id == center_id).order_by(Resident.name).all():
        admitted = r.admission_date.date() if hasattr(r.admission_date, "date") and r.admission_date else None
        if admitted and start <= admitted <= end:  # 신규수급자는 급여 시작이 속한 반기를 확인하지 않음
            continue
        residents.append({"id": r.id, "name": r.name, "done": r.id in done,
                          "last_date": done[r.id].isoformat() if r.id in done else None})
    overdue = [e for e in evs if _follow_up(db, e, today)["state"] == "overdue"]
    return {"year": year, "half": half, "start": start.isoformat(), "end": end.isoformat(), "residents": residents,
            "missing": sum(1 for r in residents if not r["done"]), "overdue_follow_up": len(overdue)}


@router.get("/evaluations/status")
def get_evaluation_status(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    return evaluation_status(db, actor.center_id, date.today())


# ---------------- 사례관리 회의 ----------------

class Attendee(BaseModel):
    name: str
    role: str
    opinion: str  # 의견이 없으면 '의견없음'이라고 적어야 한다
    signed: bool = False


class ConferenceBody(BaseModel):
    resident_id: int
    conference_date: date
    reason: str
    content: str
    plan: str
    attendees: List[Attendee]


class ConferenceFollowUp(BaseModel):
    reflected_date: Optional[date] = None
    reflected_note: Optional[str] = None
    evaluated_date: Optional[date] = None
    evaluator_name: Optional[str] = None
    resolved: Optional[bool] = None
    next_action: Optional[str] = None


def check_attendees(attendees: List[Attendee]):
    if len(attendees) < MIN_ATTENDEES:
        raise HTTPException(status_code=400, detail=f"사례관리 회의는 총 {MIN_ATTENDEES}인 이상 참석해야 인정됩니다")
    for a in attendees:
        if not a.name.strip() or not a.role.strip():
            raise HTTPException(status_code=400, detail="참석자의 이름과 직종을 모두 입력해 주세요")
        if not a.opinion.strip():
            raise HTTPException(status_code=400, detail=f"{a.name}님의 의견을 입력해 주세요 (의견이 없으면 '의견없음'이라고 적어야 합니다)")
    if not any("시설장" in a.role or "센터장" in a.role for a in attendees):
        raise HTTPException(status_code=400, detail="참석자에 시설장(센터장)이 포함되어야 합니다")
    if len({a.name.strip() for a in attendees}) < len(attendees):
        raise HTTPException(status_code=400, detail="같은 이름의 참석자가 중복되어 있습니다")


def _conf_follow_up(c: CaseConference, today: date) -> dict:
    deadline = c.conference_date + timedelta(days=FOLLOW_UP_DAYS)
    if c.reflected_date and c.evaluated_date and c.resolved is not None:
        late = c.reflected_date > deadline
        return {"state": "late" if late else "done", "deadline": deadline.isoformat(),
                "label": "반영·평가 완료" + (" (반영이 30일을 넘김)" if late else "")}
    state = "overdue" if today > deadline else "pending"
    missing = []
    if not c.reflected_date:
        missing.append("급여 반영")
    if not c.evaluated_date or c.resolved is None:
        missing.append("평가(해결 여부)")
    return {"state": state, "deadline": deadline.isoformat(),
            "label": f"{' · '.join(missing)} 필요, 기한 {deadline}" + (f" (D-{(deadline - today).days})" if state == "pending" else " 초과")}


def _conf_dict(c: CaseConference, names: dict, today: date) -> dict:
    return {
        "id": c.id, "resident_id": c.resident_id, "resident_name": names.get(("r", c.resident_id)),
        "conference_date": c.conference_date.isoformat(), "author_name": names.get(("u", c.author_id)),
        "reason": c.reason, "content": c.content, "plan": c.plan, "attendees": json.loads(c.attendees or "[]"),
        "reflected_date": c.reflected_date.isoformat() if c.reflected_date else None, "reflected_note": c.reflected_note,
        "evaluated_date": c.evaluated_date.isoformat() if c.evaluated_date else None, "evaluator_name": c.evaluator_name,
        "resolved": c.resolved, "next_action": c.next_action, "follow_up": _conf_follow_up(c, today),
    }


@router.post("/conferences")
def create_conference(body: ConferenceBody, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    resident = db.query(Resident).filter(Resident.id == body.resident_id).first()
    if not resident or resident.center_id != actor.center_id:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")
    _need_text("선정사유", body.reason)
    _need_text("회의내용", body.content)
    _need_text("사례관리 계획", body.plan)
    check_attendees(body.attendees)
    c = CaseConference(
        center_id=actor.center_id, resident_id=body.resident_id, conference_date=body.conference_date, author_id=actor.id,
        reason=body.reason.strip(), content=body.content.strip(), plan=body.plan.strip(),
        attendees=json.dumps([a.dict() for a in body.attendees], ensure_ascii=False),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"status": "success", "data": _conf_dict(c, _names(db, actor.center_id), date.today())}


@router.get("/conferences")
def list_conferences(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    rows = db.query(CaseConference).filter(CaseConference.center_id == actor.center_id).order_by(
        CaseConference.conference_date.desc(), CaseConference.id.desc()).limit(100).all()
    names = _names(db, actor.center_id)
    return {"conferences": [_conf_dict(c, names, date.today()) for c in rows]}


@router.put("/conferences/{conf_id}/follow-up")
def update_follow_up(conf_id: int, body: ConferenceFollowUp, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    c = db.query(CaseConference).filter(CaseConference.id == conf_id, CaseConference.center_id == actor.center_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="회의 기록을 찾을 수 없습니다")
    if body.reflected_date is not None:
        if body.reflected_date <= c.conference_date:
            raise HTTPException(status_code=400, detail="급여 반영일은 회의 다음날부터 인정됩니다")
        c.reflected_date = body.reflected_date
        c.reflected_note = (body.reflected_note or "").strip() or None
    if body.evaluated_date is not None:
        if body.resolved is None:
            raise HTTPException(status_code=400, detail="선정사유가 해결되었는지 선택해 주세요")
        if body.resolved is False:
            _need_text("미해결 시 추가 조치 계획", body.next_action)
        c.evaluated_date = body.evaluated_date
        c.evaluator_name = (body.evaluator_name or "").strip() or actor.full_name
        c.resolved = body.resolved
        c.next_action = (body.next_action or "").strip() or None
    db.commit()
    return {"status": "success", "data": _conf_dict(c, _names(db, actor.center_id), date.today())}


@router.delete("/conferences/{conf_id}")
def delete_conference(conf_id: int, db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    c = db.query(CaseConference).filter(CaseConference.id == conf_id, CaseConference.center_id == actor.center_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="회의 기록을 찾을 수 없습니다")
    db.delete(c)
    db.commit()
    return {"status": "success"}


def conference_status(db: Session, center_id: int, today: date) -> dict:
    start, end = quarter_range(today)
    rows = db.query(CaseConference).filter(CaseConference.center_id == center_id).all()
    this_quarter = [c for c in rows if start <= c.conference_date <= end]
    overdue = [c for c in rows if _conf_follow_up(c, today)["state"] == "overdue"]
    return {"quarter_start": start.isoformat(), "quarter_end": end.isoformat(), "count_this_quarter": len(this_quarter),
            "quarter_done": bool(this_quarter), "overdue_follow_up": len(overdue)}


@router.get("/conferences/status")
def get_conference_status(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    return conference_status(db, actor.center_id, date.today())
