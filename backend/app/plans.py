"""센터의 이용 형태(체험·파트너·정식)와 그에 따른 사용 가능 범위.

- 체험(trial): TRIAL_DAYS(30일) 동안 전부 쓸 수 있다. 끝나면 **읽기 전용**(자료는 보고 내려받을 수 있지만 새로 쓰거나 고칠 수 없다).
  예전에는 체험이 끝나면 로그인이 막혀 자료도 못 봤고, 그러면 센터가 이탈하기 쉬웠다.
- 파트너(partner): 이벤트로 선정한 센터(선착순 PARTNER_SLOT_LIMIT곳). 기간 제한 없이 무료. 운영자가 지정·해제한다.
- 정식(paid): 정식 계약. 기간 제한 없음. plan이 비어 있고 체험 종료일도 없는 기존 센터도 정식으로 본다.
"""
from datetime import datetime
from typing import Optional

TRIAL_DAYS = 30
PARTNER_SLOT_LIMIT = 20
PARTNER_RESIDENT_LIMIT = 100  # 파트너 센터가 무료로 등록할 수 있는 이용자 수 (넘으면 요금제를 시작해야 한다)

# 이용자 규모 구간별 정액 (부가세 포함 총액). 인당 단가가 아니라 구간 정액이다. 101명 이상은 엔터프라이즈에서 협의한다.
FEE_BANDS = ((20, 12900), (40, 19900), (60, 27900), (100, 34900))  # (이 인원까지, 월 요금) - 신규 가입 기준, 기존 센터 요금 분리는 미구현


def monthly_fee(resident_count: int) -> Optional[int]:
    """이용자 수가 속한 구간의 월 요금(원). 101명 이상은 None (엔터프라이즈 협의)."""
    for limit, fee in FEE_BANDS:
        if resident_count <= limit:
            return fee
    return None


PLAN_TRIAL = "trial"
PLAN_PARTNER = "partner"
PLAN_PAID = "paid"

# 읽기 전용 상태에서도 할 수 있는 쓰기 (자기 프로필·알림 설정·알림 읽음 처리). 나머지 쓰기는 막는다.
READ_ONLY_ALLOWED_WRITES = (
    "/api/v1/users/me",
    "/api/v1/auth/me",
    "/api/v1/notifications/read-all",
    "/api/v1/notifications/",
    "/api/v1/admin/",
)


def center_plan_info(center, now: Optional[datetime] = None) -> dict:
    """센터의 현재 이용 상태. state: trial(체험 중) / trial_expired(체험 끝, 읽기 전용) / partner / paid."""
    now = now or datetime.utcnow()
    plan = getattr(center, "plan", None)
    ends = getattr(center, "trial_ends_at", None)
    info = {"plan": PLAN_PAID, "state": "paid", "days_left": None, "trial_ends_at": None, "read_only": False}
    if plan == PLAN_PARTNER:
        info.update(plan=PLAN_PARTNER, state="partner")
    elif plan == PLAN_PAID or ends is None:
        pass  # 정식 전환했거나 체험 제한이 없는 기존 센터
    else:
        remaining = (ends - now).total_seconds()
        info.update(plan=PLAN_TRIAL, trial_ends_at=ends.isoformat())
        if remaining > 0:
            info.update(state="trial", days_left=max(1, -(-int(remaining) // 86400)))
        else:
            info.update(state="trial_expired", days_left=0, read_only=True)
    return info


def resident_limit(center) -> Optional[int]:
    """센터가 등록할 수 있는 이용자 수 상한. 파트너만 상한이 있고, 나머지는 제한 없음(None)."""
    return PARTNER_RESIDENT_LIMIT if getattr(center, "plan", None) == PLAN_PARTNER else None


def plan_info_with_usage(db, center) -> dict:
    """center_plan_info에 파트너의 이용자 수 사용량(resident_count/resident_limit)을 더한다."""
    info = center_plan_info(center)
    limit = resident_limit(center)
    if limit is not None:
        from app.models import Resident
        info["resident_limit"] = limit
        info["resident_count"] = db.query(Resident).filter(Resident.center_id == center.id).count()
    return info


def assert_resident_capacity(db, center, adding: int = 1) -> None:
    """파트너 센터가 상한을 넘겨 이용자를 등록하려 하면 거절한다."""
    limit = resident_limit(center)
    if limit is None or not center:
        return
    from fastapi import HTTPException
    from app.models import Resident
    count = db.query(Resident).filter(Resident.center_id == center.id).count()
    if count + adding > limit:
        raise HTTPException(
            status_code=400,
            detail=f"파트너 센터는 이용자 {limit}명까지 무료입니다 (현재 {count}명). 더 등록하려면 요금제를 시작해 주세요 - 이음로직에 문의해 주세요.",
        )


def is_write_blocked(center, method: str, path: str, now: Optional[datetime] = None) -> bool:
    """쓰기를 막아야 하는 센터인지: 체험이 끝났거나, 셀프 가입 후 지정서 확인을 기다리는 중 (읽기·허용 목록은 통과)."""
    if method in ("GET", "HEAD", "OPTIONS"):
        return False
    if any(path.startswith(p) for p in READ_ONLY_ALLOWED_WRITES):
        return False
    return is_pending_verification(center) or center_plan_info(center, now)["read_only"]


def is_pending_verification(center) -> bool:
    """셀프 가입 센터는 운영자가 지정서를 확인해 verified를 True로 바꾸기 전까지 읽기 전용이다. 예전 센터는 NULL이라 해당 없음."""
    return getattr(center, "verified", None) is False


PENDING_VERIFY_MESSAGE = "가입 신청은 접수되었고, 운영자가 지정서를 확인하면 자료를 입력할 수 있습니다. 지금은 보기만 가능합니다."


def write_block_message(center) -> str:
    return PENDING_VERIFY_MESSAGE if is_pending_verification(center) else READ_ONLY_MESSAGE


READ_ONLY_MESSAGE = "무료 체험 기간이 끝나 지금은 자료를 보고 내려받기만 할 수 있습니다. 계속 쓰시려면 이음로직에 문의해 주세요."
