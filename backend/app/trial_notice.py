"""체험 종료 안내: 체험이 끝나기 7일 전·하루 전, 끝난 뒤에 그 센터의 센터장에게 앱 안 알림을 한 번씩 보낸다.

따로 도는 예약 작업이 없어서, 센터장이 로그인하거나 화면을 열 때(/users/me) 확인해서 보낸다.
단계마다 한 번만 보내도록 같은 종류의 알림이 이미 있는지 먼저 본다. 이 확인이 실패해도 로그인·화면은 막지 않는다.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.api.notifications import notify
from app.models import Notification, User
from app.plans import center_plan_info

MESSAGES = {
    "trial_d7": "무료 체험이 {days}일 뒤에 끝납니다. 체험이 끝나면 자료는 그대로 보이지만 새 기록과 청구는 쓸 수 없게 됩니다. 이어 쓰시려면 요금제를 시작해 주세요.",
    "trial_d1": "무료 체험이 내일 끝납니다. 끝나면 자료는 볼 수 있지만 새 기록과 청구는 쓸 수 없게 됩니다. 이어 쓰시려면 요금제를 시작해 주세요.",
    "trial_expired": "무료 체험이 끝나 지금은 자료를 보고 내려받기만 할 수 있습니다. 요금제를 시작하면 바로 다시 기록과 청구를 쓸 수 있습니다.",
}


def trial_stage(info: dict) -> Optional[str]:
    if info["state"] == "trial_expired":
        return "trial_expired"
    if info["state"] == "trial" and info["days_left"] is not None:
        if info["days_left"] <= 1:
            return "trial_d1"
        if info["days_left"] <= 7:
            return "trial_d7"
    return None


def maybe_notify_trial(db: Session, center, now: Optional[datetime] = None) -> Optional[str]:
    """보낼 단계가 있고 아직 안 보냈으면 센터장들에게 알림을 만든다(commit 포함). 보낸 단계 이름을 돌려준다."""
    if not center:
        return None
    info = center_plan_info(center, now)
    stage = trial_stage(info)
    if not stage:
        return None
    managers = db.query(User).filter(User.center_id == center.id, User.role == "center_manager", User.is_active == True).all()  # noqa: E712
    sent = False
    for manager in managers:
        already = db.query(Notification).filter(Notification.user_id == manager.id, Notification.kind == stage,
                                                Notification.created_at >= (center.trial_ends_at.replace(year=center.trial_ends_at.year - 1) if center.trial_ends_at else datetime.min)).first()
        if already:
            continue
        notify(db, manager.id, stage, MESSAGES[stage].format(days=info["days_left"] or 0))
        sent = True
    if sent:
        db.commit()
    return stage if sent else None
