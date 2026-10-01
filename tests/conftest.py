"""Shared test helpers."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest

from finance_engine.models import Entry, EntryType

HEADER = "date,type,category,description,amount,gross,tax,benefits,retirement"
SAMPLE_DATA = Path(__file__).resolve().parent.parent / "sample_data"


@pytest.fixture
def write_csv(tmp_path: Path) -> Callable[..., Path]:
    """Write CSV lines to a temp file. The standard header is added unless ``header=None``."""

    def _write(*lines: str, header: str | None = HEADER, name: str = "data.csv") -> Path:
        path = tmp_path / name
        body = ([header] if header is not None else []) + list(lines)
        path.write_text("\n".join(body) + ("\n" if body else ""), encoding="utf-8")
        return path

    return _write


def make_entry(
    *,
    row: int = 2,
    date: str = "2026-09-15",
    type: str = "expense",
    category: str = "groceries",
    description: str = "Food",
    amount: str = "10.00",
    gross: str | None = None,
    tax: str = "0.00",
    benefits: str = "0.00",
    retirement: str = "0.00",
) -> Entry:
    """Build an Entry from simple strings so tests stay short and readable."""
    return Entry(
        row=row,
        date=dt.date.fromisoformat(date),
        type=EntryType(type),
        category=category,
        description=description,
        amount=Decimal(amount),
        gross=None if gross is None else Decimal(gross),
        tax=Decimal(tax),
        benefits=Decimal(benefits),
        retirement=Decimal(retirement),
    )


def paycheck(row: int = 2, date: str = "2026-09-15", **overrides: str) -> Entry:
    """A paycheck whose deductions add up exactly: 3000 - (600 + 150 + 150) = 2100."""
    values = {
        "amount": "2100.00",
        "gross": "3000.00",
        "tax": "600.00",
        "benefits": "150.00",
        "retirement": "150.00",
        "category": "salary",
        "description": "Paycheck",
    }
    values.update(overrides)
    return make_entry(row=row, date=date, type="income", **values)
