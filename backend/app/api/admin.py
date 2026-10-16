from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.users import get_password_hash
from app.auth import require_platform_admin
from app.database import get_db
from app.plans import PARTNER_RESIDENT_LIMIT, PARTNER_SLOT_LIMIT, PLAN_PAID, PLAN_PARTNER, PLAN_TRIAL, TRIAL_DAYS, center_plan_info
from app.demo_seed import DEMO_CENTER_NAME, seed_demo
from app.email_service import send_email
from app.models import (
    AlimtalkUsage,
    BillingRecord,
    Center,
    CopayInvoice,
    DailyRecord,
    GuardianInvite,
    HealthMetric,
    MonthlySummary,
    NeedsAssessment,
    Notification,
    Resident,
    ResidentChangeRequest,
    ResidentMedia,
    ResidentMessage,
    ResidentThreadRead,
    RiskAssessment,
    Salary,
    SalaryStatement,
    Schedule,
    StaffCertificate,
    StaffRecord,
    User,
    VoiceRecord,
)

router = APIRouter()


@router.get("/is-admin")
def check_is_admin(actor: User = Depends(require_platform_admin)):
    """프런트에서 운영자 콘솔 링크를 보여줄지 판단하기 위한 가벼운 확인용 (DB 조회 없음)."""
    return {"is_admin": True}


@router.get("/demo/status")
def demo_status(db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)):
    """로그인 화면 '둘러보기' 버튼이 쓰는 데모 계정이 운영 DB에 있는지 읽기만 한다."""
    from app.demo_seed import DEMO_CAREGIVER_EMAIL, DEMO_GUARDIAN_EMAIL, DEMO_MANAGER_EMAIL, DEMO_SOCIAL_EMAIL
    center = db.query(Center).filter(Center.name == DEMO_CENTER_NAME).first()
    accounts = [
        {"email": email, "exists": db.query(User).filter(User.email == email).first() is not None}
        for email in (DEMO_MANAGER_EMAIL, DEMO_CAREGIVER_EMAIL, DEMO_SOCIAL_EMAIL, DEMO_GUARDIAN_EMAIL)
    ]
    return {
        "center_exists": center is not None,
        "residents": db.query(Resident).filter(Resident.center_id == center.id).count() if center else 0,
        "accounts": accounts,
        "ready": center is not None and all(a["exists"] for a in accounts),
    }


@router.post("/demo/reset")
def demo_reset(db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)):
    """데모 체험 센터·계정·방문 데이터를 (다시) 만든다. 실제 센터 데이터는 건드리지 않고 데모 전용 데이터만 지우고 새로 만든다."""
    result = seed_demo(db)
    return {"status": "success", **result}


@router.get("/users/lookup")
def lookup_user(email: str, db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)):
    """이메일로 계정을 찾는다 (운영자 전용). 로그인이 안 된다는 문의가 왔을 때 어느 센터
    소속인지, 역할이 뭔지 확인한 뒤 바로 비밀번호를 재설정해 줄 수 있게 한다."""
    user = db.query(User).filter(User.email == email.strip()).first()
    if not user:
        raise HTTPException(status_code=404, detail="해당 이메일의 계정을 찾을 수 없습니다")
    center = db.query(Center).filter(Center.id == user.center_id).first() if user.center_id else None
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "center_id": user.center_id,
        "center_name": center.name if center else None,
        "trial_ends_at": center.trial_ends_at.isoformat() if center and center.trial_ends_at else None,
    }


class AdminResetPasswordRequest(BaseModel):
    new_password: str


@router.post("/users/{user_id}/reset-password")
def admin_reset_password(
    user_id: int,
    body: AdminResetPasswordRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_platform_admin),
):
    """운영자가 어떤 계정이든 비밀번호를 바로 재설정한다 (센터장을 거치지 않고 즉시 처리할 때 사용)."""
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 최소 8자 이상이어야 합니다")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="계정을 찾을 수 없습니다")
    user.hashed_password = get_password_hash(body.new_password)
    db.commit()
    return {"status": "success", "email": user.email}


class CenterCreateRequest(BaseModel):
    center_name: str
    manager_name: str
    manager_email: str
    manager_password: str




