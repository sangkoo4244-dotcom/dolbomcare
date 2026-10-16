"""급여제공계획서 전산 등록 입력 시트: 공단 화면 탭 순서대로 값을 나누고, 빠진 값을 알려 준다 (엑셀 업로드 대신 쓰는 입력 보조)."""
from tests.test_care_plans import CAREGIVER, MANAGER, body, env  # noqa: F401  (픽스처 재사용)


def plan_id(client):
    return client.post("/api/v1/care-plans", json=body(), headers=MANAGER).json()["data"]["id"]


def test_entry_sheet_follows_the_nhis_tab_order(env):
    db, client = env
    pid = plan_id(client)
    r = client.get(f"/api/v1/care-plans/{pid}/entry-sheet", headers=MANAGER)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert [t["tab"].split(" ")[0] for t in data["tabs"]] == ["등록", "필요내용", "목표주기", "통보"]
    fields = {f["label"].split(" (")[0]: f["value"] for t in data["tabs"] for f in t["fields"]}
    assert fields["적용기간 시작일"] == "2026-10-10" and fields["작성일자"] == "2026-10-05"
    assert fields["필요영역·필요내용"] == "보행 보조와 식사 준비"
    assert fields["세부제공내용"] == "신체활동 지원, 식사 준비, 청소"
    assert fields["횟수"] == "주 5회" and fields["1회 제공시간(분)"] == "180"
    assert fields["세부목표"] == "낙상 없이 일상생활 유지" and fields["종합의견"].startswith("허리 통증")
    # 시스템 전송이 아니므로 공단 쪽에서만 입력하는 값은 비워 둔다
    assert fields["적용기간 종료일"] == "" and fields["개인별장기요양이용계획서 번호"] == ""


def test_missing_values_are_listed_as_warnings(env):
    db, client = env
    pid = plan_id(client)
    from app import models
    plan = db.query(models.CarePlan).filter(models.CarePlan.id == pid).one()
    plan.goals, plan.guardian_signed_date, plan.duration_minutes = "", None, None
    db.commit()
    w = client.get(f"/api/v1/care-plans/{pid}/entry-sheet", headers=MANAGER).json()["data"]["warnings"]
    assert any("세부목표" in x for x in w) and any("동의일" in x for x in w) and any("1회 제공시간" in x for x in w)


def test_change_plan_without_reason_is_flagged_and_tenant_is_isolated(env):
    db, client = env
    pid = plan_id(client)
    from app import models
    plan = db.query(models.CarePlan).filter(models.CarePlan.id == pid).one()
    plan.plan_type = "change"
    db.commit()
    assert any("변경 사유" in x for x in client.get(f"/api/v1/care-plans/{pid}/entry-sheet", headers=MANAGER).json()["data"]["warnings"])
    # 요양보호사는 볼 수 없다 (센터장 전용)
    assert client.get(f"/api/v1/care-plans/{pid}/entry-sheet", headers=CAREGIVER).status_code in (403,)
    assert client.get("/api/v1/care-plans/9999/entry-sheet", headers=MANAGER).status_code == 404
