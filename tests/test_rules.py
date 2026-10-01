from decimal import Decimal

from conftest import make_entry, paycheck

from finance_engine.calculator import Period, summarize
from finance_engine.rules import (
    RuleConfig,
    check_category_share,
    check_deductions,
    check_large_expenses,
    check_overspending,
    evaluate,
)


def income(amount: str) -> list:
    return [make_entry(row=99, type="income", category="salary", amount=amount)]


# --- overspending ------------------------------------------------------------------


def test_overspending_warns():
    alerts = check_overspending(summarize(income("1000.00") + [make_entry(amount="1200.50")]))
    assert len(alerts) == 1
    assert alerts[0].code == "overspending"
    assert "$200.50 more than you earned" in alerts[0].message


def test_no_overspending_when_exactly_break_even():
    assert check_overspending(summarize(income("1000.00") + [make_entry(amount="1000.00")])) == []


def test_overspending_with_no_income():
    assert len(check_overspending(summarize([make_entry(amount="5.00")]))) == 1


# --- category share ------------------------------------------------------------


def test_category_over_limit():
    summary = summarize(income("1000.00") + [make_entry(category="housing", amount="350.00")])
    alerts = check_category_share(summary, Decimal("30"))
    assert [a.code for a in alerts] == ["category_over_limit"]
    assert "'housing' spending of $350.00 is 35.0% of net income (limit 30%)" in alerts[0].message


def test_category_exactly_at_limit_is_fine():
    summary = summarize(income("1000.00") + [make_entry(category="housing", amount="300.00")])
    assert check_category_share(summary, Decimal("30")) == []


def test_category_share_skipped_without_income():
    summary = summarize([make_entry(category="housing", amount="300.00")])
    assert check_category_share(summary, Decimal("30")) == []


# --- large expenses ------------------------------------------------------------


def shopping(row: int, amount: str, date: str = "2026-08-10") -> object:
    return make_entry(row=row, date=date, category="shopping", description=f"Item {row}", amount=amount)


def test_large_expense_flagged_against_category_history():
    history = [shopping(2, "40.00"), shopping(3, "60.00"), shopping(4, "1299.00", date="2026-09-12")]
    alerts = check_large_expenses([history[2]], history, Decimal("3"))
    assert len(alerts) == 1
    assert alerts[0].row == 4
    assert "26.0x your usual shopping expense (average $50.00)" in alerts[0].message


def test_large_expense_not_flagged_below_multiplier():
    history = [shopping(2, "40.00"), shopping(3, "60.00"), shopping(4, "150.00")]
    assert check_large_expenses(history, history, Decimal("3")) == []


def test_large_expense_needs_enough_history():
    history = [shopping(2, "40.00"), shopping(3, "1299.00")]
    assert check_large_expenses(history, history, Decimal("3"), min_history=2) == []
    assert len(check_large_expenses(history, history, Decimal("3"), min_history=1)) == 1


def test_recurring_rent_is_not_a_large_expense():
    rent = [make_entry(row=i, date=f"2026-0{i}-01", category="housing", amount="1650.00") for i in (7, 8, 9)]
    groceries = [make_entry(row=20 + i, description=str(i), amount="50.00") for i in range(5)]
    assert check_large_expenses(rent, rent + groceries, Decimal("3")) == []


def test_large_expense_ignores_income():
    entries = [paycheck(row=2), paycheck(row=3, date="2026-09-01"), paycheck(row=4, date="2026-09-29", amount="99999")]
    assert check_large_expenses(entries, entries, Decimal("3")) == []


# --- deductions ------------------------------------------------------------------


def test_deductions_that_add_up_are_fine():
    assert check_deductions([paycheck()]) == []


def test_deduction_mismatch():
    alerts = check_deductions([paycheck(row=7, amount="2150.00")])
    assert [a.code for a in alerts] == ["deduction_mismatch"]
    assert alerts[0].row == 7
    assert "is $2,100.00, but net pay is recorded as $2,150.00 (off by $50.00)" in alerts[0].message


def test_deduction_check_skips_rows_without_gross_and_expenses():
    no_gross = make_entry(type="income", category="salary", amount="500.00", tax="100.00")
    assert check_deductions([no_gross, make_entry()]) == []


# --- evaluate ------------------------------------------------------------------


def test_evaluate_runs_every_rule_for_the_period_only():
    entries = [
        paycheck(row=2, date="2026-09-01", amount="2000.00"),  # mismatch: should be 2100
        make_entry(row=3, date="2026-09-02", category="housing", amount="2500.00"),
        shopping(4, "20.00"),
        shopping(5, "30.00"),
        shopping(6, "900.00", date="2026-09-20"),
        paycheck(row=7, date="2026-08-01", amount="1.00"),  # August mismatch: out of period
    ]
    summary = summarize(entries, Period.for_month(2026, 9))
    codes = [a.code for a in evaluate(summary, entries)]
    assert codes == ["overspending", "category_over_limit", "category_over_limit", "large_expense", "deduction_mismatch"]


def test_evaluate_respects_config():
    entries = income("1000.00") + [make_entry(category="housing", amount="350.00")]
    summary = summarize(entries)
    assert evaluate(summary, entries, RuleConfig(category_limit_pct=Decimal("40"))) == []


def test_evaluate_with_no_entries():
    assert evaluate(summarize([]), []) == []
