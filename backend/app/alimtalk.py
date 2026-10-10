"""카카오 알림톡 발송 (솔라피 연동).

API 키/템플릿이 설정되지 않은 동안은 조용히 건너뛴다 - 인앱 알림(Notification)은
이 모듈과 무관하게 항상 동작해야 하므로, 여기서 실패해도 전체 요청을 막지 않는다.

필요한 환경변수:
    SOLAPI_API_KEY, SOLAPI_API_SECRET, SOLAPI_SENDER_PHONE, SOLAPI_PFID
    (카카오 비즈니스채널 + 솔라피 가입, 템플릿 승인 후 채워 넣는다)
    ALIMTALK_TEMPLATE_RECORD_NEEDED, ALIMTALK_TEMPLATE_MESSAGE_RECEIVED,
    ALIMTALK_TEMPLATE_VISIT_COMPLETED, ALIMTALK_TEMPLATE_CHANGE_REJECTED
    (알림톡 템플릿 승인 후 발급되는 템플릿 ID)
"""
import hashlib
import hmac
import os
import uuid
from datetime import datetime, timezone

import httpx

SOLAPI_API_KEY = os.getenv("SOLAPI_API_KEY")
SOLAPI_API_SECRET = os.getenv("SOLAPI_API_SECRET")
SOLAPI_SENDER_PHONE = os.getenv("SOLAPI_SENDER_PHONE")
SOLAPI_PFID = os.getenv("SOLAPI_PFID")  # 카카오 비즈니스채널 ID

# notify()의 kind -> 솔라피 템플릿 ID. 템플릿 미승인 상태면 값이 비어 있고,
# 그 kind는 알림톡을 보내지 않는다 (인앱 알림만 동작).
TEMPLATE_IDS = {
    "record_needed": os.getenv("ALIMTALK_TEMPLATE_RECORD_NEEDED"),
    "message_received": os.getenv("ALIMTALK_TEMPLATE_MESSAGE_RECEIVED"),
    "visit_completed": os.getenv("ALIMTALK_TEMPLATE_VISIT_COMPLETED"),
    "change_rejected": os.getenv("ALIMTALK_TEMPLATE_CHANGE_REJECTED"),
    "plan_approved": os.getenv("ALIMTALK_TEMPLATE_PLAN_APPROVED"),
    "plan_rejected": os.getenv("ALIMTALK_TEMPLATE_PLAN_REJECTED"),
    "schedule_today": os.getenv("ALIMTALK_TEMPLATE_SCHEDULE_TODAY"),
}


def _signature(date: str, salt: str) -> str:
    return hmac.new(SOLAPI_API_SECRET.encode(), (date + salt).encode(), hashlib.sha256).hexdigest()


def send_alimtalk(phone: str, kind: str, message: str) -> None:
    template_id = TEMPLATE_IDS.get(kind)
    if not (SOLAPI_API_KEY and SOLAPI_API_SECRET and SOLAPI_SENDER_PHONE and SOLAPI_PFID and template_id and phone):
        return

    date = datetime.now(timezone.utc).isoformat()
    salt = uuid.uuid4().hex
    signature = _signature(date, salt)

    try:
        httpx.post(
            "https://api.solapi.com/messages/v4/send",
            headers={
                "Authorization": (
                    f"HMAC-SHA256 apiKey={SOLAPI_API_KEY}, date={date}, salt={salt}, signature={signature}"
                ),
            },
            json={
                "message": {
                    "to": phone,
                    "from": SOLAPI_SENDER_PHONE,
                    "kakaoOptions": {
                        "pfId": SOLAPI_PFID,
                        "templateId": template_id,
                        "variables": {"#{message}": message},
                    },
                }
            },
            timeout=5,
        )
    except Exception as e:  # 알림톡 실패가 본 요청을 막으면 안 된다
        print(f"[WARN] alimtalk send failed (kind={kind}): {e}")
