"""Money amounts, formatted for reports."""

from decimal import Decimal

CENT = Decimal("0.01")


def parse_amount(text: str) -> Decimal:
    """Parse an amount such as '1,234.50', '-3.25' or '$7' into a Decimal (whole cents)."""
    cleaned = text.strip().replace(",", "").replace("$", "")
    if not cleaned:
        raise ValueError("empty amount")
    negative = cleaned.startswith("-")
    whole, _, fraction = cleaned.lstrip("-").partition(".")
    if not (whole or fraction) or not (whole.isdigit() or whole == "") or (fraction and not fraction.isdigit()):
        raise ValueError(f"not an amount: {text!r}")
    cents = int(whole or "0") * 100 + int(fraction[:2] or "0")
    return (Decimal(-cents if negative else cents) / 100).quantize(CENT)


def format_amount(value: Decimal) -> str:
    """Format an amount for a report: '$1,234.50', '-$5.00'."""
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"
