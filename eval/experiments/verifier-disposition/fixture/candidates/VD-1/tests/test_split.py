from decimal import Decimal

import pytest

from ledger.money import split_amount


def test_even_split():
    assert split_amount(Decimal("9.00"), 3) == [Decimal("3.00")] * 3


def test_leftover_cents_go_to_the_first_shares():
    assert split_amount(Decimal("10.00"), 3) == [Decimal("3.34"), Decimal("3.33"), Decimal("3.33")]


def test_shares_add_up():
    assert sum(split_amount(Decimal("100.00"), 7)) == Decimal("100.00")


def test_parts_must_be_positive():
    with pytest.raises(ValueError):
        split_amount(Decimal("1.00"), 0)
