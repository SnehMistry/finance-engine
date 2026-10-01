import datetime as dt
from decimal import Decimal

import pytest

from finance_engine.models import EntryType, RawRow
from finance_engine.validator import (
    FieldError,
    parse_category,
    parse_date,
    parse_money,
    parse_type,
    validate_row,
    validate_rows,
)

GOOD = {
    "date": "2026-09-01",
    "type": "expense",
    "category": "groceries",
    "description": "Weekly groceries",
    "amount": "85.20",
}


def raw(row: int = 2, extra_values: int = 0, **fields: str) -> RawRow:
    return RawRow(row=row, fields={**GOOD, **fields}, extra_values=extra_values)


def errors_for(**fields: str) -> list[str]:
    entry, problems = validate_row(raw(**fields))
    assert entry is None
    return problems


# --- valid rows -------------------------------------------------------------


def test_valid_expense_row():
    entry, problems = validate_row(raw())
    assert problems == []
    assert entry.date == dt.date(2026, 9, 1)
    assert entry.type is EntryType.EXPENSE
    assert entry.amount == Decimal("85.20")
    assert entry.gross is None and entry.deductions == 0


def test_valid_income_row_with_deductions():
    entry, problems = validate_row(
        raw(type="Income", category="SALARY", amount="2100", gross="3000", tax="600", benefits="150", retirement="150")
    )
    assert problems == []
    assert entry.category == "salary"
    assert entry.amount == Decimal("2100.00")
    assert entry.gross == Decimal("3000.00")
    assert entry.deductions == Decimal("900.00")


def test_zero_deduction_is_allowed():
    entry, _ = validate_row(raw(type="income", category="salary", gross="100", tax="0", amount="100"))
    assert entry.tax == Decimal("0.00")


# --- dates ------------------------------------------------------------------


@pytest.mark.parametrize("value", ["2026-02-30", "2026-13-01", "09/01/2026", "yesterday", "2026/09/01"])
def test_bad_dates(value):
    with pytest.raises(FieldError, match="not a valid YYYY-MM-DD date"):
        parse_date(value)


def test_missing_date():
    assert errors_for(date="") == ["date is missing"]


def test_leap_day_is_valid():
    assert parse_date("2028-02-29") == dt.date(2028, 2, 29)


# --- amounts ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [("12", "12.00"), ("12.5", "12.50"), ("$12.34", "12.34"), ("1.500", "1.50"), ("0007.10", "7.10")],
)
def test_money_accepts(value, expected):
    assert parse_money(value, "amount") == Decimal(expected)


@pytest.mark.parametrize("value", ["abc", "12,50", "1e3", "NaN", "Infinity", "1_000", "12.", ".5", "$", "--5", "$-5"])
def test_money_rejects_non_numbers(value):
    with pytest.raises(FieldError, match="is not a number"):
        parse_money(value, "amount")


def test_money_rejects_negative():
    with pytest.raises(FieldError, match="cannot be negative"):
        parse_money("-45.00", "amount")


def test_money_rejects_zero_unless_allowed():
    with pytest.raises(FieldError, match="greater than zero"):
        parse_money("0.00", "amount")
    assert parse_money("0", "tax", allow_zero=True) == Decimal("0.00")


def test_money_rejects_fractions_of_a_cent():
    with pytest.raises(FieldError, match="more than 2 decimal places"):
        parse_money("4.255", "amount")


def test_money_rejects_huge_values():
    with pytest.raises(FieldError, match="larger than the 1,000,000,000 limit"):
        parse_money("9" * 40, "amount")


def test_missing_amount():
    assert errors_for(amount="") == ["amount is missing"]


def test_values_are_decimal_not_float():
    entry, _ = validate_row(raw(amount="0.10"))
    assert isinstance(entry.amount, Decimal)


# --- type and category --------------------------------------------------------


def test_bad_type():
    with pytest.raises(FieldError, match="must be 'income' or 'expense'"):
        parse_type("salary")


def test_missing_type():
    assert "type is missing" in errors_for(type="")


def test_unknown_category():
    with pytest.raises(FieldError, match="unknown expense category 'gambling'"):
        parse_category("gambling", EntryType.EXPENSE)


def test_category_must_match_type():
    with pytest.raises(FieldError, match="unknown income category 'groceries'"):
        parse_category("groceries", EntryType.INCOME)


def test_category_only_checked_for_presence_when_type_invalid():
    problems = errors_for(type="transfer", category="anything")
    assert problems == ["type 'transfer' must be 'income' or 'expense'"]


def test_missing_category():
    assert errors_for(category="") == ["category is missing"]


# --- other fields -------------------------------------------------------------


def test_missing_description():
    assert errors_for(description="") == ["description is missing"]


def test_deductions_not_allowed_on_expense_rows():
    assert errors_for(gross="70.00", tax="5") == ["income-only field(s) set on an expense row: gross, tax"]


def test_bad_deduction_values_on_income_row():
    problems = errors_for(type="income", category="salary", gross="abc", tax="-1")
    assert problems == ["gross 'abc' is not a number", "tax cannot be negative (got -1)"]


def test_extra_values_are_reported():
    assert errors_for(extra_values=2) == ["row has 2 more value(s) than the header has columns"]


def test_every_problem_in_a_row_is_reported():
    problems = errors_for(date="bad", amount="-3", description="")
    assert len(problems) == 3


def test_missing_columns_in_short_row():
    entry, problems = validate_row(RawRow(row=5, fields={"date": "2026-09-01"}))
    assert entry is None
    assert set(problems) == {"type is missing", "category is missing", "description is missing", "amount is missing"}


# --- whole-file validation ------------------------------------------------------


def test_validate_rows_skips_bad_rows_and_keeps_good_ones():
    result = validate_rows([raw(row=2), raw(row=3, amount="oops"), raw(row=4, description="Other food")])
    assert [entry.row for entry in result.entries] == [2, 4]
    assert [str(error) for error in result.errors] == ["Row 3: amount 'oops' is not a number"]
    assert result.rows_read == 3
    assert result.invalid_rows == 1


def test_duplicates_are_skipped_with_reference_to_first_row():
    result = validate_rows([raw(row=2), raw(row=3, description="WEEKLY GROCERIES"), raw(row=4)])
    assert [entry.row for entry in result.entries] == [2]
    assert [str(e) for e in result.errors] == ["Row 3: duplicate of row 2", "Row 4: duplicate of row 2"]


def test_same_description_different_amount_is_not_duplicate():
    result = validate_rows([raw(row=2), raw(row=3, amount="85.21")])
    assert len(result.entries) == 2


def test_invalid_row_does_not_count_as_first_copy():
    result = validate_rows([raw(row=2, category="nope"), raw(row=3, category="nope"), raw(row=4)])
    assert [entry.row for entry in result.entries] == [4]
    assert all("duplicate" not in error.message for error in result.errors)


def test_all_rows_invalid():
    result = validate_rows([raw(row=2, amount="x"), raw(row=3, date="x")])
    assert result.entries == []
    assert result.invalid_rows == 2


def test_invalid_rows_counts_distinct_rows():
    result = validate_rows([raw(row=2, amount="x", date="x")])
    assert len(result.errors) == 2
    assert result.invalid_rows == 1