@router.post("/centers")
def create_center(
    body: CenterCreateRequest, db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)
):
    """새 센터와 센터장 계정을 만든다 (운영자 전용). 지금은 가입 페이지가 실제 계정을 만들지
    않기 때문에, 파일럿 센터를 쓰게 하려면 운영자가 이 화면에서 직접 만들어 전달해야 한다.
    무료 체험(TRIAL_DAYS일)이 자동으로 시작되고, 기간이 지나면 읽기 전용이 된다 (plans.py 참고)."""
    if not body.center_name.strip():
        raise HTTPException(status_code=400, detail="센터명을 입력해 주세요")
    if len(body.manager_password) < 8:
        raise HTTPException(status_code=400, detail="비밀번호는 최소 8자 이상이어야 합니다")
    if db.query(User).filter(User.email == body.manager_email).first():
        raise HTTPException(status_code=400, detail="이미 사용 중인 이메일입니다")

    center = Center(name=body.center_name.strip(), plan=PLAN_TRIAL, trial_ends_at=datetime.utcnow() + timedelta(days=TRIAL_DAYS))
    db.add(center)
    db.flush()
    manager = User(
        email=body.manager_email,
        hashed_password=get_password_hash(body.manager_password),
        full_name=body.manager_name,
        role="center_manager",
        center_id=center.id,
        is_active=True,
    )
    db.add(manager)
    db.commit()

    email_sent = send_email(
        to=manager.email,
        subject=f"[돌봄케어] {center.name} {TRIAL_DAYS}일 무료체험 계정이 만들어졌습니다",
        body=(
            f"{body.manager_name}님, 안녕하세요.\n\n"
            f"신청하신 돌봄케어 {TRIAL_DAYS}일 무료체험 계정이 만들어졌습니다.\n\n"
            f"센터명: {center.name}\n"
            f"로그인 이메일: {manager.email}\n"
            f"비밀번호: {body.manager_password}\n\n"
            f"아래 주소에서 로그인해 주세요.\n"
            f"https://seniorcareinfo.kr/pages/login.html\n\n"
            f"문의: contact@eeum-logic.com\n"
            f"이음로직 드림"
        ),
    )
    return {
        "status": "success",
        "center_id": center.id,
        "center_name": center.name,
        "manager_email": manager.email,
        "email_sent": email_sent,
    }


@router.get("/alimtalk-overview")
def list_alimtalk_overview(db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)):
    """센터별 이번 달 알림톡 사용량·충전 잔액 (운영자 전용)."""
    year_month = datetime.utcnow().strftime("%Y-%m")
    usages = {u.center_id: u for u in db.query(AlimtalkUsage).filter(AlimtalkUsage.year_month == year_month).all()}
    centers = db.query(Center).order_by(Center.name).all()
    return [
        {
            "center_id": c.id,
            "center_name": c.name,
            "balance": c.alimtalk_balance or 0,
            "free_sent": usages[c.id].free_sent if c.id in usages else 0,
            "paid_sent": usages[c.id].paid_sent if c.id in usages else 0,
            "blocked_count": usages[c.id].blocked_count if c.id in usages else 0,
            "resident_count": db.query(Resident).filter(Resident.center_id == c.id).count(),
            "staff_count": db.query(User).filter(User.center_id == c.id).count(),
            "trial_ends_at": c.trial_ends_at.isoformat() if c.trial_ends_at else None,
            "plan": center_plan_info(c)["plan"],
            "plan_state": center_plan_info(c)["state"],
            "partner_since": c.partner_since.isoformat() if c.partner_since else None,
            "partner_note": c.partner_note,
        }
        for c in centers
    ]


class ExtendTrialRequest(BaseModel):
    days: int


@router.post("/centers/{center_id}/extend-trial")
def extend_trial(
    center_id: int, body: ExtendTrialRequest, db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)
):
    """체험 기간을 연장한다 (운영자 전용). 이미 지난 센터는 오늘부터, 아직 안 지난 센터는
    남은 기간에 이어서 더한다."""
    if body.days <= 0:
        raise HTTPException(status_code=400, detail="연장할 일수를 입력해 주세요")
    center = db.query(Center).filter(Center.id == center_id).first()
    if not center:
        raise HTTPException(status_code=404, detail="센터를 찾을 수 없습니다")

    base = center.trial_ends_at if center.trial_ends_at and center.trial_ends_at > datetime.utcnow() else datetime.utcnow()
    center.trial_ends_at = base + timedelta(days=body.days)
    db.commit()
    return {"status": "success", "center_id": center.id, "trial_ends_at": center.trial_ends_at.isoformat()}


@router.post("/centers/{center_id}/convert-to-paid")
def convert_to_paid(center_id: int, db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)):
    """체험 기간 제한을 완전히 없앤다 (운영자 전용) - 정식 계약 전환 시 사용."""
    center = db.query(Center).filter(Center.id == center_id).first()
    if not center:
        raise HTTPException(status_code=404, detail="센터를 찾을 수 없습니다")
    center.trial_ends_at = None
    center.plan = PLAN_PAID
    db.commit()
    return {"status": "success", "center_id": center.id}


