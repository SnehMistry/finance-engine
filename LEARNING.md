# Learning Guide: how Finance Engine works

This guide explains the project in plain language, so you can understand every
part of it and talk about it confidently. Read it alongside the code: each
section matches one file.

## The big picture in one paragraph

You give the program a CSV file (a spreadsheet saved as text). It reads every
line, checks that each value makes sense, throws away bad lines (and tells you
why), adds up the good lines for the month you asked about, runs a few "is
something wrong here?" checks, and prints the result as a table or saves it as
JSON or CSV.

```text
CSV file ─▶ parser ─▶ validator ─▶ calculator ─▶ rules ─▶ report
            RawRow    Entry /       Summary       Alert     table / JSON / CSV
                      RowError
```

Each arrow is a function call, and each name under an arrow is the kind of
object passed along. A pipeline like this is easy to test, because you can
check each stage on its own.

---

## File by file

### `money.py`: handling money correctly

Computers store `float` numbers in binary (base 2). Most decimal fractions,
like 0.1, can't be written exactly in binary, just as 1/3 can't be written
exactly in decimal (0.3333...). So in Python `0.1 + 0.2` gives
`0.30000000000000004`. For money that is unacceptable.

Python's `Decimal` type stores numbers in base 10, so `Decimal("0.1") +
Decimal("0.2")` is exactly `Decimal("0.3")`. This file has small helpers:

- `CENT` is `Decimal("0.01")`, used to round to whole cents.
- `to_cents()` rounds with `ROUND_HALF_UP` (2.345 becomes 2.35), the rounding
  most people expect. Python's default is "banker's rounding" (round half to
  even), which would surprise a user.
- `percent(part, whole)` returns e.g. `Decimal("33.3")`, or `None` when
  `whole` is zero, because dividing by zero has no meaningful answer (there is
  no savings rate if you earned nothing).
- `format_money()` turns `Decimal("-1234.5")` into `"-$1,234.50"`.

**Key idea:** always create a `Decimal` from a *string* (`Decimal("0.1")`),
never from a float (`Decimal(0.1)` copies the float's error).

### `models.py`: the data shapes

This file defines the "nouns" of the program as **dataclasses**. A dataclass
is a class where Python writes `__init__`, `__repr__` and `__eq__` for you
from the field list.

- `EntryType`: an enum with two values, `INCOME` and `EXPENSE`. It is a
  `StrEnum`, so `EntryType("income")` turns the text from the CSV into the enum.
- `INCOME_CATEGORIES` / `EXPENSE_CATEGORIES`: the allowed category names, as
  `frozenset`s (unchangeable sets with fast `in` checks).
- `RawRow`: one CSV line *before* checking. Just text, plus the row number.
- `Entry`: one line *after* checking. Real types: a `date`, an `EntryType`, a
  `Decimal` amount. It has small helper properties:
  - `deductions` = tax + benefits + retirement
  - `gross_amount` = the gross column, or net + deductions if gross was blank
  - `identity()` = the values used to spot duplicates
- `RowError`: "row 5 had this problem."
- `ParseResult`: the outcome of reading a file: good entries plus errors.

`frozen=True` makes objects read-only after creation, which prevents
accidental changes. `slots=True` makes them a little smaller and faster.

### `parser.py`: reading the file

This file only cares about the *file*, not the values in it.

- Opens the file with `encoding="utf-8-sig"`. The `-sig` part quietly removes
  an invisible marker (a "BOM") that Excel adds to CSV exports, which would
  otherwise make the first column name `"﻿date"` instead of `"date"`.
- Uses `csv.DictReader`, which turns each line into a dictionary keyed by the
  header: `{"date": "2026-09-01", "amount": "1650.00", ...}`. This handles
  quoted values with commas inside, like `"Tacos, chips and salsa"`.
- Cleans the header (lowercase, strip spaces) and checks that required
  columns exist and none are repeated.
- Records `reader.line_num` as the row number, so error messages point to
  the real line in the file even if there are blank lines.
- File-level problems (missing file, not text, bad header) raise
  `FileFormatError`. The CLI catches it and prints a clean message instead of
  a Python traceback.

`parse_file()` is a shortcut: read the rows, then validate them.

### `validator.py`: checking every value

This is the heart of the "never crash on bad input" promise.

There is one small function per field: `parse_date`, `parse_type`,
`parse_category`, `parse_money`. Each one either returns a clean value or
raises `FieldError("a readable message")`.

`validate_row()` calls each of them through a helper called `_attempt()`.
`_attempt` catches the `FieldError`, adds its message to a list, and returns
`None`. Because errors are *collected* rather than stopping at the first one, a
row with three problems reports all three.

What `parse_money` checks, in order:
1. Not empty.
2. Matches the pattern `digits` or `digits.digits` (after removing an optional
   `-` and `$`). This regex is stricter than `Decimal()`, which would accept
   `"NaN"`, `"Infinity"` and `"1e5"`.
3. Not negative (gives a clearer message than "not a number").
4. Not over one billion (a sanity limit).
5. At most two decimal places (`4.255` is rejected; `1.500` is fine).
6. Not zero (except deductions, which may legitimately be 0).

`validate_rows()` runs over every row. For valid rows it uses a dictionary
`first_seen` that maps each entry's `identity()` to the row where it first
appeared. If the same identity shows up again, that row is reported as
`duplicate of row N`. Dictionary lookups are fast (O(1) on average), so
duplicate checking is O(n) overall instead of comparing every pair (O(n²)).

### `calculator.py`: adding things up

- `Period` is a date range with a label. `Period.for_month(2026, 9)` uses
  `calendar.monthrange` to find the last day of the month (30 for September,
  29 for February in a leap year). Either end can be `None`, meaning "no limit".
- `filter_entries()` keeps entries inside the period.
- `summarize()` splits entries into income and expenses and sums them. Note
  the `sum(..., ZERO)`: starting from `Decimal("0.00")` instead of the integer
  `0` keeps every result a `Decimal`.
- Expenses are grouped by category using a `defaultdict`, then sorted biggest
  first (ties alphabetically, so the output never changes randomly).
- `Summary` stores the totals. Values that can be *derived* (`savings`,
  `savings_rate`, `total_deductions`) are properties instead of stored fields,
  so they can never get out of sync.

### `rules.py`: the warnings

Each rule is a separate small function that returns a list of `Alert`s. An
empty list means "all good."

| Rule | Fires when |
|------|-----------|
| `check_overspending` | expenses > net income |
| `check_category_share` | one category > `limit`% of net income (default 30%) |
| `check_large_expenses` | an expense > 3x the average of the *other* expenses in the same category |
| `check_deductions` | gross − (tax + benefits + retirement) ≠ net pay |

The large-expense rule is the most interesting one. It first totals every
category across the whole file, then for each expense computes "the average
of the others" as `(category total − this expense) / (count − 1)`. That is
one pass to build totals and one pass to check, so O(n). If a category has
fewer than 2 other expenses, there isn't enough history to judge, so it's skipped.

`RuleConfig` holds the thresholds so the CLI can change them
(`--category-limit`, `--large-multiplier`). `evaluate()` runs all the rules
in a fixed order.

### `report.py`: presenting results

- `render_table()` draws an ASCII table. It finds the widest cell in each
  column, then pads every cell to that width (`f"{cell:>{width}}"` means
  "right-align in `width` characters"). A `None` row draws a divider line.
- `render_text()` builds the full report: income table, expense table,
  bottom line, warnings.
- `to_dict()` converts everything to plain dictionaries and strings, which
  `to_json()` and `to_csv()` then write out. Money becomes strings like
  `"1650.00"` so no precision is lost.

### `cli.py`: the command line

Uses `argparse` with **subcommands** (like `git commit` / `git push`):
`validate`, `summary`, `export`.

- Custom `type=` functions (`_month_arg`, `_date_arg`, `_positive_decimal`)
  check arguments as they are parsed. If they raise
  `argparse.ArgumentTypeError`, argparse prints a usage message and exits
  with code 2.
- `main()` returns an integer exit code instead of calling `sys.exit()`
  itself. That makes it easy to test: tests just call `main([...])` and
  check the number returned.
- Skipped-row warnings go to **stderr** and the report goes to **stdout**.
  So `finance-engine export data.csv > report.json` produces a clean JSON
  file while warnings still appear on screen.

### `__main__.py`

Lets you run `python -m finance_engine ...`. It just calls `main()`.

### `pyproject.toml`

The modern standard file describing a Python package: its name, version, the
Python versions it supports, optional `dev` dependencies, and
`[project.scripts]`, which creates the `finance-engine` terminal command that
points at `finance_engine.cli:main`. `pip install -e .` installs it in
"editable" mode, so code changes take effect without reinstalling.

### `tests/`

One test file per module. A few techniques worth knowing:

- **Fixtures** (`conftest.py`): `write_csv` creates a temporary CSV file using
  pytest's built-in `tmp_path`, so tests never touch real files.
- **Factory helpers**: `make_entry()` and `paycheck()` build test objects in
  one line, with sensible defaults you can override.
- **Parametrize**: `@pytest.mark.parametrize` runs one test with many inputs,
  e.g. every kind of bad date or bad number.
- **`capsys`**: captures what the CLI prints, so tests can check the output
  and the exit code.
- **Coverage** (`pytest-cov`) measures which lines and branches the tests ran.
  This project is at 100%, and CI fails if it drops below 90%.

### `.github/workflows/tests.yml`

On every push, GitHub starts four fresh Linux machines (Python 3.11, 3.12,
3.13, 3.14), installs the project, runs the tests with coverage, and runs the
CLI on the sample file. The badge in the README shows whether the latest run
passed.

---

## 5 likely interview questions

**1. Why did you use `Decimal` instead of `float` for money?**

> Floats are stored in binary, so values like 0.1 can't be represented
> exactly; `0.1 + 0.2` is `0.30000000000000004` in Python. Small errors like
> that add up across many transactions and totals stop matching the bank.
> `Decimal` stores base-10 digits exactly. I parse amounts directly from the
> CSV string into `Decimal` so a float is never involved, keep everything at
> two decimal places, and round half-up only when displaying or computing
> percentages. I also export money as strings in JSON, because most JSON
> parsers would turn numbers back into floats.

**2. How does your program handle bad input without crashing?**

> I split errors into two levels. File-level problems (missing file, wrong
> encoding, missing columns) raise one custom exception, `FileFormatError`,
> which the CLI catches and prints as a one-line error with exit code 2.
> Row-level problems never raise out of the validator: each field has a parse
> function that raises a `FieldError`, a helper catches it and records the
> message, and the row is skipped with its line number. All problems in a row
> are collected, not just the first. The rest of the file is still processed.
> I tested it with a deliberately messy file and with parametrized tests for
> every rule.

**3. How do you detect duplicate entries, and what's the trade-off?**

> Each valid entry has an `identity()` tuple: date, type, category,
> lowercased description, amount and paycheck fields. I keep a dictionary
> from identity to the first row number where I saw it. Lookups are O(1) on
> average, so the whole check is O(n). The trade-off is that two genuinely
> identical purchases on the same day look like duplicates. I chose to be
> strict and document it (the user can label one `Coffee #2`), because
> silently double-counting money is worse. Fuzzy matching would be a possible
> improvement, but it risks dropping real transactions.

