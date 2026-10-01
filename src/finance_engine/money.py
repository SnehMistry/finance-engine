"""Small helpers for working with money as :class:`~decimal.Decimal`.

Money is never stored as ``float``: ``0.1 + 0.2`` is ``0.30000000000000004``
in binary floating point, while ``Decimal("0.1") + Decimal("0.2")`` is exactly
``Decimal("0.3")``. Every amount in this project is a ``Decimal`` with exactly
two decimal places (whole cents).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
_ONE_DECIMAL = Decimal("0.1")
_HUNDRED = Decimal("100")


def to_cents(value: Decimal) -> Decimal:
    """Round ``value`` to whole cents, rounding halves up like a receipt does."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def percent(part: Decimal, whole: Decimal) -> Decimal | None:
    """Return ``part`` as a percentage of ``whole``, rounded to one decimal place.

    Returns ``None`` when ``whole`` is zero, because the percentage is undefined
    (for example, a savings rate for a month with no income).
    """
    if whole == 0:
        return None
    return (part / whole * _HUNDRED).quantize(_ONE_DECIMAL, rounding=ROUND_HALF_UP)


def format_money(value: Decimal) -> str:
    """Format ``value`` for people, e.g. ``Decimal("-1234.5")`` -> ``"-$1,234.50"``."""
    cents = to_cents(value)
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents):,.2f}"


def format_percent(value: Decimal | None) -> str:
    """Format a percentage from :func:`percent`, using ``"n/a"`` for ``None``."""
    return "n/a" if value is None else f"{value}%"
