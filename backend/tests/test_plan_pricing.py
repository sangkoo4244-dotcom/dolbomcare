"""이용자 규모 구간별 정액: 1~20명 19,900원, 21~50명 29,900원, 51~100명 39,900원, 101명 이상은 협의."""
import pytest

from app.plans import monthly_fee


@pytest.mark.parametrize("count, fee", [(1, 19900), (20, 19900), (21, 29900), (50, 29900), (51, 39900), (100, 39900)])
def test_monthly_fee_follows_the_band(count, fee):
    assert monthly_fee(count) == fee


def test_over_100_residents_is_negotiated_not_priced():
    assert monthly_fee(101) is None
