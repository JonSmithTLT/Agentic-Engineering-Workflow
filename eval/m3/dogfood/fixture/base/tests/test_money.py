from decimal import Decimal

import pytest

from ledger.money import format_amount, parse_amount


def test_parse_amount():
    assert parse_amount("12.50") == Decimal("12.50")
    assert parse_amount("1,234.56") == Decimal("1234.56")
    assert parse_amount("$7") == Decimal("7.00")
    assert parse_amount("-3.25") == Decimal("-3.25")


def test_parse_amount_rejects_garbage():
    with pytest.raises(ValueError):
        parse_amount("twelve")
    with pytest.raises(ValueError):
        parse_amount("  ")


def test_format_amount():
    assert format_amount(Decimal("1234.5")) == "$1,234.50"
    assert format_amount(Decimal("0")) == "$0.00"
