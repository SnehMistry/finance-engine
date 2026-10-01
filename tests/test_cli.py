import json
import runpy
import sys

import pytest
from conftest import SAMPLE_DATA

from finance_engine import __version__
from finance_engine.cli import main

SAMPLE = str(SAMPLE_DATA / "transactions.csv")
MESSY = str(SAMPLE_DATA / "messy_transactions.csv")


def run(capsys, *argv):
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


# --- validate ---------------------------------------------------------------------


def test_validate_clean_file(capsys):
    code, out, _ = run(capsys, "validate", SAMPLE)
    assert code == 0
    assert out.strip() == "All 60 rows are valid."


def test_validate_messy_file_lists_every_bad_row(capsys):
    code, out, _ = run(capsys, "validate", MESSY)
    assert code == 1
    assert "Row 3: date '2026-09-31' is not a valid YYYY-MM-DD date" in out
    assert "Row 5: amount 'abc' is not a number" in out
    assert "Row 6: amount cannot be negative (got -45.00)" in out
    assert "Row 8: unknown expense category 'gambling'" in out
    assert "Row 11: duplicate of row 10" in out
    assert "Checked 14 rows: 3 valid, 11 invalid (skipped)." in out


def test_validate_empty_file(capsys, write_csv):
    code, out, _ = run(capsys, "validate", str(write_csv(header=None)))
    assert code == 0
    assert "no data rows found" in out


def test_validate_missing_file(capsys):
    code, _, err = run(capsys, "validate", "nope.csv")
    assert code == 2
    assert err.strip() == "error: file not found: nope.csv"


# --- summary ------------------------------------------------------------------------


def test_summary_for_month(capsys):
    code, out, err = run(capsys, "summary", SAMPLE, "--month", "2026-09")
    assert code == 0
    assert err == ""
    assert "Finance Engine report: September 2026" in out
    assert "| Net income       |  $4,982.55 |" in out
    assert "| Savings rate   |      22.9% |" in out
    assert "Warnings (3):" in out
    assert "New laptop" in out


def test_summary_all_dates(capsys):
    code, out, _ = run(capsys, "summary", SAMPLE)
    assert code == 0
    assert "Finance Engine report: All dates" in out


def test_summary_date_range(capsys):
    code, out, _ = run(capsys, "summary", SAMPLE, "--from", "2026-08-01", "--to", "2026-08-31")
    assert code == 0
    assert "Finance Engine report: 2026-08-01 to 2026-08-31" in out
    assert "more than you earned" in out  # the August vacation


def test_summary_month_with_no_data(capsys):
    code, out, _ = run(capsys, "summary", SAMPLE, "--month", "2025-01")
    assert code == 0
    assert "No entries found in this period." in out


def test_summary_skips_invalid_rows_with_messages(capsys):
    code, out, err = run(capsys, "summary", MESSY)
    assert code == 0
    assert "warning: skipped row 5: amount 'abc' is not a number" in err
    assert "Entries: 3 (income: 1, expense: 2)" in out


def test_summary_all_rows_invalid(capsys, write_csv):
    path = write_csv("bad,expense,housing,Rent,1.00", "2026-09-01,expense,housing,Rent,abc")
    code, out, err = run(capsys, "summary", str(path))
    assert code == 0
    assert err.count("warning: skipped row") == 2
    assert "No entries found in this period." in out


def test_summary_custom_thresholds(capsys):
    _, out, _ = run(capsys, "summary", SAMPLE, "--month", "2026-09", "--category-limit", "50", "--large-multiplier", "100")
    assert "Warnings (1):" in out
    assert "deductions" in out


# --- export -------------------------------------------------------------------------


def test_export_json_to_stdout(capsys):
    code, out, _ = run(capsys, "export", SAMPLE, "--month", "2026-09")
    assert code == 0
    data = json.loads(out)
    assert data["income"]["net"] == "4982.55"
    assert {w["code"] for w in data["warnings"]} == {"category_over_limit", "large_expense", "deduction_mismatch"}


def test_export_csv_to_file(capsys, tmp_path):
    target = tmp_path / "report.csv"
    code, out, _ = run(capsys, "export", SAMPLE, "--format", "csv", "-o", str(target), "--month", "2026-09")
    assert code == 0
    assert out.strip() == f"Wrote CSV report to {target}"
    assert "expenses,total,3839.89" in target.read_text()


def test_export_includes_skipped_rows(capsys):
    _, out, _ = run(capsys, "export", MESSY)
    assert len(json.loads(out)["skipped_rows"]) == 11


def test_export_to_unwritable_path(capsys, tmp_path):
    code, _, err = run(capsys, "export", SAMPLE, "-o", str(tmp_path / "missing_dir" / "r.json"))
    assert code == 2
    assert err.startswith("error: cannot write")


def test_export_bad_header(capsys, write_csv):
    code, _, err = run(capsys, "export", str(write_csv(header="when,what")))
    assert code == 2
    assert "missing required column(s)" in err


# --- argument errors -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["summary", SAMPLE, "--month", "2026-13"], "is not a month in YYYY-MM format"),
        (["summary", SAMPLE, "--month", "Sept"], "is not a month in YYYY-MM format"),
        (["summary", SAMPLE, "--from", "2026/09/01"], "is not a date in YYYY-MM-DD format"),
        (["summary", SAMPLE, "--month", "2026-09", "--from", "2026-09-01"], "cannot be combined"),
        (["summary", SAMPLE, "--from", "2026-09-30", "--to", "2026-09-01"], "--from must be on or before --to"),
        (["summary", SAMPLE, "--category-limit", "abc"], "is not a number"),
        (["summary", SAMPLE, "--category-limit", "-5"], "must be a positive number"),
        (["summary", SAMPLE, "--large-multiplier", "inf"], "must be a positive number"),
        (["export", SAMPLE, "--format", "xml"], "invalid choice"),
        ([], "required"),
    ],
)
def test_bad_arguments_exit_with_usage_error(capsys, argv, message):
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 2
    assert message in capsys.readouterr().err


def test_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    assert capsys.readouterr().out.strip() == f"finance-engine {__version__}"


def test_python_dash_m_entry_point(capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["finance_engine", "validate", SAMPLE])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("finance_engine", run_name="__main__")
    assert exc.value.code == 0
