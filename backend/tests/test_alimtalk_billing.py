import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.alimtalk_billing import FREE_QUOTA_PER_MONTH, PER_MESSAGE_COST, get_usage_summary, reserve_send
from app.database import Base


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(models.Center(id=1, name="테스트센터", alimtalk_balance=0))
    session.commit()
    yield session
    session.close()


def test_free_quota_consumed_first(db):
    assert reserve_send(db, 1) is True
    db.commit()
    usage = get_usage_summary(db, 1)
    assert usage["free_sent"] == 1
    assert usage["paid_sent"] == 0


def test_falls_back_to_balance_after_free_quota(db):
    center = db.query(models.Center).filter(models.Center.id == 1).first()
    center.alimtalk_balance = PER_MESSAGE_COST * 2
    db.commit()

    for _ in range(FREE_QUOTA_PER_MONTH):
        assert reserve_send(db, 1) is True
    db.commit()

    assert reserve_send(db, 1) is True  # 무료 소진 후 잔액 사용
    db.commit()
    usage = get_usage_summary(db, 1)
    assert usage["paid_sent"] == 1
    assert usage["balance"] == PER_MESSAGE_COST


def test_blocked_when_quota_and_balance_exhausted(db):
    for _ in range(FREE_QUOTA_PER_MONTH):
        assert reserve_send(db, 1) is True
    db.commit()

    assert reserve_send(db, 1) is False  # 무료 소진, 잔액도 0
    db.commit()
    usage = get_usage_summary(db, 1)
    assert usage["blocked_count"] == 1


def test_no_center_id_returns_false(db):
    assert reserve_send(db, None) is False
