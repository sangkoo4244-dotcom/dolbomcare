"""센터장 처리함 - 센터장이 직접 메뉴를 열어 보지 않아도 "지금 처리해야 할 건수"를 한 번에 본다.

이미 대시보드에 있는 승인 대기(청구·방문 계획·보호자 가입)는 화면에서 계산하고,
여기서는 각 메뉴 안에만 있던 처리 대기 건수를 모은다.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import require_manager
from app.database import get_db
from app.models import BillingRecord, DailyRecord, HandoverNote, IncidentReport, Resident, ResidentChangeRequest, Schedule, User
from app.visit_precheck import run_precheck
from app.anomaly import find_anomalies
from app.models import VisitObjection

router = APIRouter()

ITEMS = [
    # key, 이름, 설명, 이동할 화면
    ("missing_record", "방문 기록 누락", "일정은 지났는데 도착·기록이 없거나 퇴실이 없는 방문 (최근 14일)", "./dashboard.html#precheckPanel"),
    ("draft_claims", "제출 안 한 방문 기록", "요양보호사가 기록만 하고 3일 넘게 제출하지 않은 청구(작성중)", "./billing_management.html?status=draft"),
    ("rejected_claims", "보완 요청 후 미처리 청구", "반려했는데 요양보호사가 아직 다시 제출하지 않은 청구", "./billing_management.html?status=rejected"),
    ("change_requests", "이용자 정보 변경 요청", "요양보호사가 요청한 이용자 정보 변경 승인 대기", "./resident_management.html#changeRequestPanel"),
    ("schedule_changes", "방문 일정 변경 요청", "요양보호사가 요청한 방문 날짜·시간 변경 승인 대기", "./schedule_approval.html#changePanel"),
    ("handover_unread", "인수인계 미확인", "받는 요양보호사가 아직 읽지 않은 인계 메모", "./handover.html?unread=1"),
    ("objections", "보호자 이의 제기", "보호자가 방문 사실 없음을 신고해 답변을 기다리는 건 (처리 전까지 그 날짜 청구 승인 보류)", "./objections.html"),
    ("anomalies", "이상 패턴 확인", "같은 시간 중복 기록, 연차일 기록, 계획 없이 반복된 기록이 있는 요양보호사", "./anomalies.html"),
    ("incident_incomplete", "사고 보고 보완 필요", "보호자 통보일이나 재발방지 대책이 비어 있는 사고 보고", "./incident.html?issues=1"),
]


@router.get("")
def manager_inbox(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    center = actor.center_id
    precheck = run_precheck(db, center, 14, datetime.now())["counts"]
    counts = {
        "missing_record": precheck.get("missing_record", 0) + precheck.get("missing_end", 0),
        "draft_claims": db.query(BillingRecord).filter(
            BillingRecord.center_id == center, BillingRecord.approval_status == "draft",
            BillingRecord.recorded_date <= datetime.now() - timedelta(days=3)).count(),
        "rejected_claims": db.query(BillingRecord).filter(
            BillingRecord.center_id == center, BillingRecord.approval_status == "rejected").count(),
        "change_requests": db.query(ResidentChangeRequest).filter(
            ResidentChangeRequest.center_id == center, ResidentChangeRequest.status == "pending").count(),
        "schedule_changes": db.query(Schedule).filter(
            Schedule.center_id == center, Schedule.change_date.isnot(None)).count(),
        "handover_unread": db.query(HandoverNote).filter(
            HandoverNote.center_id == center, HandoverNote.to_caregiver_id.isnot(None),
            HandoverNote.acknowledged_at.is_(None)).count(),
        "objections": db.query(VisitObjection).filter(
            VisitObjection.center_id == center, VisitObjection.status == "open").count(),
        "anomalies": len(find_anomalies(db, center, datetime.now())),
        "incident_incomplete": db.query(IncidentReport).filter(
            IncidentReport.center_id == center,
            or_(IncidentReport.guardian_notified_date.is_(None), IncidentReport.prevention.is_(None),
                IncidentReport.prevention == "")).count(),
    }
    return {"items": [{"key": k, "label": label, "desc": desc, "href": href, "count": counts[k]}
                      for k, label, desc, href in ITEMS]}


@router.get("/caregivers")
def caregiver_board(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    """요양보호사별 현황판 - 한 사람씩 무엇이 밀려 있는지 한눈에 본다 (센터장 전용)."""
    center = actor.center_id
    now = datetime.now()
    day_start = datetime.combine(now.date(), datetime.min.time())
    month_start = day_start.replace(day=1)
    caregivers = db.query(User).filter(User.center_id == center, User.role == "caregiver").order_by(User.full_name).all()
    board = {u.id: {"caregiver_id": u.id, "name": u.full_name, "residents": 0, "today_planned": 0, "today_arrived": 0,
                    "missing_records": 0, "draft_claims": 0, "rejected_claims": 0, "month_records": 0} for u in caregivers}

    for r in db.query(Resident).filter(Resident.center_id == center, Resident.primary_caregiver_id.isnot(None)).all():
        if r.primary_caregiver_id in board:
            board[r.primary_caregiver_id]["residents"] += 1

    today = db.query(Schedule).filter(
        Schedule.center_id == center, Schedule.scheduled_date >= day_start,
        Schedule.scheduled_date < day_start + timedelta(days=1), Schedule.status.notin_(["cancelled", "proposed", "rejected"])).all()
    for sch in today:
        if sch.caregiver_id in board:
            board[sch.caregiver_id]["today_planned"] += 1
            if sch.arrived_at:
                board[sch.caregiver_id]["today_arrived"] += 1

    missing_ids = {i["schedule_id"] for i in run_precheck(db, center, 14, now)["all_issues"]
                   if i["type"] in ("missing_record", "missing_end") and i.get("schedule_id")}
    if missing_ids:
        for sch in db.query(Schedule).filter(Schedule.id.in_(missing_ids)).all():
            if sch.caregiver_id in board:
                board[sch.caregiver_id]["missing_records"] += 1

    for status, key in (("draft", "draft_claims"), ("rejected", "rejected_claims")):
        for b in db.query(BillingRecord).filter(BillingRecord.center_id == center, BillingRecord.approval_status == status).all():
            if b.caregiver_id in board:
                board[b.caregiver_id][key] += 1

    for rec in db.query(DailyRecord).filter(DailyRecord.recorded_date >= month_start, DailyRecord.caregiver_id.in_(list(board) or [0])).all():
        board[rec.caregiver_id]["month_records"] += 1

    return {"caregivers": list(board.values())}


VISIT_STATES = ("예정", "방문중", "방문완료", "완료", "도착 미기록", "미기록")  # 승인 대기·반려 같은 계획 단계는 방문 현황에서 뺀다


@router.get("/visits-overview")
def visits_overview(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    """방문 기록 현황 오른쪽 패널용: 센터 전체의 오늘 방문, 기록이 비어 있는 방문, 이번 달 이행 현황 (센터장 전용).

    요양보호사별 일정 조회(caregiver_schedule_view)와 같은 판정을 쓰므로 요양보호사 화면과 상태가 일치한다."""
    from app.api.schedule import caregiver_schedule_view

    now = datetime.now()
    ym = now.strftime("%Y-%m")
    today = now.date().isoformat()
    caregivers = db.query(User).filter(User.center_id == actor.center_id, User.role == "caregiver").order_by(User.full_name).all()
    today_rows, missing, month = [], [], {"total": 0, "done": 0, "missing": 0}
    for u in caregivers:
        for it in caregiver_schedule_view(caregiver_id=u.id, year_month=ym, db=db, actor=actor).get("items", []):
            if not it.get("planned") or it.get("state") not in VISIT_STATES or it.get("companion"):
                continue  # 함께 가는 요양보호사(companion)의 일정은 주 담당자의 일정과 같은 방문이라 센터 현황에서 한 번만 센다
            row = {"date": it["date"], "time": it["time"], "resident": it.get("resident_name"), "caregiver": u.full_name, "state": it["state"],
                   "arrived_at": it.get("arrived_at"), "left_at": it.get("left_at")}
            if it["state"] == "미기록" and it["date"] == today:
                row["late_minutes"] = max(0, int((now - datetime.strptime(f"{it['date']} {it['time']}", "%Y-%m-%d %H:%M")).total_seconds() // 60))
            month["total"] += 1
            if it["state"] in ("완료", "방문완료", "도착 미기록"):
                month["done"] += 1
            if it["state"] == "미기록":
                month["missing"] += 1
            if it["date"] == today:
                today_rows.append(row)
            if it["state"] in ("미기록", "방문완료"):
                missing.append(row)
    today_rows.sort(key=lambda r: r["time"])
    missing.sort(key=lambda r: (r["date"], r["time"]), reverse=True)
    return {"today": today_rows, "today_summary": _today_summary(today_rows), "missing": missing[:8], "missing_total": len(missing), "month": month}


def _today_summary(today_rows):
    """오늘 방문을 한눈에: 정상완료·진행중·확인필요(기록 작성 필요·도착 미기록)·미처리(시작 시각이 지났는데 도착도 기록도 없음).
    도착 기록률 = 시작했어야 하는(예정이 아닌) 방문 중 도착 시각이 기록된 비율. 공단 태그와는 별개인 돌봄케어 기록 기준이다."""
    count = lambda *states: sum(1 for r in today_rows if r["state"] in states)  # noqa: E731
    started = [r for r in today_rows if r["state"] != "예정"]
    arrived = sum(1 for r in started if r.get("arrived_at"))
    return {"total": len(today_rows), "scheduled": count("예정"), "in_progress": count("방문중"), "done": count("완료"),
            "need_check": count("방문완료", "도착 미기록"), "late": count("미기록"),
            "started": len(started), "arrived": arrived,
            "arrival_rate": round(arrived * 100 / len(started)) if started else None}
