"""Command-line interface: ``finance-engine validate | summary | export``.

Exit codes:
    0  success
    1  ``validate`` found invalid rows
    2  usage error or unreadable file
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from pathlib import Path

from finance_engine import __version__
from finance_engine.calculator import Period, summarize
from finance_engine.models import ParseResult
from finance_engine.parser import FileFormatError, parse_file
from finance_engine.report import render_text, to_csv, to_json
from finance_engine.rules import (
    DEFAULT_CATEGORY_LIMIT_PCT,
    DEFAULT_LARGE_EXPENSE_MULTIPLIER,
    RuleConfig,
    evaluate,
)

_MONTH = re.compile(r"(\d{4})-(\d{2})")


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point for the ``finance-engine`` command. Returns the exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate":
            return _cmd_validate(args)
        period = _period_from_args(parser, args)
        return _cmd_report(args, period)
    except FileFormatError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    """Define the commands and options."""
    parser = argparse.ArgumentParser(
        prog="finance-engine",
        description="Analyze income, paychecks and spending from a CSV file.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    validate = commands.add_parser("validate", help="check a CSV file and list every invalid row")
    validate.add_argument("file", type=Path, help="CSV file to check")

    summary = commands.add_parser("summary", help="print a report for a month or date range")
    _add_report_arguments(summary)

    export = commands.add_parser("export", help="export the report as JSON or CSV")
    _add_report_arguments(export)
    export.add_argument("--format", choices=("json", "csv"), default="json", help="default: json")
    export.add_argument("-o", "--output", type=Path, help="write to this file instead of stdout")
    return parser


def _add_report_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", type=Path, help="CSV file to analyze")
    parser.add_argument("--month", type=_month_arg, metavar="YYYY-MM", help="report on one month")
    parser.add_argument(
        "--from", dest="start", type=_date_arg, metavar="YYYY-MM-DD", help="first day (inclusive)"
    )
    parser.add_argument(
        "--to", dest="end", type=_date_arg, metavar="YYYY-MM-DD", help="last day (inclusive)"
    )
    parser.add_argument(
        "--category-limit",
        type=_positive_decimal,
        default=DEFAULT_CATEGORY_LIMIT_PCT,
        metavar="PCT",
        help="warn when one category exceeds this %% of net income (default: %(default)s)",
    )
    parser.add_argument(
        "--large-multiplier",
        type=_positive_decimal,
        default=DEFAULT_LARGE_EXPENSE_MULTIPLIER,
        metavar="X",
        help="warn when an expense is X times its category average (default: %(default)s)",
    )


def _cmd_validate(args: argparse.Namespace) -> int:
    result = parse_file(args.file)
    for error in result.errors:
        print(error)
    if result.rows_read == 0:
        print(f"{args.file}: no data rows found.")
        return 0
    if not result.errors:
        print(f"All {result.rows_read} rows are valid.")
        return 0
    print(
        f"\nChecked {result.rows_read} rows: {len(result.entries)} valid, "
        f"{result.invalid_rows} invalid (skipped)."
    )
    return 1


def _cmd_report(args: argparse.Namespace, period: Period) -> int:
    result = parse_file(args.file)
    _warn_skipped(result)
    summary = summarize(result.entries, period)
    config = RuleConfig(
        category_limit_pct=args.category_limit,
        large_expense_multiplier=args.large_multiplier,
    )
    alerts = evaluate(summary, result.entries, config)

    if args.command == "summary":
        print(render_text(summary, alerts))
        return 0

    render = to_json if args.format == "json" else to_csv
    text = render(summary, alerts, result.errors)
    if args.output is None:
        sys.stdout.write(text)
        return 0
    try:
        args.output.write_text(text, encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot write {args.output}: {exc.strerror}", file=sys.stderr)
        return 2
    print(f"Wrote {args.format.upper()} report to {args.output}")
    return 0


def _warn_skipped(result: ParseResult) -> None:
    for error in result.errors:
        print(f"warning: skipped row {error.row}: {error.message}", file=sys.stderr)


def _period_from_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> Period:
    if args.month and (args.start or args.end):
        parser.error("--month cannot be combined with --from/--to")
    if args.start and args.end and args.start > args.end:
        parser.error("--from must be on or before --to")
    if args.month:
        year, month = args.month
        return Period.for_month(year, month)
    return Period.between(args.start, args.end)


def _month_arg(value: str) -> tuple[int, int]:
    match = _MONTH.fullmatch(value)
    if not match or not 1 <= int(match.group(2)) <= 12:
        raise argparse.ArgumentTypeError(f"'{value}' is not a month in YYYY-MM format")
    return int(match.group(1)), int(match.group(2))


def _date_arg(value: str) -> dt.date:
    try:
        return dt.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a date in YYYY-MM-DD format") from None


def _positive_decimal(value: str) -> Decimal:
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"'{value}' is not a number") from None
    if not number.is_finite() or number <= 0:
        raise argparse.ArgumentTypeError(f"'{value}' must be a positive number")
    return number
