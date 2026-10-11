"""이메일 발송 (일반 SMTP) - 체험 센터 생성 시 센터장에게 로그인 정보를 보낸다.

SMTP 설정이 없으면 조용히 건너뛴다 - 운영자 콘솔 화면에 표시되는 비밀번호로
직접 전달하면 되므로, 메일 발송 실패가 센터 생성 자체를 막으면 안 된다.

필요한 환경변수:
    SMTP_HOST, SMTP_PORT(선택, 기본 587), SMTP_USER, SMTP_PASSWORD,
    SMTP_FROM(선택, 기본값 SMTP_USER)
"""
import os
import smtplib
from email.mime.text import MIMEText

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM") or SMTP_USER


def send_email(to: str, subject: str, body: str) -> bool:
    """성공하면 True, 설정이 없거나 실패하면 False (호출한 쪽에서 비밀번호를
    화면에 표시해 수동 전달할 수 있게 폴백한다)."""
    if not (SMTP_HOST and SMTP_USER and SMTP_PASSWORD and to):
        return False
    try:
        msg = MIMEText(body, _charset="utf-8")
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [to], msg.as_string())
        return True
    except Exception as e:  # 메일 발송 실패가 센터 생성을 막으면 안 된다
        print(f"[WARN] email send failed (to={to}): {e}")
        return False
