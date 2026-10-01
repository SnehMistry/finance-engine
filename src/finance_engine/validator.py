"""Turn raw CSV rows into validated :class:`~finance_engine.models.Entry` objects.

Every data check lives here. A row that fails any check is *skipped*, and one
:class:`~finance_engine.models.RowError` is recorded per problem so a user can
fix everything wrong with a row in one pass. Nothing in this module raises on
bad data, which is what keeps the program from crashing on messy input.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable, Iterable
from decimal import Decimal
from typing import TypeVar

from finance_engine.models import (
    CATEGORIES_BY_TYPE,
    Entry,
    EntryType,
    ParseResult,
    RawRow,
    RowError,
)
from finance_engine.money import CENT, ZERO

DATE_FORMAT = "%Y-%m-%d"
MAX_AMOUNT = Decimal("1000000000")
DEDUCTION_FIELDS: tuple[str, ...] = ("tax", "benefits", "retirement")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")

T = TypeVar("T")


class FieldError(ValueError):
    """One field failed validation. The message is shown to the user as-is."""


def parse_date(raw: str) -> dt.date:
    """Parse a ``YYYY-MM-DD`` date, rejecting impossible dates like 2026-02-30."""
    if not raw:
        raise FieldError("date is missing")
    try:
        return dt.datetime.strptime(raw, DATE_FORMAT).date()
    except ValueError:
        raise FieldError(f"date '{raw}' is not a valid YYYY-MM-DD date") from None


def parse_money(raw: str, field: str, *, allow_zero: bool = False) -> Decimal:
    """Parse a money amount into a ``Decimal`` with exactly two decimal places.

    Accepts plain numbers with an optional leading ``$`` (``1250``, ``$1250.5``).
    Rejects text, negatives, scientific notation, ``NaN``/``Infinity``, more than
    two decimal places, and absurdly large values.
    """
    if not raw:
        raise FieldError(f"{field} is missing")
    negative = raw.startswith("-")
    digits = raw.removeprefix("-").removeprefix("$")
    # A strict regex instead of trusting Decimal(): Decimal happily accepts
    # "NaN", "Infinity", "1e5" and "1_000", none of which belong in a budget.
    if not _NUMBER.fullmatch(digits):
        raise FieldError(f"{field} '{raw}' is not a number")
    if negative:
        raise FieldError(f"{field} cannot be negative (got {raw})")
    value = Decimal(digits)
    if value > MAX_AMOUNT:
        raise FieldError(f"{field} {raw} is larger than the {MAX_AMOUNT:,} limit")
    if value != value.quantize(CENT):
        raise FieldError(f"{field} '{raw}' has more than 2 decimal places")
    if value == 0 and not allow_zero:
        raise FieldError(f"{field} must be greater than zero")
    return value.quantize(CENT)


def parse_type(raw: str) -> EntryType:
    """Parse ``income`` or ``expense`` (case-insensitive)."""
    if not raw:
        raise FieldError("type is missing")
    try:
        return EntryType(raw.lower())
    except ValueError:
        raise FieldError(f"type '{raw}' must be 'income' or 'expense'") from None


def parse_category(raw: str, entry_type: EntryType | None) -> str:
    """Parse a category and check it is allowed for ``entry_type``.

    If the type itself was invalid, only presence is checked, because we cannot
    know which list of categories applies.
    """
    if not raw:
        raise FieldError("category is missing")
    category = raw.lower()
    if entry_type is None:
        return category
    allowed = CATEGORIES_BY_TYPE[entry_type]
    if category not in allowed:
        raise FieldError(
            f"unknown {entry_type} category '{raw}' (allowed: {', '.join(sorted(allowed))})"
        )
    return category


def validate_row(raw: RawRow) -> tuple[Entry | None, list[str]]:
    """Validate one row.

    Returns:
        ``(entry, [])`` when the row is valid, or ``(None, problems)`` listing
        every problem found.
    """
    problems: list[str] = []
    cells = raw.fields

    if raw.extra_values:
        problems.append(f"row has {raw.extra_values} more value(s) than the header has columns")

    date = _attempt(problems, parse_date, cells.get("date", ""))
    entry_type = _attempt(problems, parse_type, cells.get("type", ""))
    category = _attempt(problems, parse_category, cells.get("category", ""), entry_type)
    description = cells.get("description", "")
    if not description:
        problems.append("description is missing")
    amount = _attempt(problems, parse_money, cells.get("amount", ""), "amount")

    gross: Decimal | None = None
    deductions = {name: ZERO for name in DEDUCTION_FIELDS}
    provided = [name for name in ("gross", *DEDUCTION_FIELDS) if cells.get(name)]
    if entry_type is EntryType.EXPENSE and provided:
        problems.append(f"income-only field(s) set on an expense row: {', '.join(provided)}")
    elif provided:
        if cells.get("gross"):
            gross = _attempt(problems, parse_money, cells["gross"], "gross")
        for name in DEDUCTION_FIELDS:
            if cells.get(name):
                deductions[name] = (
                    _attempt(problems, parse_money, cells[name], name, allow_zero=True) or ZERO
                )

    if problems:
        return None, problems
    entry = Entry(
        row=raw.row,
        date=date,  # type: ignore[arg-type]  # all None cases were reported above
        type=entry_type,  # type: ignore[arg-type]
        category=category,  # type: ignore[arg-type]
        description=description,
        amount=amount,  # type: ignore[arg-type]
        gross=gross,
        **deductions,
    )
    return entry, []


def validate_rows(rows: Iterable[RawRow]) -> ParseResult:
    """Validate every row, skipping invalid ones and flagging duplicates.

    A row is a duplicate when it matches an earlier *valid* row on every value
    (see :meth:`Entry.identity`). The first copy is kept; later copies are skipped.
    """
    result = ParseResult()
    first_seen: dict[tuple[object, ...], int] = {}
    for raw in rows:
        result.rows_read += 1
        entry, problems = validate_row(raw)
        if entry is not None:
            original = first_seen.setdefault(entry.identity(), raw.row)
            if original != raw.row:
                entry, problems = None, [f"duplicate of row {original}"]
        if entry is None:
            result.errors.extend(RowError(raw.row, problem) for problem in problems)
        else:
            result.entries.append(entry)
    return result


def _attempt(problems: list[str], parse: Callable[..., T], *args: object, **kwargs: object) -> T | None:
    """Call ``parse``; on :class:`FieldError` record the message and return ``None``."""
    try:
        return parse(*args, **kwargs)
    except FieldError as exc:
        problems.append(str(exc))
        return None
