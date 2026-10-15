import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.billing_rules import split_benefit, split_visit
from app.database import Base
from app.visit_benefit import job_type_of, normalize_visit_benefit


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'vb.db'}")
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    s.add_all([
        models.Center(id=1, name="방문센터", service_types="방문요양,방문목욕,방문간호"),
        models.Center(id=2, name="요양만", service_types="방문요양"),
        models.Center(id=3, name="미설정"),
        models.User(id=1, email="a@t.com", full_name="요양A", role="caregiver", center_id=1),
        models.User(id=2, email="b@t.com", full_name="요양B", role="caregiver", center_id=1),
        models.User(id=3, email="n@t.com", full_name="간호사N", role="caregiver", center_id=1, job_type="간호사"),
        models.User(id=4, email="o@t.com", full_name="타센터요양", role="caregiver", center_id=2),
        models.User(id=5, email="g@t.com", full_name="보호자", role="guardian", center_id=1),
    ])
    s.commit()
    return s


def err(call):
    with pytest.raises(HTTPException) as e:
        call()
    assert e.value.status_code == 400
    return e.value.detail


def test_fee_split_by_benefit_uses_nhis_table_and_copay_rates():
    assert split_benefit(None, 60, "일반") == split_visit(60, "일반") == (25320, 3790, 21530)  # 방문요양은 기존과 같다
    assert split_benefit("home_bath", None, "일반", "vehicle_in") == (88990, 13340, 75650)
    assert split_benefit("home_bath", 70, "기초생활보장", "no_vehicle") == (50100, 0, 50100)
    assert split_benefit("home_nursing", 45, "일반") == (53770, 8060, 45710)
    with pytest.raises(ValueError):
        split_benefit("home_nursing", 10, "일반")  # 15분 미만은 청구 불가
    with pytest.raises(ValueError):
        split_benefit("day_night", 300, "일반")  # 방문 급여가 아니다


def test_home_care_defaults_work_without_any_new_fields(db):
    assert normalize_visit_benefit(db, center_id=3, caregiver_id=1) == {"benefit_type": "home_care", "bath_mode": None, "co_caregiver_id": None}
    assert normalize_visit_benefit(db, center_id=1, caregiver_id=1, benefit_type="home_care", duration_minutes=60)["benefit_type"] == "home_care"
    assert "30" in err(lambda: normalize_visit_benefit(db, center_id=1, caregiver_id=1, duration_minutes=45, strict_home_care_duration=True))  # 기록은 정해진 시간만
    assert normalize_visit_benefit(db, center_id=1, caregiver_id=1, duration_minutes=45)["benefit_type"] == "home_care"  # 일정 계획은 예전처럼 제한 없음


def test_bath_and_nursing_need_the_center_to_offer_them(db):
    assert "센터 정보" in err(lambda: normalize_visit_benefit(db, center_id=2, caregiver_id=4, benefit_type="home_bath", bath_mode="vehicle_in", co_caregiver_id=1))
    assert "센터 정보" in err(lambda: normalize_visit_benefit(db, center_id=3, caregiver_id=1, benefit_type="home_nursing"))
    assert "골라" in err(lambda: normalize_visit_benefit(db, center_id=1, caregiver_id=1, benefit_type="day_night"))


def test_bath_needs_mode_and_a_second_caregiver_from_the_same_center(db):
    ok = normalize_visit_benefit(db, center_id=1, caregiver_id=1, benefit_type="home_bath", bath_mode="vehicle_home", co_caregiver_id=2, duration_minutes=60)
    assert ok == {"benefit_type": "home_bath", "bath_mode": "vehicle_home", "co_caregiver_id": 2}
    assert "방식" in err(lambda: normalize_visit_benefit(db, center_id=1, caregiver_id=1, benefit_type="home_bath", co_caregiver_id=2))
    assert "2인" in err(lambda: normalize_visit_benefit(db, center_id=1, caregiver_id=1, benefit_type="home_bath", bath_mode="vehicle_in"))
    assert "2인" in err(lambda: normalize_visit_benefit(db, center_id=1, caregiver_id=1, benefit_type="home_bath", bath_mode="vehicle_in", co_caregiver_id=1))
    assert "우리 센터" in err(lambda: normalize_visit_benefit(db, center_id=1, caregiver_id=1, benefit_type="home_bath", bath_mode="vehicle_in", co_caregiver_id=4))
    assert "우리 센터" in err(lambda: normalize_visit_benefit(db, center_id=1, caregiver_id=1, benefit_type="home_bath", bath_mode="vehicle_in", co_caregiver_id=5))
    assert "우리 센터" in err(lambda: normalize_visit_benefit(db, center_id=1, caregiver_id=1, benefit_type="home_bath", bath_mode="vehicle_in", co_caregiver_id=3))  # 함께 가는 사람이 간호사
    assert "요양보호사가 제공" in err(lambda: normalize_visit_benefit(db, center_id=1, caregiver_id=3, benefit_type="home_bath", bath_mode="vehicle_in", co_caregiver_id=2))


def test_nursing_is_for_nursing_staff_and_needs_15_minutes(db):
    ok = normalize_visit_benefit(db, center_id=1, caregiver_id=3, benefit_type="home_nursing", duration_minutes=30)
    assert ok == {"benefit_type": "home_nursing", "bath_mode": None, "co_caregiver_id": None}
    assert "직종" in err(lambda: normalize_visit_benefit(db, center_id=1, caregiver_id=1, benefit_type="home_nursing", duration_minutes=30))
    assert "15분" in err(lambda: normalize_visit_benefit(db, center_id=1, caregiver_id=3, benefit_type="home_nursing", duration_minutes=10))
    assert "시간" in err(lambda: normalize_visit_benefit(db, center_id=1, caregiver_id=3, benefit_type="home_nursing", require_duration=True))
    assert job_type_of(None) == "요양보호사" and job_type_of(db.query(models.User).get(1)) == "요양보호사"
