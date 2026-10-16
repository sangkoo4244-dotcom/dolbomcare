"""계약통보서 초안: 이용 일정과 수가로 채우고, 취소·다른 달·다른 급여 종류는 빼며, 다른 센터 이용자는 보지 못한다."""
from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.api import contract_notice
from app.api.users import create_access_token
from app.database import Base, get_db


def auth(uid, role, email):
    return {"Authorization": "Bearer " + create_access_token({"sub": email, "uid": uid, "role": role}, timedelta(hours=1))}


MANAGER = auth(1, "center_manager", "m@test.com")
CG = auth(2, "caregiver", "c@test.com")
OTHER_MANAGER = auth(5, "center_manager", "o@test.com")


@pytest.fixture
def env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'cn.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add_all([
        models.Center(id=1, name="A센터", institution_code="12345678901"),
        models.Center(id=2, name="B센터"),
        models.User(id=1, email="m@test.com", full_name="센터장", role="center_manager", center_id=1),
        models.User(id=2, email="c@test.com", full_name="요양사", role="caregiver", center_id=1),
        models.User(id=5, email="o@test.com", full_name="타센터장", role="center_manager", center_id=2),
        models.Resident(id=1, center_id=1, name="이용자", care_grade=2, client_type="일반",
                        recognition_number="L1234567890", guardian_name="보호자", guardian_phone="010-0000-0000"),
        models.Resident(id=2, center_id=2, name="타센터이용자", care_grade=2),
        # 2026-10 방문요양: 낮 60분 1회(10/5는 개천절 대체공휴일이라 제외), 밤 22:30 60분 1회(야간 30% 가산), 취소 1회
        models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=datetime(2026, 10, 12, 10, 0), duration_minutes=60, status="completed"),
        models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=datetime(2026, 10, 6, 22, 30), duration_minutes=60, status="completed"),
        models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=datetime(2026, 10, 7, 10, 0), duration_minutes=60, status="cancelled"),
        models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=datetime(2026, 11, 1, 10, 0), duration_minutes=60, status="scheduled"),
        models.Schedule(caregiver_id=2, resident_id=1, center_id=1, scheduled_date=datetime(2026, 10, 8, 10, 0), duration_minutes=60, status="scheduled", benefit_type="home_nursing"),
    ])
    db.commit()
    app = FastAPI()
    app.include_router(contract_notice.router, prefix="/api/v1/contract-notice")

    def override():
        s = Session()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override
    return TestClient(app)


def test_draft_counts_only_live_visits_in_the_month_with_fees(env):
    data = env.get("/api/v1/contract-notice/draft", params={"resident_id": 1, "benefit_type": "home_care", "year_month": "2026-10"}, headers=MANAGER).json()["data"]
    assert data["count"] == 2 and [v["date"] for v in data["visits"]] == ["2026-10-06", "2026-10-12"]
    assert [v["amount"] for v in data["visits"]] == [32920, 25320]  # 10/6 밤 60분은 30% 가산(7596원→10원 단위 32920), 10/12 낮은 기본 25320
    assert data["total"] == 25320 + 32920
    assert data["resident"]["recognition_number"] == "L1234567890"
    assert data["center"]["institution_code"] == "12345678901"
    assert data["guardian"]["phone"] == "010-0000-0000"
    assert "계약일" in data["to_fill"]


def test_nursing_draft_only_contains_nursing_visits(env):
    data = env.get("/api/v1/contract-notice/draft", params={"resident_id": 1, "benefit_type": "home_nursing", "year_month": "2026-10"}, headers=MANAGER).json()["data"]
    assert data["count"] == 1 and data["visits"][0]["date"] == "2026-10-08"


def test_caregiver_and_other_center_cannot_open_the_draft(env):
    params = {"resident_id": 1, "benefit_type": "home_care", "year_month": "2026-10"}
    assert env.get("/api/v1/contract-notice/draft", params=params, headers=CG).status_code == 403
    assert env.get("/api/v1/contract-notice/draft", params=params, headers=OTHER_MANAGER).status_code == 404
