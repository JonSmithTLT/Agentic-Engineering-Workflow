from decimal import Decimal

import pytest

from ledger.money import split_amount


def test_even_split():
    assert split_amount(Decimal("9.00"), 3) == [Decimal("3.00")] * 3


def test_shares_add_up_in_whole_cents():
    for total, parts in ((Decimal("10.00"), 3), (Decimal("100.00"), 7), (Decimal("0.05"), 2)):
        shares = split_amount(total, parts)
        assert sum(shares) == total
        assert all(share == share.quantize(Decimal("0.01")) for share in shares)


def test_parts_must_be_positive():
    with pytest.raises(ValueError):
        split_amount(Decimal("1.00"), 0)
