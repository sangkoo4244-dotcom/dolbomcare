"""정기 작업 스케줄러: 하루 한 번(기본 오전 7시) 센터별 정기 점검을 돌린다.

- 외부 라이브러리 없이 asyncio로 돌린다. 서버 프로세스 안에서 한 개의 루프만 돈다.
- 작업은 모두 같은 달에 중복 발송되지 않게 되어 있어(알림마다 키 확인), 여러 프로세스가 떠도 알림이 두 번 쌓이지 않는다.
- SCHEDULER_ENABLED=0 이면 시작하지 않는다 (테스트나 점검 시). SCHEDULER_HOUR로 실행 시각을 바꾼다.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta

from app.models import Center

log = logging.getLogger("scheduler")


def seconds_until(hour: int, now: datetime | None = None) -> float:
    """다음 `hour`시 정각까지 남은 초. 이미 지났으면 내일 그 시각."""
    now = now or datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def run_daily_jobs(db) -> dict:
    """모든 센터에 대해 정기 점검을 한 번 돌린다. 결과는 작업별 발송 건수."""
    from app.api.risk_assessments import send_due_notices
    result = {"assessment_due_sent": 0, "centers": 0}
    for center in db.query(Center).all():
        result["centers"] += 1
        result["assessment_due_sent"] += send_due_notices(db, center.id)
    return result


async def _loop(hour: int, session_factory) -> None:
    while True:
        await asyncio.sleep(seconds_until(hour))
        db = session_factory()
        try:
            summary = await asyncio.to_thread(run_daily_jobs, db)
            log.info("정기 점검 완료: %s", summary)
        except Exception:
            log.exception("정기 점검 실패 (다음 실행 때 다시 시도한다)")
        finally:
            db.close()


def start(session_factory) -> asyncio.Task | None:
    """서버 시작 때 호출한다. 꺼 두었으면 None을 돌려준다."""
    if os.getenv("SCHEDULER_ENABLED", "1") != "1":
        return None
    hour = int(os.getenv("SCHEDULER_HOUR", "7"))
    return asyncio.create_task(_loop(hour, session_factory))
