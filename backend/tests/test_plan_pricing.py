"""이용자 수에 따른 월 요금: 10명까지 9,900원, 10명을 넘으면 1명당 500원, 100명을 넘으면 협의."""
import pytest

from app.plans import monthly_fee


@pytest.mark.parametrize("count, fee", [(1, 9900), (10, 9900), (11, 10400), (20, 14900), (30, 19900), (50, 29900), (100, 54900)])
def test_monthly_fee_follows_the_published_table(count, fee):
    assert monthly_fee(count) == fee


def test_over_100_residents_is_negotiated_not_priced():
    assert monthly_fee(101) is None
