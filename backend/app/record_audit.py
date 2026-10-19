"""일일 기록 수정·삭제 이력. 변경 전 내용을 남겨 두어, 기록이 바뀌거나 지워졌을 때 무엇이었는지 확인할 수 있게 한다."""
import json
from datetime import datetime

from app.models import RecordAuditLog, Resident


def snapshot(record):
    """기록 한 줄의 칸 값을 사전으로 옮긴다. 날짜는 문자열로 바꾼다."""
    values = {}
    for column in record.__table__.columns:
        value = getattr(record, column.name)
        values[column.name] = value.isoformat() if isinstance(value, datetime) else value
    return values


def log_record_change(db, record, action, actor, before, after):
    resident = db.query(Resident).filter(Resident.id == record.resident_id).first()
    db.add(RecordAuditLog(
        center_id=resident.center_id if resident else actor.center_id,
        record_kind="daily",
        record_id=record.id,
        action=action,
        actor_id=actor.id,
        actor_name=actor.full_name,
        before_json=json.dumps(before, ensure_ascii=False, default=str) if before is not None else None,
        after_json=json.dumps(after, ensure_ascii=False, default=str) if after is not None else None,
    ))
