# Complete Budgeting Framework — working prototype

**Scope:** transaction analysis, historical spending patterns, candidate recurring expenses,
manual confirmed future bills, forecasting, dynamic budgeting, cash constraints, and purchase
affordability. **Not included:** store/product recommendations, LLMs, bank connections,
financial account reconciliation, or a graphical frontend.

## Quick start (Python 3.10+, no external dependencies)

```bash
python -m unittest discover -v
python cli.py --db demo.sqlite3 import sample_transactions.json
python cli.py --db demo.sqlite3 set-budget 3000
python cli.py --db demo.sqlite3 set-config sample_config.json
python cli.py --db demo.sqlite3 add-bill sample_confirmed_bill.json
python cli.py --db demo.sqlite3 analyze --date 2026-10-15
python cli.py --db demo.sqlite3 purchase 350 --date 2026-10-15
```

The example uses synthetic HKD transactions and creates a local SQLite database.
Use `--db` consistently to refer to the same database.

## Engine components

| Component | Entry point | Purpose |
| --- | --- | --- |
| Validation | `load`, `quality` | Decimal money, transaction IDs, status, currency, duplicate flags |
| Accounting summary | `breakdown` | Income, gross expenses, refunds, net spending, daily/category/merchant breakdown |
| Recurrence candidates | `recurring` | Weekly, biweekly, monthly, quarterly, annual timing heuristics |
| Historical baselines | `history` | Per-category observed monthly averages/medians, excludes incomplete current month |
| Forecast | `forecast` | Current spending plus historical projection, current pace, confirmed upcoming bills |
| Spending patterns | `spending_rhythm` | Descriptive weekday averages |
| Unusual transactions | `anomalies` | High-amount flags relative to prior same-category transactions |
| Dynamic budget | `plan` | Essential reserves, budget headroom, cash headroom, shortfalls, adaptive category allowances |
| Purchase affordability | `purchase_check` | Maximum safe amount from independent budget and cash constraints |
| Orchestrator | `analyze` | Produces all components in one JSON-serializable report |
| Local persistence | `BudgetStore` in `storage.py` | SQLite transaction, setting, and confirmed bill storage |
| CLI | `cli.py` | Import, configure, analyze, assess purchase |

## Core equations

`net_spending = posted_expenses - posted_refunds`

`budget_headroom = monthly_budget - posted_net_spending - remaining_essential_reserves - expected_other_future_spending - budget_safety_buffer`

`cash_headroom = spendable_cash - unpaid_cash_obligations - cash_safety_buffer`

`safe_discretionary_limit = max(0, min(budget_headroom, cash_headroom))`
when cash balance is provided; otherwise uses budget headroom alone.

`daily_allowance = safe_discretionary_limit / remaining_days_after_today`

Category allocations distribute positive budget headroom proportionally to observed
category spending weights. Manual category caps further constrain suggested
allowances. Unused allocations do not imply the user should spend them.

## Recurrence policy

Detection is a **candidate generator** and never silently creates a confirmed bill.
It requires at least three distinct payment dates and sufficient regularity.
Merchant aliases, multiple charges per merchant, and variable billing dates can
produce misses or false positives. Confirm due date, amount, and category with the
user. A confirmed bill must be explicitly entered in `confirmed_bills`.

**Important (v1.1):** Confirmed bills due later this month now automatically
protect their unpaid amount in Safe to Spend and are included in the forecast.
Do not enter the same confirmed bill in `unpaid_cash_obligations`; that field
now means *other* cash obligations. Where a manual essential reserve shares a
category with confirmed bills, the larger amount is protected.

The current implementation does not automatically generate next month's
confirmed bill or payment schedules; the app must create the next due item
or user must enter it.

## Accounting boundaries and limitations

- **Monthly budget is not a bank balance.** A positive budget remainder does not
  mean the user has cash to spend.
- **Income** is tracked but future income is not counted as spendable until received.
- **Transfers** are excluded from income and spending; they are not used to derive
  account balances. The `spendable_cash` setting is an externally verified input.
- **Refunds** reduce net spending but cannot be automatically matched to an
  original charge. Unmatched/partial refunds require reconciliation in production.
- **Pending** transactions are excluded from posted spending; reserve them in
  `unpaid_cash_obligations` if they affect available cash.
- **Currency**: one currency per analysis, no automatic conversion. Keep original
  amounts, rates, and fees when adding FX handling later.
- **Missing months**: category baselines use months with observed activity;
  absence of data is not proof of zero spending.
- **Forecasting**: transparent rule-based heuristic, not ML. Estimates may be
  inaccurate for one-offs, irregular income, seasonality, and incomplete data.
  No prediction confidence interval or measured backtest error yet.
- **Recurring candidates**: never treated as confirmed future bills without user
  input.
- **Account data**: no bank sync, double-entry ledger, cross-account transfer
  matching, balance reconciliation, or multi-user authentication.
- **Local security**: SQLite is unencrypted. Do not store credentials or sensitive
  banking identifiers in it. Production requires authentication, encryption,
  auditing, backups, and privacy controls.
- **Budget period**: calendar month; custom cycles not implemented.
- **Dynamic category allocation**: basic proportional heuristic, not a constrained
  optimizer. A category absent from historical data receives no automatic
  allocation until the user supplies a limit or history.

## Architecture for next iteration

1. Introduce account-level balance snapshots and reconciliation, and a transaction
   lifecycle that handles pending->posted, refunds, chargebacks, split purchases,
   and transfer matching.
2. Store user-approved recurring schedules and due-date rules, distinguish
   essential/optional commitments, and automatically project each occurrence.
3. Add explicit future income and cash-flow timeline with confidence labels.
4. Improve forecasting using rolling medians, separate fixed/variable expenses,
   seasonality, and historical backtesting.
5. Build FastAPI endpoints around the existing `analyze` function, then a frontend
   dashboard; keep financial arithmetic outside any LLM.

## Important quality note

The included tests cover basic calculations and several boundary conditions.
This is a functional **prototype**, not a bug-free or production-certified
financial system. Review outputs and reconcile data before relying on them for
financial decisions.