@router.get("/trial-requests")
def list_trial_requests(db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)):
    """로그인 화면으로 들어온 무료체험·파트너 신청 (새 신청이 위로)."""
    from app.models import TrialRequest
    rows = db.query(TrialRequest).order_by(TrialRequest.status.desc(), TrialRequest.created_at.desc()).limit(100).all()
    return {"requests": [
        {"id": r.id, "center_name": r.center_name, "manager_name": r.manager_name, "email": r.email, "phone": r.phone,
         "partner_interest": bool(r.partner_interest), "status": r.status, "created_at": r.created_at.isoformat() if r.created_at else None,
         "institution_code": r.institution_code, "institution_verified": bool(r.institution_verified),
         "cert_name": r.cert_name, "has_cert": bool(r.cert_data)}
        for r in rows
    ], "new_count": sum(1 for r in rows if r.status == "new")}


@router.get("/facilities/status")
def facilities_status(db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)):
    """공단 장기요양기관 목록이 마지막으로 언제 가져와졌는지 (체험 신청의 기관기호 대조에 쓴다)."""
    from app.facility_registry import registry_status
    return {"status": "success", "data": registry_status(db)}


@router.post("/facilities/import")
async def import_facilities(file: UploadFile = File(...), db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)):
    """공단 '장기요양기관 시설별 현황' 엑셀을 올려 기관 목록을 새로 바꾼다."""
    from app.facility_registry import FacilityImportError, import_workbook
    data = await file.read()
    try:
        result = import_workbook(db, data, file.filename or "facility.xlsx")
    except FacilityImportError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "data": result}


@router.get("/trial-requests/{request_id}/certificate")
def get_trial_certificate(request_id: int, db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)):
    """체험 신청에 올라온 지정서 사본. 운영자만 연다."""
    from app.models import TrialRequest
    row = db.query(TrialRequest).filter(TrialRequest.id == request_id).first()
    if not row or not row.cert_data:
        raise HTTPException(status_code=404, detail="지정서 사본이 없습니다")
    return {"status": "success", "data": {"file_name": row.cert_name, "file_type": row.cert_type, "file_data": row.cert_data}}


@router.post("/trial-requests/{request_id}/handled")
def mark_trial_request_handled(request_id: int, db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)):
    from app.models import TrialRequest
    row = db.query(TrialRequest).filter(TrialRequest.id == request_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="신청을 찾을 수 없습니다")
    row.status = "handled"
    if row.institution_code:  # 셀프 가입 센터면 지정서 확인이 끝난 것이므로 쓰기 제한을 푼다
        from app.models import Center
        center = db.query(Center).filter(Center.institution_code == row.institution_code, Center.verified == False).first()  # noqa: E712
        if center:
            center.verified = True
    db.commit()
    return {"status": "success"}


class PartnerRequest(BaseModel):
    note: str = ""


def _partner_slots(db: Session) -> dict:
    used = db.query(Center).filter(Center.plan == PLAN_PARTNER).count()
    return {"limit": PARTNER_SLOT_LIMIT, "used": used, "remaining": max(0, PARTNER_SLOT_LIMIT - used)}


@router.get("/partners")
def list_partners(db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)):
    """파트너(무기한 무료 이벤트) 센터와 남은 자리 (운영자 전용)."""
    partners = db.query(Center).filter(Center.plan == PLAN_PARTNER).order_by(Center.partner_since).all()
    mix = {}
    for c in partners:
        for service in [s for s in (c.service_types or "").split(",") if s] or ["(미선택)"]:
            mix[service] = mix.get(service, 0) + 1
    return {
        **_partner_slots(db),
        "resident_limit": PARTNER_RESIDENT_LIMIT,
        "service_mix": mix,
        "partners": [{"center_id": c.id, "center_name": c.name, "partner_since": c.partner_since.isoformat() if c.partner_since else None,
                      "note": c.partner_note, "services": [s for s in (c.service_types or "").split(",") if s],
                      "resident_count": db.query(Resident).filter(Resident.center_id == c.id).count()} for c in partners],
    }


