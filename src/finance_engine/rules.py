"""Rule-based warnings about a :class:`~finance_engine.calculator.Summary`.

Each rule is a small, independent function that returns a list of
:class:`Alert` objects, which keeps rules easy to test and easy to add.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from finance_engine.calculator import Summary, filter_entries
from finance_engine.models import Entry
from finance_engine.money import ZERO, format_money, percent

DEFAULT_CATEGORY_LIMIT_PCT = Decimal("30")
DEFAULT_LARGE_EXPENSE_MULTIPLIER = Decimal("3")
DEFAULT_MIN_HISTORY = 2


@dataclass(frozen=True)
class RuleConfig:
    """Thresholds for the rules. Defaults can be overridden from the CLI.

    Attributes:
        category_limit_pct: Warn when one expense category is more than this
            percentage of net income.
        large_expense_multiplier: Warn when an expense is more than this many
            times the average of the *other* expenses in the same category.
        min_history: How many other expenses a category needs before the
            large-expense rule trusts its average.
    """

    category_limit_pct: Decimal = DEFAULT_CATEGORY_LIMIT_PCT
    large_expense_multiplier: Decimal = DEFAULT_LARGE_EXPENSE_MULTIPLIER
    min_history: int = DEFAULT_MIN_HISTORY


@dataclass(frozen=True, slots=True)
class Alert:
    """One warning. ``code`` is stable and machine-readable; ``message`` is for people."""

    code: str
    message: str
    row: int | None = None


def check_overspending(summary: Summary) -> list[Alert]:
    """Warn when expenses are larger than net income."""
    if summary.total_expenses <= summary.net_income:
        return []
    gap = summary.total_expenses - summary.net_income
    return [
        Alert(
            "overspending",
            f"You spent {format_money(gap)} more than you earned "
            f"(expenses {format_money(summary.total_expenses)} vs "
            f"net income {format_money(summary.net_income)}).",
        )
    ]


def check_category_share(summary: Summary, limit_pct: Decimal) -> list[Alert]:
    """Warn for each category that uses more than ``limit_pct`` of net income.

    Skipped when there is no income: the overspending rule already covers that.
    """
    alerts = []
    for category, amount in summary.expenses_by_category.items():
        share = percent(amount, summary.net_income)
        if share is not None and share > limit_pct:
            alerts.append(
                Alert(
                    "category_over_limit",
                    f"'{category}' spending of {format_money(amount)} is {share}% of "
                    f"net income (limit {limit_pct}%).",
                )
            )
    return alerts


def check_large_expenses(
    period_entries: Sequence[Entry],
    history: Sequence[Entry],
    multiplier: Decimal,
    min_history: int = DEFAULT_MIN_HISTORY,
) -> list[Alert]:
    """Flag one-off expenses far above what you normally spend in that category.

    Each expense in the period is compared with the average of every *other*
    expense in the same category across the whole file (``history``). Rent is
    then compared with other rent payments, not with a cup of coffee.
    """
    totals: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
    counts: defaultdict[str, int] = defaultdict(int)
    for entry in history:
        if not entry.is_income:
            totals[entry.category] += entry.amount
            counts[entry.category] += 1

    alerts = []
    for entry in period_entries:
        if entry.is_income:
            continue
        others = counts[entry.category] - 1
        if others < min_history:
            continue
        average = (totals[entry.category] - entry.amount) / others
        if average > 0 and entry.amount > average * multiplier:
            times = (entry.amount / average).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
            alerts.append(
                Alert(
                    "large_expense",
                    f"Row {entry.row}: {format_money(entry.amount)} on {entry.category} "
                    f"('{entry.description}') is {times}x your usual {entry.category} "
                    f"expense (average {format_money(average)}).",
                    row=entry.row,
                )
            )
    return alerts


def check_deductions(period_entries: Sequence[Entry]) -> list[Alert]:
    """Warn when gross pay minus deductions does not equal the net pay recorded."""
    alerts = []
    for entry in period_entries:
        if not entry.is_income or entry.gross is None:
            continue
        expected_net = entry.gross - entry.deductions
        if expected_net != entry.amount:
            alerts.append(
                Alert(
                    "deduction_mismatch",
                    f"Row {entry.row}: gross {format_money(entry.gross)} minus deductions "
                    f"{format_money(entry.deductions)} is {format_money(expected_net)}, but "
                    f"net pay is recorded as {format_money(entry.amount)} "
                    f"(off by {format_money(abs(expected_net - entry.amount))}).",
                    row=entry.row,
                )
            )
    return alerts


def evaluate(
    summary: Summary, all_entries: Sequence[Entry], config: RuleConfig | None = None
) -> list[Alert]:
    """Run every rule for the summary's period and return all alerts in a fixed order."""
    config = config or RuleConfig()
    period_entries = filter_entries(all_entries, summary.period)
    return [
        *check_overspending(summary),
        *check_category_share(summary, config.category_limit_pct),
        *check_large_expenses(
            period_entries, all_entries, config.large_expense_multiplier, config.min_history
        ),
        *check_deductions(period_entries),
    ]
