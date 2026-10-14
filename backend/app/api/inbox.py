"""센터장 처리함 - 센터장이 직접 메뉴를 열어 보지 않아도 "지금 처리해야 할 건수"를 한 번에 본다.

이미 대시보드에 있는 승인 대기(청구·방문 계획·보호자 가입)는 화면에서 계산하고,
여기서는 각 메뉴 안에만 있던 처리 대기 건수를 모은다.
"""
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import require_manager
from app.database import get_db
from app.models import BillingRecord, HandoverNote, IncidentReport, ResidentChangeRequest, User
from app.visit_precheck import run_precheck

router = APIRouter()

ITEMS = [
    # key, 이름, 설명, 이동할 화면
    ("missing_record", "방문 기록 누락", "일정은 지났는데 도착·기록이 없거나 퇴실이 없는 방문 (최근 14일)", "./dashboard.html#precheckPanel"),
    ("rejected_claims", "보완 요청 후 미처리 청구", "반려했는데 요양보호사가 아직 다시 제출하지 않은 청구", "./billing_management.html"),
    ("change_requests", "이용자 정보 변경 요청", "요양보호사가 요청한 이용자 정보 변경 승인 대기", "./resident_management.html#changeRequestPanel"),
    ("handover_unread", "인수인계 미확인", "받는 요양보호사가 아직 읽지 않은 인계 메모", "./handover.html"),
    ("incident_incomplete", "사고 보고 보완 필요", "보호자 통보일이나 재발방지 대책이 비어 있는 사고 보고", "./incident.html"),
]


@router.get("")
def manager_inbox(db: Session = Depends(get_db), actor: User = Depends(require_manager)):
    center = actor.center_id
    precheck = run_precheck(db, center, 14, datetime.now())["counts"]
    counts = {
        "missing_record": precheck.get("missing_record", 0) + precheck.get("missing_end", 0),
        "rejected_claims": db.query(BillingRecord).filter(
            BillingRecord.center_id == center, BillingRecord.approval_status == "rejected").count(),
        "change_requests": db.query(ResidentChangeRequest).filter(
            ResidentChangeRequest.center_id == center, ResidentChangeRequest.status == "pending").count(),
        "handover_unread": db.query(HandoverNote).filter(
            HandoverNote.center_id == center, HandoverNote.to_caregiver_id.isnot(None),
            HandoverNote.acknowledged_at.is_(None)).count(),
        "incident_incomplete": db.query(IncidentReport).filter(
            IncidentReport.center_id == center,
            or_(IncidentReport.guardian_notified_date.is_(None), IncidentReport.prevention.is_(None),
                IncidentReport.prevention == "")).count(),
    }
    return {"items": [{"key": k, "label": label, "desc": desc, "href": href, "count": counts[k]}
                      for k, label, desc, href in ITEMS]}
