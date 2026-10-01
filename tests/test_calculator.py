import datetime as dt
from decimal import Decimal

from conftest import make_entry, paycheck

from finance_engine.calculator import Period, filter_entries, summarize


def test_period_for_month_handles_month_lengths():
    assert Period.for_month(2026, 9).end == dt.date(2026, 9, 30)
    assert Period.for_month(2028, 2).end == dt.date(2028, 2, 29)
    assert Period.for_month(2026, 12).label == "December 2026"


def test_period_between():
    period = Period.between(dt.date(2026, 9, 1), None)
    assert period.label == "2026-09-01 to end"
    assert period.contains(dt.date(2030, 1, 1))
    assert not period.contains(dt.date(2026, 8, 31))
    assert Period.between(None, dt.date(2026, 9, 1)).label == "start to 2026-09-01"
    assert Period.between(None, None) == Period()


def test_period_boundaries_are_inclusive():
    period = Period.for_month(2026, 9)
    assert period.contains(dt.date(2026, 9, 1))
    assert period.contains(dt.date(2026, 9, 30))
    assert not period.contains(dt.date(2026, 10, 1))


def test_filter_entries():
    entries = [make_entry(date="2026-08-31"), make_entry(date="2026-09-01")]
    assert filter_entries(entries, Period.for_month(2026, 9)) == [entries[1]]


def test_full_summary():
    entries = [
        paycheck(row=2),
        make_entry(row=3, type="income", category="freelance", amount="400.00"),
        make_entry(row=4, category="housing", amount="1500.00"),
        make_entry(row=5, category="groceries", amount="80.10"),
        make_entry(row=6, category="groceries", amount="19.90"),
        make_entry(row=7, category="dining", amount="100.00"),
    ]
    summary = summarize(entries)

    assert summary.income_count == 2 and summary.expense_count == 4 and summary.entry_count == 6
    # freelance has no gross column, so its gross is its net amount
    assert summary.gross_income == Decimal("3400.00")
    assert (summary.tax, summary.benefits, summary.retirement) == (Decimal("600"), Decimal("150"), Decimal("150"))
    assert summary.total_deductions == Decimal("900.00")
    assert summary.net_income == Decimal("2500.00")
    assert summary.total_expenses == Decimal("1700.00")
    assert summary.savings == Decimal("800.00")
    assert summary.savings_rate == Decimal("32.0")
    # sorted biggest first, ties alphabetical
    assert list(summary.expenses_by_category) == ["housing", "dining", "groceries"]
    assert summary.expenses_by_category["groceries"] == Decimal("100.00")


def test_gross_is_net_plus_deductions_when_gross_blank():
    entry = make_entry(type="income", category="salary", amount="800.00", tax="200.00")
    assert summarize([entry]).gross_income == Decimal("1000.00")


def test_summary_only_counts_the_period():
    entries = [make_entry(date="2026-08-15", amount="999.00"), make_entry(date="2026-09-15", amount="1.00")]
    assert summarize(entries, Period.for_month(2026, 9)).total_expenses == Decimal("1.00")


def test_month_with_no_data():
    summary = summarize([make_entry(date="2026-08-15")], Period.for_month(2026, 9))
    assert summary.entry_count == 0
    assert summary.net_income == summary.total_expenses == summary.savings == Decimal("0")
    assert summary.savings_rate is None
    assert summary.expenses_by_category == {}


def test_negative_savings_rate_when_overspending():
    entries = [make_entry(type="income", category="salary", amount="1000.00"), make_entry(amount="1500.00")]
    summary = summarize(entries)
    assert summary.savings == Decimal("-500.00")
    assert summary.savings_rate == Decimal("-50.0")


def test_money_sums_are_exact():
    entries = [make_entry(row=i, amount="0.10", description=str(i)) for i in range(10)]
    assert summarize(entries).total_expenses == Decimal("1.00")
