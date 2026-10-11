"""알림톡 충전형 과금 - 월 무료 발송 한도를 넘기면 센터의 충전 잔액에서 건당 차감한다.

실제 결제(충전) 연동은 아직 없다 - 센터장이 /pages/center_settings.html에서 잔액·사용량만
확인하고, 충전은 문의 메일로 안내한다 (운영진이 수동으로 Center.alimtalk_balance를 올려준다).

한도·잔액이 모두 소진되면 알림톡만 건너뛰고, 인앱 알림(Notification)은 이 모듈과 무관하게
항상 그대로 저장된다 - notifications.py의 notify()가 이미 그렇게 설계돼 있다.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import AlimtalkUsage, Center

FREE_QUOTA_PER_MONTH = 100  # 센터당 월 무료 알림톡 발송 건수
PER_MESSAGE_COST = 20  # 무료 한도를 넘긴 뒤 건당 차감액(원)


def _current_year_month() -> str:
    return datetime.utcnow().strftime("%Y-%m")


def _get_or_create_usage(db: Session, center_id: int, year_month: str) -> AlimtalkUsage:
    usage = db.query(AlimtalkUsage).filter(
        AlimtalkUsage.center_id == center_id, AlimtalkUsage.year_month == year_month
    ).first()
    if not usage:
        usage = AlimtalkUsage(center_id=center_id, year_month=year_month)
        db.add(usage)
        db.flush()
    return usage


def reserve_send(db: Session, center_id: int) -> bool:
    """알림톡 1건을 보내도 되는지 확인하고, 가능하면 무료 한도 또는 충전 잔액에서 즉시 차감한다.
    True를 반환할 때만 실제로 발송해야 한다 (커밋은 호출한 쪽의 책임 - notify()와 같은 패턴)."""
    if not center_id:
        return False

    year_month = _current_year_month()
    usage = _get_or_create_usage(db, center_id, year_month)

    if usage.free_sent < FREE_QUOTA_PER_MONTH:
        usage.free_sent += 1
        return True

    center = db.query(Center).filter(Center.id == center_id).first()
    if center and (center.alimtalk_balance or 0) >= PER_MESSAGE_COST:
        center.alimtalk_balance -= PER_MESSAGE_COST
        usage.paid_sent += 1
        return True

    usage.blocked_count += 1
    return False


def get_usage_summary(db: Session, center_id: int) -> dict:
    year_month = _current_year_month()
    usage = db.query(AlimtalkUsage).filter(
        AlimtalkUsage.center_id == center_id, AlimtalkUsage.year_month == year_month
    ).first()
    center = db.query(Center).filter(Center.id == center_id).first()
    return {
        "year_month": year_month,
        "free_quota": FREE_QUOTA_PER_MONTH,
        "free_sent": usage.free_sent if usage else 0,
        "paid_sent": usage.paid_sent if usage else 0,
        "blocked_count": usage.blocked_count if usage else 0,
        "balance": (center.alimtalk_balance or 0) if center else 0,
        "per_message_cost": PER_MESSAGE_COST,
    }
