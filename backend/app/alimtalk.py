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


def sms_configured() -> bool:
    return bool(SOLAPI_API_KEY and SOLAPI_API_SECRET and SOLAPI_SENDER_PHONE)


def send_sms(phone: str, text: str) -> bool:
    """문자(SMS)를 보낸다. 템플릿이 필요 없는 자유 문장이다. 발송이 접수되면 True.
    발신번호(SOLAPI_SENDER_PHONE)는 솔라피에 미리 등록된 번호여야 한다."""
    if not (sms_configured() and phone and text):
        return False
    date = datetime.now(timezone.utc).isoformat()
    salt = uuid.uuid4().hex
    try:
        response = httpx.post(
            "https://api.solapi.com/messages/v4/send",
            headers={"Authorization": f"HMAC-SHA256 apiKey={SOLAPI_API_KEY}, date={date}, salt={salt}, signature={_signature(date, salt)}"},
            json={"message": {"to": phone, "from": SOLAPI_SENDER_PHONE, "text": text, "type": "SMS"}},
            timeout=5,
        )
        return response.status_code < 300
    except Exception as e:  # 문자 실패가 본 요청을 막으면 안 된다
        print(f"[WARN] sms send failed: {e}")
        return False
