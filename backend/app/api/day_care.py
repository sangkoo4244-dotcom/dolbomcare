"""주·야간보호 하루 이용 기록과 청구.

청구 단위가 방문 1회가 아니라 수급자 1일이다(고시 제30~35조). 한 건의 이용 기록이 다음을 만든다:
- 급여비용: 이용 시간 구간 × 장기요양등급(인지지원등급 포함), 본인부담은 재가급여 기준(billing_rules)
- 이동서비스비용(제34조): 기관~실거주지 최단거리(편도) 4구간, 1일 1회, 편도만이면 50%, 수급자 부담 없음, 월 한도 밖
- 목욕서비스 가산(제35조): 수급자당 주 1회 3,000원, 수급자 부담 없음
이동서비스비용·목욕 가산은 청구서의 별도 금액(extra_amount)으로 두어 요양보호사 급여 계산에 섞이지 않게 한다.
같은 날 같은 수급자에게 주·야간보호와 방문목욕을 함께 제공하면 한 종류만 산정한다(제32조 ②).
"""
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import benefits
from app.api.notifications import notify
from app.auth import get_current_user
from app.billing_rules import split_day_night
from app.database import get_db
from app.models import BillingRecord, Center, DailyRecord, DayCareAttendance, Resident, User

router = APIRouter()

EDITABLE_APPROVALS = ("draft", "rejected")


class AttendanceIn(BaseModel):
    resident_id: int
    caregiver_id: Optional[int] = None  # 센터장이 대신 입력할 때 기록 주인이 될 요양보호사
    attendance_date: date
    arrive_time: str  # "HH:MM"
    leave_time: str  # "HH:MM" - 같은 날 안에 끝나야 한다(24시 이후 보호는 청구할 수 없다)
    transport: Literal["none", "in", "out", "both"] = "none"
    distance_km: Optional[float] = Field(None, ge=0, le=300)
    bath_given: bool = False
    special_note: Optional[str] = Field(None, max_length=300)
    notes: Optional[str] = Field(None, max_length=300)


def _clock(value: str, label: str) -> tuple[int, int]:
    try:
        hour, minute = (int(x) for x in value.split(":"))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
        return hour, minute
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail=f"{label}은(는) 00:00~23:59 형식으로 입력해 주세요")


def _require_service(db: Session, actor: User) -> Center:
    if actor.role not in ("center_manager", "caregiver"):
        raise HTTPException(status_code=403, detail="권한이 없습니다")
    center = db.query(Center).filter(Center.id == actor.center_id).first() if actor.center_id else None
    if "day_night" not in benefits.enabled_codes(center.service_types if center else None):
        raise HTTPException(status_code=400, detail="주·야간보호는 센터 정보에서 제공 급여로 선택한 뒤 쓸 수 있습니다")
    return center


def _week_bounds(day: date):
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=7)


