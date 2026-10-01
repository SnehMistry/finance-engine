"""Present a summary as a terminal table, a JSON document, or a CSV file."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from finance_engine.calculator import Summary
from finance_engine.models import RowError
from finance_engine.money import format_money, format_percent, percent
from finance_engine.rules import Alert

# A row of None inside a table draws a horizontal rule (used above totals).
TableRow = Sequence[str] | None


def render_table(headers: Sequence[str], rows: Sequence[TableRow]) -> str:
    """Draw a simple ASCII table. The first column is left-aligned, the rest right-aligned."""
    real_rows = [row for row in rows if row is not None]
    widths = [max(len(cell) for cell in column) for column in zip(headers, *real_rows)]
    rule = "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    def line(cells: Sequence[str]) -> str:
        parts = [
            f" {cell:<{width}} " if index == 0 else f" {cell:>{width}} "
            for index, (cell, width) in enumerate(zip(cells, widths))
        ]
        return "|" + "|".join(parts) + "|"

    out = [rule, line(headers), rule]
    out.extend(rule if row is None else line(row) for row in rows)
    out.append(rule)
    return "\n".join(out)


def render_text(summary: Summary, alerts: Sequence[Alert]) -> str:
    """Build the human-readable report printed by ``finance-engine summary``."""
    title = f"Finance Engine report: {summary.period.label}"
    lines = [title, "=" * len(title)]
    if summary.entry_count == 0:
        lines.append("No entries found in this period.")
        return "\n".join(lines)

    lines.append(
        f"{summary.entry_count} entries ({summary.income_count} income, "
        f"{summary.expense_count} expense)"
    )
    lines.append("")
    lines.append(
        render_table(
            ["Income", "Amount"],
            [
                ["Gross income", format_money(summary.gross_income)],
                ["  Tax", format_money(-summary.tax)],
                ["  Benefits", format_money(-summary.benefits)],
                ["  Retirement", format_money(-summary.retirement)],
                ["Total deductions", format_money(-summary.total_deductions)],
                None,
                ["Net income", format_money(summary.net_income)],
            ],
        )
    )
    lines.append("")
    expense_rows: list[TableRow] = [
        [category, format_money(amount), format_percent(percent(amount, summary.total_expenses))]
        for category, amount in summary.expenses_by_category.items()
    ]
    if not expense_rows:
        expense_rows.append(["(none)", format_money(summary.total_expenses), "n/a"])
    expense_rows += [
        None,
        [
            "Total expenses",
            format_money(summary.total_expenses),
            "100.0%" if summary.total_expenses else "n/a",
        ],
    ]
    lines.append(render_table(["Expenses by category", "Amount", "Share"], expense_rows))
    lines.append("")
    lines.append(
        render_table(
            ["Bottom line", "Amount"],
            [
                ["Net income", format_money(summary.net_income)],
                ["Total expenses", format_money(-summary.total_expenses)],
                None,
                ["Savings", format_money(summary.savings)],
                ["Savings rate", format_percent(summary.savings_rate)],
            ],
        )
    )
    lines.append("")
    if alerts:
        lines.append(f"Warnings ({len(alerts)}):")
        lines.extend(f"  ! {alert.message}" for alert in alerts)
    else:
        lines.append("No warnings.")
    return "\n".join(lines)


def to_dict(
    summary: Summary, alerts: Sequence[Alert], errors: Sequence[RowError] = ()
) -> dict[str, Any]:
    """Convert a report to plain data.

    Money is written as strings like ``"1234.50"`` rather than JSON numbers,
    because JSON numbers are usually read back as binary floats and would lose
    the exactness ``Decimal`` gives us.
    """
    period = summary.period
    return {
        "period": {
            "label": period.label,
            "start": period.start.isoformat() if period.start else None,
            "end": period.end.isoformat() if period.end else None,
        },
        "counts": {
            "entries": summary.entry_count,
            "income": summary.income_count,
            "expense": summary.expense_count,
        },
        "income": {
            "gross": _money(summary.gross_income),
            "tax": _money(summary.tax),
            "benefits": _money(summary.benefits),
            "retirement": _money(summary.retirement),
            "total_deductions": _money(summary.total_deductions),
            "net": _money(summary.net_income),
        },
        "expenses": {
            "total": _money(summary.total_expenses),
            "by_category": {
                category: _money(amount)
                for category, amount in summary.expenses_by_category.items()
            },
        },
        "savings": _money(summary.savings),
        "savings_rate_percent": None if summary.savings_rate is None else str(summary.savings_rate),
        "warnings": [{"code": a.code, "message": a.message, "row": a.row} for a in alerts],
        "skipped_rows": [{"row": e.row, "error": e.message} for e in errors],
    }


def to_json(summary: Summary, alerts: Sequence[Alert], errors: Sequence[RowError] = ()) -> str:
    """Render the report as pretty-printed JSON."""
    return json.dumps(to_dict(summary, alerts, errors), indent=2) + "\n"


def to_csv(summary: Summary, alerts: Sequence[Alert], errors: Sequence[RowError] = ()) -> str:
    """Render the report as a three-column ``section,name,value`` CSV.

    A long, flat layout opens cleanly in any spreadsheet and is easy to filter.
    """
    data = to_dict(summary, alerts, errors)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["section", "name", "value"])
    for key, value in data["period"].items():
        writer.writerow(["period", key, value or ""])
    for key, value in data["income"].items():
        writer.writerow(["income", key, value])
    for category, value in data["expenses"]["by_category"].items():
        writer.writerow(["expenses", category, value])
    writer.writerow(["expenses", "total", data["expenses"]["total"]])
    writer.writerow(["summary", "savings", data["savings"]])
    writer.writerow(["summary", "savings_rate_percent", data["savings_rate_percent"] or ""])
    for alert in alerts:
        writer.writerow(["warning", alert.code, alert.message])
    for error in errors:
        writer.writerow(["skipped_row", error.row, error.message])
    return buffer.getvalue()


def _money(value: Decimal) -> str:
    return f"{value:.2f}"