@router.post("/centers/{center_id}/partner")
def make_partner(center_id: int, body: PartnerRequest, db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)):
    """센터를 파트너로 지정한다: 기간 제한 없이 무료. 자리가 남아 있을 때만 지정할 수 있다."""
    center = db.query(Center).filter(Center.id == center_id).first()
    if not center:
        raise HTTPException(status_code=404, detail="센터를 찾을 수 없습니다")
    if center.plan == PLAN_PARTNER:
        raise HTTPException(status_code=400, detail="이미 파트너 센터입니다")
    if _partner_slots(db)["remaining"] <= 0:
        raise HTTPException(status_code=400, detail=f"파트너 자리 {PARTNER_SLOT_LIMIT}곳이 모두 찼습니다")
    center.plan = PLAN_PARTNER
    center.trial_ends_at = None
    center.partner_since = datetime.utcnow()
    center.partner_note = (body.note or "").strip() or None
    db.commit()
    return {"status": "success", "center_id": center.id, **_partner_slots(db)}


class EndPartnerRequest(BaseModel):
    days: int = TRIAL_DAYS


@router.post("/centers/{center_id}/end-partner")
def end_partner(center_id: int, body: EndPartnerRequest, db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)):
    """파트너를 해제한다. 갑자기 막히지 않도록 days일 동안의 체험 기간으로 돌려보낸다(기본 30일, 0이면 바로 읽기 전용)."""
    center = db.query(Center).filter(Center.id == center_id).first()
    if not center or center.plan != PLAN_PARTNER:
        raise HTTPException(status_code=404, detail="파트너 센터를 찾을 수 없습니다")
    if body.days < 0:
        raise HTTPException(status_code=400, detail="일수는 0 이상이어야 합니다")
    center.plan = PLAN_TRIAL
    center.trial_ends_at = datetime.utcnow() + timedelta(days=body.days)
    db.commit()
    return {"status": "success", "center_id": center.id, "trial_ends_at": center.trial_ends_at.isoformat(), **_partner_slots(db)}