def _compute(db: Session, actor: User, body: AttendanceIn, exclude_id: Optional[int] = None) -> dict:
    """입력을 검사하고 금액을 계산한다. 문제가 있으면 400."""
    center = _require_service(db, actor)
    resident = db.query(Resident).filter(Resident.id == body.resident_id, Resident.center_id == center.id).first()
    if not resident:
        raise HTTPException(status_code=404, detail="이용자를 찾을 수 없습니다")

    ah, am = _clock(body.arrive_time, "도착 시각")
    lh, lm = _clock(body.leave_time, "퇴실 시각")
    arrived = datetime(body.attendance_date.year, body.attendance_date.month, body.attendance_date.day, ah, am)
    left = datetime(body.attendance_date.year, body.attendance_date.month, body.attendance_date.day, lh, lm)
    if left <= arrived:
        raise HTTPException(status_code=400, detail="퇴실 시각이 도착 시각보다 늦어야 합니다. 24시 이후까지 보호하면 급여비용을 청구할 수 없습니다(고시 제32조 ①)")
    minutes = int((left - arrived).total_seconds() // 60)
    try:
        fee_total, patient, insurer = split_day_night(minutes, resident.care_grade, resident.client_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        transport_code, transport_amount = benefits.day_night_transport_fee(body.distance_km, body.transport)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # 같은 날 방문목욕과 겹치면 한 종류만 산정한다
    bath_visit = db.query(DailyRecord).filter(
        DailyRecord.resident_id == resident.id, DailyRecord.benefit_type == "home_bath",
        DailyRecord.recorded_date >= datetime.combine(body.attendance_date, datetime.min.time()),
        DailyRecord.recorded_date < datetime.combine(body.attendance_date + timedelta(days=1), datetime.min.time())).first()
    if bath_visit:
        raise HTTPException(status_code=400, detail="같은 날 방문목욕을 이미 기록했습니다. 주·야간보호와 방문목욕은 같은 날 한 종류만 산정합니다(고시 제32조 ②)")

    q = db.query(DayCareAttendance).filter(DayCareAttendance.resident_id == resident.id, DayCareAttendance.attendance_date == body.attendance_date)
    if exclude_id:
        q = q.filter(DayCareAttendance.id != exclude_id)
    if q.first():
        raise HTTPException(status_code=409, detail="이 이용자의 그날 이용 기록이 이미 있습니다")

    bath_bonus, bath_note = 0, ""
    if body.bath_given:
        start, end = _week_bounds(body.attendance_date)
        done = db.query(DayCareAttendance).filter(
            DayCareAttendance.resident_id == resident.id, DayCareAttendance.attendance_date >= start, DayCareAttendance.attendance_date < end,
            DayCareAttendance.bath_bonus > 0).first()
        if done:
            bath_note = "같은 주에 목욕서비스 가산을 이미 받아 이번에는 가산하지 않습니다(주 1회)"
        else:
            bath_bonus = benefits.DAY_NIGHT_BATH_BONUS

    standard_start, standard_end = benefits.DAY_NIGHT_STANDARD_HOURS
    notes = []
    if ah < standard_start or lh > standard_end or (lh == standard_end and lm > 0):
        notes.append("표준급여제공시간(08~22시) 밖의 시간이 있습니다")
    if bath_note:
        notes.append(bath_note)
    return {
        "resident": resident, "center": center, "arrived": arrived, "left": left, "minutes": minutes,
        "fee_total": fee_total, "patient": patient, "insurer": insurer, "transport_code": transport_code,
        "transport_amount": transport_amount, "bath_bonus": bath_bonus, "notes": notes,
    }


def _breakdown(c: dict) -> dict:
    return {"minutes": c["minutes"], "fee_total": c["fee_total"], "patient": c["patient"], "insurer": c["insurer"],
            "transport_code": c["transport_code"], "transport_amount": c["transport_amount"], "bath_bonus": c["bath_bonus"],
            "extra_amount": c["transport_amount"] + c["bath_bonus"], "notes": c["notes"]}


@router.post("/preview")
def preview(body: AttendanceIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    """저장하기 전에 금액을 미리 계산한다. 입력이 아직 부족해서 계산할 수 없으면 ok=false와 이유를 돌려준다."""
    try:
        return {"ok": True, **_breakdown(_compute(db, actor, body))}
    except HTTPException as e:
        return {"ok": False, "message": e.detail}


@router.post("")
def create_attendance(body: AttendanceIn, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    caregiver_id = actor.id if actor.role == "caregiver" else body.caregiver_id
    c = _compute(db, actor, body)
    resident = c["resident"]
    if actor.role == "center_manager":
        target = db.query(User).filter(User.id == caregiver_id).first() if caregiver_id else None
        if not target or target.role != "caregiver" or target.center_id != actor.center_id:
            raise HTTPException(status_code=400, detail="기록할 요양보호사를 우리 센터에서 골라 주세요")

    attendance = DayCareAttendance(
        center_id=actor.center_id, resident_id=resident.id, caregiver_id=caregiver_id, attendance_date=body.attendance_date,
        arrived_at=c["arrived"], left_at=c["left"], minutes=c["minutes"], transport=body.transport, distance_km=body.distance_km,
        transport_amount=c["transport_amount"], bath_given=body.bath_given, bath_bonus=c["bath_bonus"],
        special_note=(body.special_note or "").strip() or None, notes=(body.notes or "").strip() or None,
    )
    db.add(attendance)
    db.flush()
    billing = BillingRecord(
        caregiver_id=caregiver_id, resident_id=resident.id, resident_name=resident.name, care_grade=resident.care_grade,
        client_type=resident.client_type, center_id=actor.center_id, service_category="재가급여", service_type="basic_care",
        benefit_type="day_night", amount=c["insurer"], total_cost=c["fee_total"], extra_amount=c["transport_amount"] + c["bath_bonus"],
        recorded_date=c["arrived"], year_month=c["arrived"].strftime("%Y-%m"), status="draft", approval_status="draft",
    )
    db.add(billing)
    db.flush()
    attendance.billing_record_id = billing.id
    if resident.guardian_id:
        notify(db, resident.guardian_id, "visit_completed",
               f"{resident.name}님이 오늘 주·야간보호를 이용하셨습니다 ({c['arrived']:%H:%M}~{c['left']:%H:%M}).")
    db.commit()
    return {"status": "success", "id": attendance.id, "billing_id": billing.id, **_breakdown(c)}


def _row(a: DayCareAttendance, residents: dict, staff: dict, billings: dict) -> dict:
    b = billings.get(a.billing_record_id)
    return {
        "id": a.id, "date": a.attendance_date.isoformat(), "resident_id": a.resident_id, "resident": residents.get(a.resident_id, ""),
        "caregiver": staff.get(a.caregiver_id, ""), "arrive": a.arrived_at.strftime("%H:%M"), "leave": a.left_at.strftime("%H:%M"),
        "minutes": a.minutes, "transport": a.transport, "distance_km": a.distance_km, "transport_amount": a.transport_amount or 0,
        "bath_given": bool(a.bath_given), "bath_bonus": a.bath_bonus or 0, "special_note": a.special_note, "notes": a.notes,
        "fee_total": b.total_cost if b else None, "insurer": b.amount if b else None, "approval_status": b.approval_status if b else None,
    }


@router.get("")
def list_attendance(year_month: str = Query(..., description="YYYY-MM"), db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    center = _require_service(db, actor)
    try:
        year, month = (int(x) for x in year_month.split("-"))
        start = date(year, month, 1)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="월은 YYYY-MM 형식이어야 합니다")
    end = date(year + (month == 12), month % 12 + 1, 1)
    q = db.query(DayCareAttendance).filter(DayCareAttendance.center_id == center.id, DayCareAttendance.attendance_date >= start,
                                           DayCareAttendance.attendance_date < end)
    if actor.role == "caregiver":
        q = q.filter(DayCareAttendance.caregiver_id == actor.id)
    rows = q.order_by(DayCareAttendance.attendance_date, DayCareAttendance.arrived_at).all()
    residents = {r.id: r.name for r in db.query(Resident).filter(Resident.center_id == center.id).all()}
    staff = {u.id: u.full_name for u in db.query(User).filter(User.center_id == center.id).all()}
    billings = {b.id: b for b in db.query(BillingRecord).filter(BillingRecord.id.in_([a.billing_record_id for a in rows if a.billing_record_id])).all()} if rows else {}
    items = [_row(a, residents, staff, billings) for a in rows]
    return {"year_month": year_month, "items": items,
            "totals": {"days": len(items), "fee_total": sum(i["fee_total"] or 0 for i in items), "insurer": sum(i["insurer"] or 0 for i in items),
                       "extra": sum(i["transport_amount"] + i["bath_bonus"] for i in items)}}


@router.delete("/{attendance_id}")
def delete_attendance(attendance_id: int, db: Session = Depends(get_db), actor: User = Depends(get_current_user)):
    _require_service(db, actor)
    a = db.query(DayCareAttendance).filter(DayCareAttendance.id == attendance_id, DayCareAttendance.center_id == actor.center_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="이용 기록을 찾을 수 없습니다")
    if actor.role != "center_manager" and a.caregiver_id != actor.id:
        raise HTTPException(status_code=403, detail="본인이 기록한 것만 삭제할 수 있습니다")
    billing = db.query(BillingRecord).filter(BillingRecord.id == a.billing_record_id).first() if a.billing_record_id else None
    if billing and billing.approval_status not in EDITABLE_APPROVALS:
        raise HTTPException(status_code=400, detail="이미 제출·승인된 청구라 삭제할 수 없습니다")
    if billing:
        db.delete(billing)
    db.delete(a)
    db.commit()
    return {"status": "success"}
