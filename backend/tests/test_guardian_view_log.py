"""보호자가 방문 기록을 열어 본 흔적을 남기고, 센터장만 우리 센터 이용자의 열람 기록을 본다 (공단 다빈도 Q&A Q57 증빙)."""
from app import models
from tests.test_guardian import CAREGIVER, MANAGER, approve_latest, auth, issue_code, setup, signup  # noqa: F401  (픽스처 재사용)


def guardian_headers(setup_):
    db = setup_.Session()
    gid = db.query(models.User).filter(models.User.email == "guardian@test.com").first().id
    db.close()
    return auth(gid, "guardian", "guardian@test.com")


def test_each_guardian_view_is_logged_and_manager_can_read_it(setup):
    code = issue_code(setup)
    signup(setup, code)
    assert approve_latest(setup).status_code == 200
    headers = guardian_headers(setup)

    assert setup.get("/api/v1/guardian/residents/1/visits", headers=headers, params={"days": 365}).status_code == 200
    setup.get("/api/v1/guardian/residents/1/visits", headers=headers, params={"days": 365})

    logs = setup.get("/api/v1/guardian/view-logs", headers=MANAGER, params={"resident_id": 1}).json()
    assert logs["resident_name"] and len(logs["logs"]) == 2
    assert logs["logs"][0]["guardian_name"] and logs["logs"][0]["kind"] == "visits"


def test_view_logs_are_only_for_own_center_and_managers(setup):
    code = issue_code(setup)
    signup(setup, code)
    assert approve_latest(setup).status_code == 200
    # 요양보호사와 보호자는 열람 기록을 볼 수 없다
    assert setup.get("/api/v1/guardian/view-logs", headers=CAREGIVER, params={"resident_id": 1}).status_code == 403
    assert setup.get("/api/v1/guardian/view-logs", headers=guardian_headers(setup), params={"resident_id": 1}).status_code == 403
    # 없는 이용자 번호는 404
    assert setup.get("/api/v1/guardian/view-logs", headers=MANAGER, params={"resident_id": 999}).status_code == 404
