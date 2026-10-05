from datetime import datetime, timedelta
from types import SimpleNamespace

from app.api.schedule import _visit_state

NOW = datetime(2026, 10, 5, 12, 0)
PAST = NOW - timedelta(hours=1)
FUTURE = NOW + timedelta(hours=1)


def plan(status="scheduled", scheduled_date=FUTURE, arrived_at=None, left_at=None):
    return SimpleNamespace(status=status, scheduled_date=scheduled_date, arrived_at=arrived_at, left_at=left_at)


def test_proposed_waits_for_approval():
    assert _visit_state(plan(status="proposed"), None, NOW) == "승인 대기"


def test_rejected_plan():
    assert _visit_state(plan(status="rejected"), None, NOW) == "반려"


def test_upcoming_plan_is_scheduled():
    assert _visit_state(plan(), None, NOW) == "예정"


def test_missed_plan_without_arrival_is_unrecorded():
    assert _visit_state(plan(scheduled_date=PAST), None, NOW) == "미기록"


def test_arrived_but_not_left_is_visiting():
    assert _visit_state(plan(arrived_at=NOW), None, NOW) == "방문중"


def test_left_without_record_is_visit_done_needing_record():
    assert _visit_state(plan(arrived_at=PAST, left_at=NOW), None, NOW) == "방문완료"


def test_record_saved_marks_complete():
    assert _visit_state(plan(arrived_at=PAST, left_at=NOW), object(), NOW) == "완료"
