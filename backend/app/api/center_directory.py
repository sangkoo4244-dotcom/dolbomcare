import base64
import re
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.centers import _to_directory_dict
from app.facility_registry import check_institution
from app.database import get_db
from app.kakao_local import KAKAO_JS_KEY, search_nearby_facilities
from app.api.notifications import notify
from app.models import Center, TrialRequest, User

router = APIRouter()


@router.get("/kakao-js-key")
def get_kakao_js_key():
    """센터 찾기 지도에 쓸 카카오맵 JavaScript 키 (공개 가능 - 도메인으로 제한됨).
    미설정이면 key: null을 내려주고, 화면은 지도 없이 목록만 보여준다."""
    return {"key": KAKAO_JS_KEY}


class TrialRequestIn(BaseModel):
    center_name: str
    institution_code: str  # 장기요양기관기호(11자리). 공단 기관 목록에 있는 기관만 신청할 수 있다
    sido_code: str  # 기관이 있는 시도 (공단 시도 코드 2자리)
    certificate_name: str  # 장기요양기관 지정서(재가는 설치신고증명서) 사본
    certificate_type: str
    certificate_data: str  # base64
    manager_name: str
    email: str
    phone: Optional[str] = None
    partner_interest: bool = False
    website: Optional[str] = None  # 사람은 비워 두는 숨은 칸(자동 가입 방지)


CERT_TYPES = ("application/pdf", "image/png", "image/jpeg")
CERT_MAX_BYTES = 3 * 1024 * 1024
_recent_requests = {}  # 접속 주소별 최근 신청 시각 (서버가 다시 뜨면 비워진다 - 아주 단순한 속도 제한)
REQUEST_LIMIT_PER_HOUR = 5


@router.post("/trial-requests")
def submit_trial_request(body: TrialRequestIn, request: Request, db: Session = Depends(get_db)):
    """로그인 없이 접수하는 무료체험·파트너 신청. 저장해 두고 운영자에게 앱 알림을 보낸다."""
    if body.website:  # 숨은 칸이 채워졌으면 자동 가입이므로 성공한 척 넘긴다
        return {"status": "received"}
    name, manager, email = body.center_name.strip(), body.manager_name.strip(), body.email.strip().lower()
    if not name or len(name) > 100 or not manager or len(manager) > 50:
        raise HTTPException(status_code=400, detail="센터명과 담당자명을 입력해 주세요")
    if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email) or len(email) > 120:
        raise HTTPException(status_code=400, detail="이메일 형식을 확인해 주세요. (예: name@example.com)")
    phone = (body.phone or "").strip()[:30] or None
    check = check_institution(db, body.institution_code, name, body.sido_code.strip())
    if not check["ok"]:
        raise HTTPException(status_code=400, detail=check["message"])
    cert_name = (body.certificate_name or "").strip()[:120] or "지정서"
    if body.certificate_type not in CERT_TYPES:
        raise HTTPException(status_code=400, detail="지정서 사본은 PDF 또는 PNG·JPG 사진으로 올려 주세요")
    try:
        cert_size = len(base64.b64decode(body.certificate_data, validate=True))
    except Exception:
        raise HTTPException(status_code=400, detail="지정서 사본을 읽지 못했습니다. 다시 올려 주세요")
    if cert_size > CERT_MAX_BYTES:
        raise HTTPException(status_code=400, detail="지정서 사본은 3MB 이하로 올려 주세요")

    client_ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "?"))
    now = time.time()
    recent = [t for t in _recent_requests.get(client_ip, []) if now - t < 3600]
    if len(recent) >= REQUEST_LIMIT_PER_HOUR:
        raise HTTPException(status_code=429, detail="신청이 너무 많습니다. 잠시 후 다시 시도해 주세요.")
    _recent_requests[client_ip] = recent + [now]

    # 같은 이메일로 최근 하루 안에 이미 받았으면 새로 만들지 않고 내용만 갱신한다(중복 접수 방지)
    existing = db.query(TrialRequest).filter(TrialRequest.email == email, TrialRequest.created_at >= datetime.now() - timedelta(days=1)).first()
    if existing:
        existing.center_name, existing.manager_name, existing.phone = name, manager, phone
        existing.institution_code, existing.institution_verified = check["code"], True
        existing.cert_name, existing.cert_type, existing.cert_data = cert_name, body.certificate_type, body.certificate_data
        existing.partner_interest = bool(existing.partner_interest or body.partner_interest)
        db.commit()
        return {"status": "received"}
    db.add(TrialRequest(center_name=name, manager_name=manager, email=email, phone=phone, partner_interest=body.partner_interest,
                        institution_code=check["code"], institution_verified=True,
                        cert_name=cert_name, cert_type=body.certificate_type, cert_data=body.certificate_data))
    from app.auth import platform_admin_emails
    for admin in db.query(User).filter(User.email.in_(list(platform_admin_emails()))).all():
        notify(db, admin.id, "trial_request", f"새 무료체험 신청이 들어왔습니다: {name} ({manager})" + (" · 파트너 이벤트 신청" if body.partner_interest else ""))
    db.commit()
    return {"status": "received"}


@router.get("/partner-slots")
def partner_slots(db: Session = Depends(get_db)):
    """파트너 센터 이벤트의 남은 자리 (로그인 없이 볼 수 있다: 요금제·로그인 화면 안내용). 센터 이름은 내려주지 않는다."""
    from app.models import Center as _Center
    from app.plans import PARTNER_SLOT_LIMIT, PLAN_PARTNER
    used = db.query(_Center).filter(_Center.plan == PLAN_PARTNER).count()
    return {"limit": PARTNER_SLOT_LIMIT, "used": used, "remaining": max(0, PARTNER_SLOT_LIMIT - used)}


@router.get("/directory")
def list_public_centers(q: Optional[str] = None, db: Session = Depends(get_db)):
    """센터를 못 정한 예비 보호자용 공개 디렉토리 (로그인 불필요, find_center.html이 쓴다).
    centers.router는 전체에 로그인 필수 의존성이 걸려 있어 이 엔드포인트만 별도 라우터로 분리했다."""
    query = db.query(Center).filter(Center.is_public_listed == True)  # noqa: E712
    if q:
        like = f"%{q.strip()}%"
        query = query.filter((Center.name.like(like)) | (Center.address.like(like)))
    centers = query.order_by(Center.name).all()
    return {"centers": [_to_directory_dict(c) for c in centers]}


@router.get("/nearby-facilities")
def nearby_facilities(q: str):
    """카카오맵 기반 "주변 요양시설" 참고용 검색 (로그인 불필요). 공단 인증 목록이 아니므로
    참고용임을 화면에서 반드시 밝혀야 한다 - app/kakao_local.py 모듈 docstring 참고."""
    return search_nearby_facilities(q)
