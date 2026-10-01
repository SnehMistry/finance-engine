"""Turn validated entries into totals for a month or date range."""

from __future__ import annotations

import calendar
import datetime as dt
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from finance_engine.models import Entry
from finance_engine.money import ZERO, percent


@dataclass(frozen=True, slots=True)
class Period:
    """An inclusive date range. ``None`` on either side means "unbounded"."""

    start: dt.date | None = None
    end: dt.date | None = None
    label: str = "All dates"

    @classmethod
    def for_month(cls, year: int, month: int) -> Period:
        """The whole calendar month, e.g. ``Period.for_month(2026, 9)``."""
        last_day = calendar.monthrange(year, month)[1]
        first = dt.date(year, month, 1)
        return cls(first, dt.date(year, month, last_day), first.strftime("%B %Y"))

    @classmethod
    def between(cls, start: dt.date | None, end: dt.date | None) -> Period:
        """A custom range; either end may be open."""
        if start is None and end is None:
            return cls()
        label = f"{start.isoformat() if start else 'start'} to {end.isoformat() if end else 'end'}"
        return cls(start, end, label)

    def contains(self, day: dt.date) -> bool:
        """True if ``day`` falls inside this period."""
        return (self.start is None or day >= self.start) and (self.end is None or day <= self.end)


@dataclass(frozen=True, slots=True)
class Summary:
    """All the numbers in a report. Every money value is a ``Decimal``."""

    period: Period
    income_count: int
    expense_count: int
    gross_income: Decimal
    tax: Decimal
    benefits: Decimal
    retirement: Decimal
    net_income: Decimal
    expenses_by_category: dict[str, Decimal]
    total_expenses: Decimal

    @property
    def entry_count(self) -> int:
        """Number of entries that fell inside the period."""
        return self.income_count + self.expense_count

    @property
    def total_deductions(self) -> Decimal:
        """Tax + benefits + retirement across all paychecks in the period."""
        return self.tax + self.benefits + self.retirement

    @property
    def savings(self) -> Decimal:
        """Net income minus expenses. Negative means you spent more than you earned."""
        return self.net_income - self.total_expenses

    @property
    def savings_rate(self) -> Decimal | None:
        """Savings as a percentage of net income, or ``None`` with no income."""
        return percent(self.savings, self.net_income)


def filter_entries(entries: Iterable[Entry], period: Period) -> list[Entry]:
    """Return the entries whose date falls inside ``period``."""
    return [entry for entry in entries if period.contains(entry.date)]


def summarize(entries: Iterable[Entry], period: Period | None = None) -> Summary:
    """Calculate the totals for ``period`` (all dates if not given)."""
    period = period or Period()
    selected = filter_entries(entries, period)
    income = [entry for entry in selected if entry.is_income]
    expenses = [entry for entry in selected if not entry.is_income]

    by_category: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
    for entry in expenses:
        by_category[entry.category] += entry.amount
    # Biggest spending first; ties broken alphabetically so output is stable.
    ordered = dict(sorted(by_category.items(), key=lambda item: (-item[1], item[0])))

    return Summary(
        period=period,
        income_count=len(income),
        expense_count=len(expenses),
        gross_income=sum((entry.gross_amount for entry in income), ZERO),
        tax=sum((entry.tax for entry in income), ZERO),
        benefits=sum((entry.benefits for entry in income), ZERO),
        retirement=sum((entry.retirement for entry in income), ZERO),
        net_income=sum((entry.amount for entry in income), ZERO),
        expenses_by_category=ordered,
        total_expenses=sum((entry.amount for entry in expenses), ZERO),
    )
