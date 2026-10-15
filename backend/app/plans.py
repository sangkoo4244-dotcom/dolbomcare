"""센터의 이용 형태(체험·파트너·정식)와 그에 따른 사용 가능 범위.

- 체험(trial): TRIAL_DAYS(30일) 동안 전부 쓸 수 있다. 끝나면 **읽기 전용**(자료는 보고 내려받을 수 있지만 새로 쓰거나 고칠 수 없다).
  예전에는 체험이 끝나면 로그인이 막혀 자료도 못 봤고, 그러면 센터가 이탈하기 쉬웠다.
- 파트너(partner): 이벤트로 선정한 센터(선착순 PARTNER_SLOT_LIMIT곳). 기간 제한 없이 무료. 운영자가 지정·해제한다.
- 정식(paid): 정식 계약. 기간 제한 없음. plan이 비어 있고 체험 종료일도 없는 기존 센터도 정식으로 본다.
"""
from datetime import datetime
from typing import Optional

TRIAL_DAYS = 30
PARTNER_SLOT_LIMIT = 30

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


def is_write_blocked(center, method: str, path: str, now: Optional[datetime] = None) -> bool:
    """체험이 끝난 센터의 쓰기 요청인지 (읽기·허용 목록은 통과)."""
    if method in ("GET", "HEAD", "OPTIONS"):
        return False
    if any(path.startswith(p) for p in READ_ONLY_ALLOWED_WRITES):
        return False
    return center_plan_info(center, now)["read_only"]


READ_ONLY_MESSAGE = "무료 체험 기간이 끝나 지금은 자료를 보고 내려받기만 할 수 있습니다. 계속 쓰시려면 이음로직에 문의해 주세요."
