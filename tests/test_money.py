from decimal import Decimal

from finance_engine.money import format_money, format_percent, percent, to_cents


def test_decimal_avoids_float_rounding_error():
    assert 0.1 + 0.2 != 0.3
    assert Decimal("0.1") + Decimal("0.2") == Decimal("0.3")


def test_to_cents_rounds_half_up():
    assert to_cents(Decimal("2.345")) == Decimal("2.35")
    assert to_cents(Decimal("2.344")) == Decimal("2.34")


def test_format_money():
    assert format_money(Decimal("1234.5")) == "$1,234.50"
    assert format_money(Decimal("-1234.5")) == "-$1,234.50"
    assert format_money(Decimal("0")) == "$0.00"


def test_percent_and_format():
    assert percent(Decimal("1"), Decimal("3")) == Decimal("33.3")
    assert percent(Decimal("2"), Decimal("3")) == Decimal("66.7")
    assert percent(Decimal("5"), Decimal("0")) is None
    assert format_percent(Decimal("12.5")) == "12.5%"
    assert format_percent(None) == "n/a"
