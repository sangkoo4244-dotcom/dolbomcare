"""로그인 시도 제한: 같은 계정에 짧은 시간 안에 비밀번호를 여러 번 틀리면 잠깐 막는다.
메모리에만 기록하므로 서버를 다시 띄우면 초기화된다(단일 서버 배포 전제). 이 검사가 실패해도 로그인은 막지 않는다."""
import threading
from datetime import datetime, timedelta

MAX_FAILURES = 5
FAILURE_WINDOW = timedelta(minutes=10)
LOCK_DURATION = timedelta(minutes=15)

_lock = threading.Lock()
_failures: dict[str, list[datetime]] = {}
_locked_until: dict[str, datetime] = {}


def _key(email: str) -> str:
    return (email or "").strip().lower()


def seconds_until_unlocked(email: str, now: datetime | None = None) -> int:
    now = now or datetime.now()
    with _lock:
        until = _locked_until.get(_key(email))
        if until and until > now:
            return int((until - now).total_seconds()) + 1
        if until:
            _locked_until.pop(_key(email), None)
    return 0


def record_failure(email: str, now: datetime | None = None) -> None:
    now = now or datetime.now()
    key = _key(email)
    with _lock:
        recent = [t for t in _failures.get(key, []) if now - t < FAILURE_WINDOW]
        recent.append(now)
        if len(recent) >= MAX_FAILURES:
            _locked_until[key] = now + LOCK_DURATION
            _failures.pop(key, None)
        else:
            _failures[key] = recent
        if len(_failures) > 10000:  # 메모리 보호: 오래된 기록 정리
            for k in [k for k, v in _failures.items() if not v or now - v[-1] > FAILURE_WINDOW]:
                _failures.pop(k, None)


def clear(email: str) -> None:
    key = _key(email)
    with _lock:
        _failures.pop(key, None)
        _locked_until.pop(key, None)


def reset_all() -> None:
    with _lock:
        _failures.clear()
        _locked_until.clear()
