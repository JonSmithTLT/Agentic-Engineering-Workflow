"""Money amounts: parsed exactly as Decimal, formatted for reports."""

from decimal import ROUND_DOWN, Decimal, InvalidOperation

CENT = Decimal("0.01")


def parse_amount(text: str) -> Decimal:
    """Parse an amount such as '1,234.50', '-12.5' or '$7' into a Decimal rounded to cents."""
    cleaned = text.strip().replace(",", "").replace("$", "")
    if not cleaned:
        raise ValueError("empty amount")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"not an amount: {text!r}") from None
    return value.quantize(CENT)


def format_amount(value: Decimal) -> str:
    """Format an amount for a report: '$1,234.50', '-$5.00'."""
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.2f}"


def split_amount(total: Decimal, parts: int) -> list[Decimal]:
    """Split a non-negative ``total`` into ``parts`` shares in whole cents that add up exactly to it; leftover
    cents go one each to the first shares."""
    if parts < 1:
        raise ValueError("parts must be at least 1")
    share = (total / parts).quantize(CENT, rounding=ROUND_DOWN)
    leftover = int((total - share * parts) / CENT)
    return [share + CENT if i < leftover else share for i in range(parts)]
