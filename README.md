# Python Financial Data & Application Engine

### Finance Engine: the `finance-engine` command-line tool

[![tests](https://github.com/SnehMistry/finance-engine/actions/workflows/tests.yml/badge.svg)](https://github.com/SnehMistry/finance-engine/actions/workflows/tests.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

**A command-line tool that reads your income and expenses from a CSV file and
tells you where your money went: net pay, deductions, spending by category,
savings rate, and warnings when something looks off.**

```bash
finance-engine summary sample_data/transactions.csv --month 2026-09
```

It is written in pure Python (standard library only), uses `Decimal` for every
amount of money, skips bad rows with clear messages instead of crashing, and is
covered by 137 tests at 100% coverage.

---

## Sample output

```text
$ finance-engine summary sample_data/transactions.csv --month 2026-09
Finance Engine report: September 2026
=====================================
Entries: 20 (income: 4, expense: 16)

+------------------+------------+
| Income           |     Amount |
+------------------+------------+
| Gross income     |  $7,056.55 |
|   Tax            | -$1,290.00 |
|   Benefits       |   -$360.00 |
|   Retirement     |   -$387.00 |
| Total deductions | -$2,037.00 |
+------------------+------------+
| Net income       |  $4,982.55 |
+------------------+------------+

+----------------------+-----------+--------+
| Expenses by category |    Amount |  Share |
+----------------------+-----------+--------+
| housing              | $1,650.00 |  43.0% |
| shopping             | $1,299.00 |  33.8% |
| groceries            |   $381.80 |   9.9% |
| utilities            |   $181.75 |   4.7% |
| dining               |    $94.50 |   2.5% |
| transport            |    $90.55 |   2.4% |
| education            |    $84.50 |   2.2% |
| entertainment        |    $24.00 |   0.6% |
| health               |    $22.80 |   0.6% |
| subscriptions        |    $10.99 |   0.3% |
+----------------------+-----------+--------+
| Total expenses       | $3,839.89 | 100.0% |
+----------------------+-----------+--------+

+----------------+------------+
| Bottom line    |     Amount |
+----------------+------------+
| Net income     |  $4,982.55 |
| Total expenses | -$3,839.89 |
+----------------+------------+
| Savings        |  $1,142.66 |
| Savings rate   |      22.9% |
+----------------+------------+

Warnings (3):
  ! 'housing' spending of $1,650.00 is 33.1% of net income (limit 30%).
  ! Row 50: $1,299.00 on shopping ('New laptop') is 27.8x your usual shopping expense (average $46.66).
  ! Row 58: gross $3,250.00 minus deductions $1,025.00 is $2,225.00, but net pay is recorded as $2,188.00 (off by $37.00).
```

Messy input is reported row by row, and the program keeps going:

```text
$ finance-engine validate sample_data/messy_transactions.csv
Row 3: date '2026-09-31' is not a valid YYYY-MM-DD date
Row 4: date '09/05/2026' is not a valid YYYY-MM-DD date
Row 5: amount 'abc' is not a number
Row 6: amount cannot be negative (got -45.00)
Row 7: category is missing
Row 8: unknown expense category 'gambling' (allowed: dining, education, entertainment, groceries, health, housing, insurance, other, shopping, subscriptions, transport, travel, utilities)
Row 9: type 'salary' must be 'income' or 'expense'
Row 11: duplicate of row 10
Row 12: amount '4.255' has more than 2 decimal places
Row 13: income-only field(s) set on an expense row: gross
Row 14: description is missing

Checked 14 rows: 3 valid, 11 invalid (skipped).
```

All data in `sample_data/` is made up.

## Features

- **CSV import** of income and expense entries, including paycheck details
  (gross pay, tax, benefits, retirement).
- **Validation of every row**: bad or impossible dates, non-numeric, negative or
  zero amounts, fractions of a cent, missing fields, unknown types or
  categories, paycheck fields on expense rows, extra columns, and duplicate
  entries. Each problem is reported with its row number, and the row is skipped.
- **Calculations** for any month or date range: gross income, each deduction,
  net income, expenses by category (with share of total), savings, and savings
  rate.
- **Rule-based warnings**:
  - spending more than you earned;
  - one category above a set percentage of net income (default 30%);
  - a one-off expense far above that category's usual amount (default 3x);
  - paychecks where gross minus deductions doesn't equal net pay.
- **Output** as a readable terminal table, or **export** to JSON or CSV.
- **No runtime dependencies.** Only `pytest` and `pytest-cov` for development.

## Install

Requires Python 3.11 or newer.

```bash
git clone https://github.com/SnehMistry/finance-engine.git
cd finance-engine
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

This installs the `finance-engine` command. `python -m finance_engine` also works.

## Usage

```bash
# Check a file and list every invalid row (exit code 1 if any are invalid)
finance-engine validate sample_data/transactions.csv

# Report on one month, a date range, or the whole file
finance-engine summary sample_data/transactions.csv --month 2026-09
finance-engine summary sample_data/transactions.csv --from 2026-07-01 --to 2026-08-31
finance-engine summary sample_data/transactions.csv

# Tune the warning thresholds
finance-engine summary sample_data/transactions.csv --month 2026-09 \
    --category-limit 40 --large-multiplier 5

# Export the same report as JSON (default) or CSV, to stdout or a file
finance-engine export sample_data/transactions.csv --month 2026-09 --format json
finance-engine export sample_data/transactions.csv --format csv -o report.csv
```

Run `finance-engine <command> --help` for every option.

| Exit code | Meaning |
|-----------|---------|
| 0 | Success |
| 1 | `validate` found invalid rows |
| 2 | Bad arguments, or the file is missing or unreadable |

### CSV format

```csv
date,type,category,description,amount,gross,tax,benefits,retirement
2026-09-01,expense,housing,Monthly rent,1650.00,,,,
2026-09-11,income,salary,Paycheck - Acme Data Co.,2188.00,3200.00,640.00,180.00,192.00
2026-09-14,income,freelance,Website for a local bakery,600.00,,,,
```

| Column | Required | Notes |
|--------|----------|-------|
| `date` | yes | `YYYY-MM-DD` |
| `type` | yes | `income` or `expense` (any case) |
| `category` | yes | must match the type (see below) |
| `description` | yes | free text |
| `amount` | yes | positive, at most 2 decimals, optional leading `$`. **For income, this is net pay** (what reached your bank). |
| `gross`, `tax`, `benefits`, `retirement` | no | income rows only; leave blank otherwise |

**Income categories:** `salary`, `freelance`, `bonus`, `interest`, `refund`, `other_income`
**Expense categories:** `housing`, `utilities`, `groceries`, `dining`, `transport`, `health`,
`insurance`, `entertainment`, `shopping`, `subscriptions`, `education`, `travel`, `other`

## Running the tests

```bash
pytest                                                   # 137 tests
pytest --cov=finance_engine --cov-report=term-missing    # with coverage (100%)
```

GitHub Actions runs the same suite on Python 3.11, 3.12, 3.13 and 3.14 on every
push and fails the build if coverage drops below 90%.

## Project structure

```text
finance-engine/
├── src/finance_engine/
│   ├── models.py       # Data types: RawRow, Entry, RowError, ParseResult, categories
│   ├── money.py        # Decimal helpers: rounding to cents, percentages, "$1,234.50" formatting
│   ├── parser.py       # Opens the CSV, checks the header, yields raw rows with row numbers
│   ├── validator.py    # Checks every field; turns raw rows into Entries or RowErrors
│   ├── calculator.py   # Period (month / date range) and Summary totals
│   ├── rules.py        # Warning rules and their thresholds (RuleConfig)
│   ├── report.py       # Terminal tables, JSON and CSV output
│   ├── cli.py          # argparse commands: validate, summary, export
│   └── __main__.py     # Enables `python -m finance_engine`
├── tests/              # pytest suite, one test file per module
├── sample_data/        # Fake data: a clean file and a deliberately messy one
├── .github/workflows/  # CI: tests + coverage on every push
├── pyproject.toml      # Packaging, `finance-engine` command, pytest/coverage config
├── LEARNING.md         # Plain-language walkthrough of the code + interview prep
└── LICENSE             # MIT
```

The data flows in one direction, and each stage only knows about the one before it:

```text
CSV file ─▶ parser ─▶ validator ─▶ calculator ─▶ rules ─▶ report
            RawRow    Entry /       Summary       Alert     table / JSON / CSV
                      RowError
```

## Design decisions

**Why `Decimal` and never `float`.** Floats are binary, so most decimal
fractions cannot be stored exactly: `0.1 + 0.2 == 0.30000000000000004`. Over
hundreds of transactions those errors add up, and totals stop matching a bank
statement. `Decimal("0.1") + Decimal("0.2")` is exactly `Decimal("0.3")`.
Amounts are parsed straight from the CSV text into `Decimal` (never through
`float`), stored with exactly two decimal places, and rounded half-up (the way
a receipt rounds) only for display and percentages. JSON exports write money as
strings like `"4982.55"`, because most JSON readers turn numbers into floats and
would undo all of this.

**How validation works.**
1. `parser.py` handles problems with the *whole file*: missing file, not UTF-8,
   missing or duplicate header columns. These stop the program with a clear
   `error:` message and exit code 2, because nothing useful can be done.
2. `validator.py` handles problems with *one row*. Each field has a small parse
   function that either returns a clean value or raises `FieldError` with a
   readable message. The row validator runs **all** of them and collects every
   message, so you can fix a row in one pass instead of one error at a time.
3. A row with any problem is skipped and recorded as a `RowError` with its line
   number in the file (the header is row 1, so the numbers match what a
   spreadsheet or text editor shows). Valid rows carry on. Bad data never raises
   an exception out of the validator, which is why the program never crashes on
   messy input.
4. Amounts are checked with a strict regular expression *before* being handed
   to `Decimal`, because `Decimal()` happily accepts `"NaN"`, `"Infinity"`,
   `"1e5"` and `"1_000"`, none of which belong in a budget.
5. Duplicates are detected after a row is otherwise valid: if every value
   matches an earlier valid row (description compared case-insensitively), the
   later copy is skipped as `duplicate of row N`.

**Other decisions I made (and why):**

- **`amount` is net pay for income.** It is the number you can check against
  your bank account. Gross and deductions are optional extras; when `gross` is
  blank, gross is taken as net + deductions.
- **Large expenses are compared within their own category, across the whole
  file.** Comparing against the overall average would flag rent every month.
  Comparing a laptop with other shopping, and requiring at least two other
  expenses in that category before judging, gives far fewer false alarms.
- **Category limit is a share of net income, not of expenses.** "Rent is 33%
  of what I take home" is the version people actually budget with (the classic
  30% housing guideline).
- **Duplicates are exact matches only.** Two genuinely identical purchases on
  the same day need a slightly different description (e.g. `Coffee #2`). I chose
  this over fuzzy matching because skipping a real transaction silently would be
  worse than asking the user to label it.
- **Standard library only.** I left out `rich` and wrote a small ASCII table
  helper instead, so the tool installs with nothing extra and its output is
  plain text that is easy to test exactly.
- **`src/` layout.** Tests run against the installed package, not loose files,
  which catches packaging mistakes.
- **Exit codes** let the tool be used in scripts: `finance-engine validate
  data.csv && ...` only continues if the file is clean.
- Unknown extra columns in the header are ignored, so you can keep your own
  notes column in the spreadsheet.

## Possible next steps

- Monthly budgets per category and a "budget vs actual" report
- Recurring-transaction detection (subscriptions you forgot about)
- Month-over-month trend comparison
- Importers for common bank export formats

## License

[MIT](LICENSE) © 2026 Sneh Vinay Mistry
