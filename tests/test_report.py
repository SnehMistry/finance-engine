import csv
import io
import json
from decimal import Decimal

from conftest import make_entry, paycheck

from finance_engine.calculator import Period, summarize
from finance_engine.models import RowError
from finance_engine.report import render_table, render_text, to_csv, to_dict, to_json
from finance_engine.rules import Alert

ENTRIES = [
    paycheck(row=2),
    make_entry(row=3, category="housing", amount="1500.00"),
    make_entry(row=4, category="groceries", amount="100.00"),
]
ALERTS = [Alert("large_expense", "Row 3: big one", row=3)]
ERRORS = [RowError(9, "amount 'x' is not a number")]


def test_render_table_alignment_and_rules():
    table = render_table(["Name", "Amount"], [["a", "$1.00"], None, ["total", "$10.00"]])
    assert table.splitlines() == [
        "+-------+--------+",
        "| Name  | Amount |",
        "+-------+--------+",
        "| a     |  $1.00 |",
        "+-------+--------+",
        "| total | $10.00 |",
        "+-------+--------+",
    ]


def test_render_text_contains_all_sections():
    text = render_text(summarize(ENTRIES, Period.for_month(2026, 9)), ALERTS)
    assert text.startswith("Finance Engine report: September 2026\n")
    assert "Entries: 3 (income: 1, expense: 2)" in text
    assert "| Gross income     | $3,000.00 |" in text
    assert "|   Tax            |  -$600.00 |" in text
    assert "| Net income       | $2,100.00 |" in text
    assert "| housing              | $1,500.00 |  93.8% |" in text
    assert "| Savings        |    $500.00 |" in text
    assert "| Savings rate   |      23.8% |" in text
    assert "Warnings (1):\n  ! Row 3: big one" in text


def test_render_text_without_warnings():
    assert render_text(summarize(ENTRIES), []).endswith("No warnings.")


def test_render_text_with_income_but_no_expenses():
    text = render_text(summarize([paycheck()]), [])
    assert "| (none)               |  $0.00 |   n/a |" in text
    assert "| Total expenses       |  $0.00 |   n/a |" in text


def test_render_text_for_empty_period():
    text = render_text(summarize(ENTRIES, Period.for_month(2026, 1)), [])
    assert text.endswith("No entries found in this period.")


def test_to_dict_uses_exact_decimal_strings():
    data = to_dict(summarize(ENTRIES, Period.for_month(2026, 9)), ALERTS, ERRORS)
    assert data["period"] == {"label": "September 2026", "start": "2026-09-01", "end": "2026-09-30"}
    assert data["counts"] == {"entries": 3, "income": 1, "expense": 2}
    assert data["income"]["net"] == "2100.00"
    assert data["income"]["total_deductions"] == "900.00"
    assert data["expenses"]["by_category"] == {"housing": "1500.00", "groceries": "100.00"}
    assert data["savings"] == "500.00"
    assert data["savings_rate_percent"] == "23.8"
    assert data["warnings"] == [{"code": "large_expense", "message": "Row 3: big one", "row": 3}]
    assert data["skipped_rows"] == [{"row": 9, "error": "amount 'x' is not a number"}]
    assert Decimal(data["savings"]) == Decimal("500.00")


def test_to_dict_without_income_or_period():
    data = to_dict(summarize([]), [])
    assert data["period"]["start"] is None
    assert data["savings_rate_percent"] is None


def test_to_json_round_trips():
    data = json.loads(to_json(summarize(ENTRIES), ALERTS, ERRORS))
    assert data["income"]["gross"] == "3000.00"


def test_to_csv_layout():
    text = to_csv(summarize(ENTRIES, Period.for_month(2026, 9)), ALERTS, ERRORS)
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == ["section", "name", "value"]
    assert ["income", "net", "2100.00"] in rows
    assert ["expenses", "housing", "1500.00"] in rows
    assert ["expenses", "total", "1600.00"] in rows
    assert ["summary", "savings_rate_percent", "23.8"] in rows
    assert ["warning", "large_expense", "Row 3: big one"] in rows
    assert ["skipped_row", "9", "amount 'x' is not a number"] in rows


def test_to_csv_blank_values_for_missing_data():
    rows = list(csv.reader(io.StringIO(to_csv(summarize([]), []))))
    assert ["period", "start", ""] in rows
    assert ["summary", "savings_rate_percent", ""] in rows
