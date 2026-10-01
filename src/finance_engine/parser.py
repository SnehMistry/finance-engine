"""Read a CSV file into :class:`~finance_engine.models.RawRow` objects.

This module only deals with the *file*: opening it, decoding it, and checking
the header. It does not judge the values inside each cell; that is the job of
:mod:`finance_engine.validator`.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import TextIO

from finance_engine.models import ParseResult, RawRow
from finance_engine.validator import validate_rows

REQUIRED_COLUMNS: tuple[str, ...] = ("date", "type", "category", "description", "amount")
OPTIONAL_COLUMNS: tuple[str, ...] = ("gross", "tax", "benefits", "retirement")
_EXTRA_KEY = "__extra__"


class FileFormatError(Exception):
    """The file as a whole cannot be used (missing, unreadable, or wrong header).

    Problems with individual rows never raise; they become ``RowError`` objects.
    """


def read_rows(path: str | Path) -> list[RawRow]:
    """Read every data row from the CSV at ``path``.

    Raises:
        FileFormatError: If the file is missing, unreadable, not UTF-8, or its
            header lacks a required column.
    """
    path = Path(path)
    try:
        # utf-8-sig silently drops the byte-order mark Excel adds to CSV exports.
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return _read(handle)
    except FileNotFoundError:
        raise FileFormatError(f"file not found: {path}") from None
    except UnicodeDecodeError:
        raise FileFormatError(f"{path} is not a UTF-8 text file") from None
    except OSError as exc:
        raise FileFormatError(f"cannot read {path}: {exc.strerror}") from None


def parse_file(path: str | Path) -> ParseResult:
    """Read and validate the CSV at ``path`` in one step."""
    return validate_rows(read_rows(path))


def _read(handle: TextIO) -> list[RawRow]:
    reader = csv.DictReader(handle, restkey=_EXTRA_KEY)
    if not reader.fieldnames:
        return []  # empty file, or only blank lines
    header = [name.strip().lower() for name in reader.fieldnames]
    _check_header(header)
    reader.fieldnames = header

    rows: list[RawRow] = []
    try:
        for record in reader:
            extra = record.pop(_EXTRA_KEY, [])
            fields = {name: (value or "").strip() for name, value in record.items()}
            rows.append(
                RawRow(
                    row=reader.line_num,
                    fields=fields,
                    extra_values=sum(1 for value in extra if value.strip()),
                )
            )
    except csv.Error as exc:
        raise FileFormatError(f"line {reader.line_num}: {exc}") from None
    return rows


def _check_header(header: list[str]) -> None:
    named = [name for name in header if name]
    duplicates = sorted({name for name in named if named.count(name) > 1})
    if duplicates:
        raise FileFormatError(f"duplicate column(s) in header: {', '.join(duplicates)}")
    missing = [name for name in REQUIRED_COLUMNS if name not in header]
    if missing:
        expected = ",".join(REQUIRED_COLUMNS + OPTIONAL_COLUMNS)
        raise FileFormatError(
            f"missing required column(s): {', '.join(missing)}. Expected header: {expected}"
        )
