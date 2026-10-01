"""Data types shared by every stage of the pipeline.

The flow through the program is::

    CSV file -> RawRow (parser) -> Entry or RowError (validator)
             -> Summary (calculator) -> Alert (rules) -> text/CSV/JSON (report)
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from finance_engine.money import ZERO


class EntryType(StrEnum):
    """Whether money came in or went out."""

    INCOME = "income"
    EXPENSE = "expense"


INCOME_CATEGORIES: frozenset[str] = frozenset(
    {"salary", "freelance", "bonus", "interest", "refund", "other_income"}
)
EXPENSE_CATEGORIES: frozenset[str] = frozenset(
    {
        "housing",
        "utilities",
        "groceries",
        "dining",
        "transport",
        "health",
        "insurance",
        "entertainment",
        "shopping",
        "subscriptions",
        "education",
        "travel",
        "other",
    }
)
CATEGORIES_BY_TYPE: dict[EntryType, frozenset[str]] = {
    EntryType.INCOME: INCOME_CATEGORIES,
    EntryType.EXPENSE: EXPENSE_CATEGORIES,
}


@dataclass(frozen=True, slots=True)
class RawRow:
    """One data row exactly as it appeared in the CSV, before any validation.

    Attributes:
        row: Line number in the file (the header is line 1).
        fields: Column name -> cell text, already stripped of whitespace.
        extra_values: How many non-empty cells appeared beyond the header's columns.
    """

    row: int
    fields: dict[str, str]
    extra_values: int = 0


@dataclass(frozen=True, slots=True)
class Entry:
    """One validated income or expense entry.

    For income rows ``amount`` is the *net* pay that actually reached the bank
    account. ``gross`` and the three deduction fields are optional and only
    allowed on income rows.
    """

    row: int
    date: dt.date
    type: EntryType
    category: str
    description: str
    amount: Decimal
    gross: Decimal | None = None
    tax: Decimal = ZERO
    benefits: Decimal = ZERO
    retirement: Decimal = ZERO

    @property
    def is_income(self) -> bool:
        """True for income rows, False for expense rows."""
        return self.type is EntryType.INCOME

    @property
    def deductions(self) -> Decimal:
        """Tax + benefits + retirement taken out of this paycheck."""
        return self.tax + self.benefits + self.retirement

    @property
    def gross_amount(self) -> Decimal:
        """Gross pay: the recorded ``gross``, or net + deductions if it was left blank."""
        return self.gross if self.gross is not None else self.amount + self.deductions

    def identity(self) -> tuple[object, ...]:
        """The values that make two entries count as duplicates.

        The row number is deliberately left out, and the description is compared
        case-insensitively, so the same transaction pasted twice is caught.
        """
        return (
            self.date,
            self.type,
            self.category,
            self.description.casefold(),
            self.amount,
            self.gross,
            self.tax,
            self.benefits,
            self.retirement,
        )


@dataclass(frozen=True, slots=True)
class RowError:
    """A problem that caused a row to be skipped."""

    row: int
    message: str

    def __str__(self) -> str:
        return f"Row {self.row}: {self.message}"


@dataclass(slots=True)
class ParseResult:
    """Everything learned from one CSV file: the good entries and the bad rows."""

    entries: list[Entry] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    rows_read: int = 0

    @property
    def invalid_rows(self) -> int:
        """Number of distinct rows that were skipped (a row can have several errors)."""
        return len({error.row for error in self.errors})
