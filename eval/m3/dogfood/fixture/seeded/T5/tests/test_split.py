from decimal import Decimal

import pytest

from ledger.money import split_amount


def test_even_split():
    assert split_amount(Decimal("9.00"), 3) == [Decimal("3.00")] * 3


def test_parts_must_be_positive():
    with pytest.raises(ValueError):
        split_amount(Decimal("1.00"), 0)
