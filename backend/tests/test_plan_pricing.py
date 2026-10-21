"""이용자 규모 구간별 정액: 1~20명 14,900원, 21~40명 19,900원, 41~60명 27,900원, 61~100명 34,900원, 101명 이상은 협의."""
import pytest

from app.plans import monthly_fee


@pytest.mark.parametrize("count, fee", [(1, 14900), (20, 14900), (21, 19900), (40, 19900), (41, 27900), (60, 27900), (61, 34900), (100, 34900)])
def test_monthly_fee_follows_the_band(count, fee):
    assert monthly_fee(count) == fee


def test_over_100_residents_is_negotiated_not_priced():
    assert monthly_fee(101) is None