**4. How does the "unusually large expense" rule work, and why did you design
it that way?**

> Comparing every expense with the overall average would flag
> rent every single month. Instead I compare each expense with the average of
> the other expenses in the same category across the whole file. So a $1,299
> laptop is compared with other shopping (about $47 on average) and flagged at
> 27.8x, while rent is compared with other rent and isn't flagged. To keep it
> O(n) I first total each category, then compute "average of the others" as
> `(total − this) / (count − 1)`. I require at least two other expenses in the
> category, so it doesn't make claims with too little data. The multiplier is
> configurable from the command line.

**5. How did you structure and test the project?**

> It is a pipeline of small modules with one job each: parser (file),
> validator (values), calculator (totals), rules (warnings), report (output)
> and cli (arguments). Data moves through typed dataclasses, so each module can
> be tested alone without a file or a terminal. There are 137 pytest tests
> with 100% line and branch coverage, covering every validation rule, the
> calculations, every warning (including boundary cases like spending exactly
> at the limit), edge cases like an empty file, a file where every row is
> invalid and a month with no data, and the CLI's output and exit codes.
> GitHub Actions runs the suite on Python 3.11 to 3.14 on every push. Writing
> the tests also caught a real bug: a CSV error in the header row escaped my
> error handling, and I fixed it.

---

## Quick glossary

- **CSV**: "comma-separated values", a spreadsheet saved as plain text.
- **Dataclass**: a class whose boilerplate (`__init__`, `__eq__`) Python generates.
- **Enum**: a fixed set of named values (`INCOME`, `EXPENSE`).
- **stdout / stderr**: the two output streams of a program. Normal results go to
  stdout and warnings/errors to stderr, so they can be redirected separately.
- **Exit code**: the number a program returns to the shell; 0 means success.
- **CI (continuous integration)**: automatically running tests on every push.
- **Coverage**: the percentage of code lines and branches your tests execute.