def _cascade_delete_center(db: Session, center: Center) -> None:
    """센터에 딸린 모든 데이터를 지운다 (이용자·직원·청구·기록 등 전부). FK 제약(특히 운영 DB인
    PostgreSQL)을 어기지 않도록, 참조당하는 테이블부터 역순으로 지운다."""
    center_id = center.id
    resident_ids = [r.id for r in db.query(Resident.id).filter(Resident.center_id == center_id).all()]
    user_ids = [u.id for u in db.query(User.id).filter(User.center_id == center_id).all()]

    # 보호자(guardian)는 users.center_id가 없고 residents.guardian_id로만 이 센터와 연결된다.
    # 이 센터의 이용자에게만 연결돼 있고(다른 센터 이용자는 없고) 소속 센터가 없는 보호자만
    # 함께 지운다 - 그래야 나중에 같은 이메일로 다시 못 쓰는 "유령 계정"으로 안 남는다.
    guardian_candidate_ids = {
        g for (g,) in db.query(Resident.guardian_id)
        .filter(Resident.center_id == center_id, Resident.guardian_id.isnot(None)).all()
    }
    for gid in list(guardian_candidate_ids):
        guardian = db.query(User).filter(User.id == gid).first()
        if not guardian or guardian.center_id is not None:
            guardian_candidate_ids.discard(gid)
            continue
        has_other_residents = db.query(Resident).filter(
            Resident.guardian_id == gid, Resident.center_id != center_id
        ).first() is not None
        if has_other_residents:
            guardian_candidate_ids.discard(gid)
    user_ids = list(set(user_ids) | guardian_candidate_ids)

    # centers.manager_id가 users를 참조한다 (데모 센터처럼 설정된 경우). 먼저 끊지 않으면
    # 아래에서 그 직원(User)을 지울 때 FK 위반으로 실패한다 (특히 PostgreSQL).
    center.manager_id = None
    db.flush()

    # billing_records.daily_record_id가 daily_records를 참조하므로 daily_records보다 먼저 지운다
    db.query(BillingRecord).filter(BillingRecord.center_id == center_id).delete(synchronize_session=False)

    if resident_ids:
        db.query(DailyRecord).filter(DailyRecord.resident_id.in_(resident_ids)).delete(synchronize_session=False)
        db.query(HealthMetric).filter(HealthMetric.resident_id.in_(resident_ids)).delete(synchronize_session=False)
        db.query(NeedsAssessment).filter(NeedsAssessment.resident_id.in_(resident_ids)).delete(synchronize_session=False)
        db.query(RiskAssessment).filter(RiskAssessment.resident_id.in_(resident_ids)).delete(synchronize_session=False)
        db.query(ResidentMedia).filter(ResidentMedia.resident_id.in_(resident_ids)).delete(synchronize_session=False)
        db.query(ResidentThreadRead).filter(ResidentThreadRead.resident_id.in_(resident_ids)).delete(synchronize_session=False)

    if user_ids:
        db.query(StaffCertificate).filter(StaffCertificate.user_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(StaffRecord).filter(StaffRecord.staff_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(ResidentThreadRead).filter(ResidentThreadRead.user_id.in_(user_ids)).delete(synchronize_session=False)
        db.query(Notification).filter(Notification.user_id.in_(user_ids)).delete(synchronize_session=False)

    db.query(ResidentMessage).filter(ResidentMessage.center_id == center_id).delete(synchronize_session=False)
    db.query(ResidentChangeRequest).filter(ResidentChangeRequest.center_id == center_id).delete(synchronize_session=False)
    db.query(GuardianInvite).filter(GuardianInvite.center_id == center_id).delete(synchronize_session=False)
    db.query(Schedule).filter(Schedule.center_id == center_id).delete(synchronize_session=False)
    db.query(MonthlySummary).filter(MonthlySummary.center_id == center_id).delete(synchronize_session=False)
    db.query(Salary).filter(Salary.center_id == center_id).delete(synchronize_session=False)
    db.query(SalaryStatement).filter(SalaryStatement.center_id == center_id).delete(synchronize_session=False)
    db.query(CopayInvoice).filter(CopayInvoice.center_id == center_id).delete(synchronize_session=False)
    db.query(VoiceRecord).filter(VoiceRecord.center_id == center_id).delete(synchronize_session=False)
    db.query(AlimtalkUsage).filter(AlimtalkUsage.center_id == center_id).delete(synchronize_session=False)

    db.query(Resident).filter(Resident.center_id == center_id).delete(synchronize_session=False)
    if user_ids:
        db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    db.delete(center)


@router.delete("/centers/{center_id}")
def delete_center(center_id: int, db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)):
    """사용하지 않는 센터를 삭제한다 (운영자 전용). 이용자가 한 명이라도 있거나 센터장 외에
    직원이 등록돼 있으면 실수로 실제 운영 데이터를 지우는 것을 막기 위해 거부한다.
    데이터가 있는 센터를 지우려면 /centers/{center_id}/force를 쓴다."""
    center = db.query(Center).filter(Center.id == center_id).first()
    if not center:
        raise HTTPException(status_code=404, detail="센터를 찾을 수 없습니다")

    resident_count = db.query(Resident).filter(Resident.center_id == center_id).count()
    if resident_count > 0:
        raise HTTPException(status_code=400, detail=f"이용자가 {resident_count}명 등록돼 있어 삭제할 수 없습니다")

    staff_count = db.query(User).filter(User.center_id == center_id).count()
    if staff_count > 1:
        raise HTTPException(status_code=400, detail="센터장 외 직원이 등록돼 있어 삭제할 수 없습니다")

    _cascade_delete_center(db, center)
    db.commit()
    return {"status": "success"}


class ForceDeleteRequest(BaseModel):
    confirm_name: str


@router.delete("/centers/{center_id}/force")
def force_delete_center(
    center_id: int,
    body: ForceDeleteRequest,
    db: Session = Depends(get_db),
    actor: User = Depends(require_platform_admin),
):
    """이용자·직원이 있는 센터도 강제로 삭제한다 (운영자 전용, 복구 불가능).
    실수 방지를 위해 센터명을 정확히 입력해야만 실행된다."""
    center = db.query(Center).filter(Center.id == center_id).first()
    if not center:
        raise HTTPException(status_code=404, detail="센터를 찾을 수 없습니다")
    if body.confirm_name.strip() != center.name:
        raise HTTPException(status_code=400, detail="센터명이 일치하지 않습니다")

    _cascade_delete_center(db, center)
    db.commit()
    return {"status": "success"}


class ChargeRequest(BaseModel):
    center_id: int
    amount: int


@router.post("/alimtalk-charge")
def charge_alimtalk_balance(
    body: ChargeRequest, db: Session = Depends(get_db), actor: User = Depends(require_platform_admin)
):
    """센터 충전 잔액을 수동으로 올린다 (운영자 전용). 입금 확인 후 운영자가 직접 호출한다."""
    if body.amount == 0:
        raise HTTPException(status_code=400, detail="금액을 입력해 주세요")
    center = db.query(Center).filter(Center.id == body.center_id).first()
    if not center:
        raise HTTPException(status_code=404, detail="센터를 찾을 수 없습니다")
    center.alimtalk_balance = (center.alimtalk_balance or 0) + body.amount
    db.commit()
    return {"status": "success", "center_id": center.id, "balance": center.alimtalk_balance}
