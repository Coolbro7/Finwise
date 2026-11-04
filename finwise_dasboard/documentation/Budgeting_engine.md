Finwise — Budgeting Engine Developer Documentation
Source script: budgeting_engine.py (after reorganizing: backend/budgeting_engine.py)
Audience: Developers, project reviewers, and assignment evaluators
Purpose: Explain the financial functions that power the Finwise dashboard.
Code version reviewed: Finwise v1.3.1 (November 2026)
1. Role in the application
budgeting_engine.py is the financial calculation layer. It receives transactions and settings, analyzes historical spending, forecasts the end of the month, protects upcoming confirmed bills, and calculates how much discretionary spending is currently supported. It does not directly save data, serve webpages, contact the shopping API, or manage bank accounts.

The data flow is:
1. storage.py reads saved transactions/settings/bills from SQLite.
2. server.py calls analyze(...) with those inputs.
3. analyze(...) calls the relevant functions described below.
4. The server sends the results to app.js, which updates graphs and cards.
5. shopping_ai.py uses the calculated results to set a shopping price ceiling.
This module uses Python's built-in decimal.Decimal for monetary amounts so calculations are not based on floating-point currency arithmetic. Dates are Python date objects. The application presently supports one currency per analysis (HKD in the dashboard).
2. Transaction data model
Transaction (dataclass)
Represents one transaction. Fields: id, date, amount, kind, category, merchant, account, status, currency, transfer_group, original_id.
- kind: expense, income, refund, or transfer.
- status: posted, pending, or cancelled.
- Only posted expenses and refunds affect net spending. Income is reported separately; transfers do not count as spending.
Transaction.parse(x) converts a transaction dictionary into a validated Transaction object. Missing required fields, invalid amounts, unsupported kinds/statuses, and invalid dates cause an error.

Example input:
{
  "id": "tx-example-01",
  "date": "2026-11-04",
  "amount": "112.00",
  "kind": "expense",
  "category": "Clothing",
  "merchant": "Example Shop",
  "account": "Checking",
  "status": "posted",
  "currency": "HKD"
}
3. All functions in budgeting_engine.py
A. Data validation and calendar helpers
Function	What it does	Why it exists
amount(x, signed=False)	Converts an amount to a two-decimal Decimal; rejects invalid/nonfinite values and negative values unless signed=True.	Safe, consistent currency calculations.
day(x)	Converts an ISO date string (YYYY-MM-DD) or Python date into a date.	Consistent date handling.
norm(x)	Lowercases text and normalizes punctuation/spacing.	Helps group similar merchant/category labels.
add_months(d, n, anchor=None)	Moves a date forward/backward by calendar months, constraining the day to the destination month's length.	Handles month boundaries for billing dates.
month_range(d)	Returns the first and last day of the month containing d.	Defines the current budget period.
cash_round(x)	Rounds a Decimal to two places using standard financial rounding.	Prevents extra fractional cents.
load(rows, currency='HKD')	Parses a list of transaction dictionaries; rejects duplicate transaction IDs and mixed currencies.	Ensures one consistent set of data enters the engine.
quality(tx)	Reports possible duplicate entries, counts of pending/cancelled records, uncategorized expenses, and total records.	Warns the user about data problems.


quality() only flags possible duplicates; it does not silently delete them.
B. Summaries of recorded spending
Function	What it does	Dashboard use
posted(tx, start, end)	Keeps only posted transactions within the inclusive date range.	Excludes pending or cancelled entries from financial totals.
net_expenses(tx)	Adds expense amounts, subtracts refunds, and ignores income/transfers.	Calculates net spending.
breakdown(tx, start, end)	Produces income, gross expenses, refunds, net spending, spending by category/merchant/day, and date range.	Summary cards, line chart, expense donut, and category statistics.


Core equation:
Net spending = posted expenses − posted refunds
Example: HK$500 of purchases and a HK$50 refund produce HK$450 of net spending. Transferring HK$200 between accounts does not increase spending.
C. Spending patterns and recurring-expense discovery
Function	What it does	Key qualification
recurring(tx, as_of, min_count=3)	Groups posted expenses by normalized merchant/category; evaluates timing gaps for weekly, biweekly, monthly, quarterly, or annual patterns; estimates the median charge and next date.	Produces unconfirmed candidates, not real obligations.
history(tx, as_of, months=3)	Computes average and median spending per category using previous completed calendar months (1–24 months supported).	Supplies historical baselines for forecasts and category allocation.
anomalies(tx, as_of, window=120)	Flags unusually large expenses occurring on as_of, using earlier same-category purchases.	Spending warnings; not fraud detection.
spending_rhythm(tx, as_of, window=90)	Calculates average recorded spending by weekday over a historical window.	Descriptive weekday spending insight.


Example recurrence: Three rent charges with similar amounts and approximately one month between dates may be flagged as a monthly candidate. It is not automatically added to the confirmed-bills database. The user must confirm it separately.

history() excludes the incomplete current month. Missing historical transactions can make its averages unreliable; it does not know whether an omitted month means no spending or missing data.
D. Future confirmed bills and forecasting
Function	What it does	Why it matters
upcoming_confirmed_bills(confirmed_bills, as_of)	Selects confirmed bills with due dates after as_of and within the same calendar month.	Identifies unpaid upcoming obligations for this month's calculation.
bill_totals_by_category(bills)	Adds upcoming bill amounts by category.	Supports reserve merging and forecast totals.
forecast(tx, as_of, budget, baselines, confirmed_bills=None)	Estimates total spending at month end using current spending pace, historical categories, and future confirmed bills.	Powers the month-end forecast card and overspending warnings.


The forecasting heuristic works as follows:
Current pace projection = spending to date × days in month / days elapsed
Historical projection  = spending to date + estimated remaining category spending

If historical baselines exist:
    Variable forecast = 70% × historical variable projection
                      + 30% × current pace projection
    Month-end forecast = variable forecast + confirmed future bills
Otherwise:
    Month-end forecast = current pace projection + confirmed future bills

Final result cannot be lower than: current posted spending + confirmed future bills.
The implementation subtracts overlapping confirmed-bill amounts from each corresponding historical category estimate before adding the confirmed bills, reducing the risk of counting the same obligation twice. The 70/30 weights are prototype assumptions, not learned ML parameters.

Example: On November 3, if HK$112 has been spent, the current-pace estimate for a 30-day month is HK$1,120. An unpaid confirmed HK$600 bill later that month raises the no-history projection to HK$1,720.
E. Dynamic budgeting and affordability
Function	What it does	Dashboard use
plan(tx, as_of, budget, reserves=None, expected_variable=0, buffer=0, spendable_cash=None, unpaid_cash_obligations=0, cash_buffer=0, category_caps=None, baselines=None)	Calculates remaining budget, reserves, budget and optional cash headroom, budget shortfall, safe discretionary limit, daily allowance, and proportional category allowances.	Safe to Spend, daily allowance, cash headroom, category allocations.
purchase_check(price, p, policy_cap=None)	Compares a proposed purchase price with the plan's safe discretionary limit (and optional stricter cap).	Quick price checker and AI-shopping price validation.
analyze(rows, *, as_of, monthly_budget, currency='HKD', lookback_months=3, confirmed_bills=None, essential_reserves=None, expected_other_spending=0, safety_buffer=0, spendable_cash=None, unpaid_cash_obligations=0, cash_buffer=0, category_caps=None)	Main orchestration function that validates inputs, calculates all analytics, automatically protects confirmed upcoming bills, and returns a combined report.	The server calls this to populate the dashboard.


The main affordability equations are:
Budget headroom = monthly budget
                − posted net spending
                − remaining essential reserves
                − other expected future spending
                − budget safety buffer

Cash headroom = entered spendable cash
              − other unpaid cash obligations
              − confirmed upcoming bills
              − cash safety buffer

Safe to Spend = max(0, min(budget headroom, cash headroom))
If spendable cash is not entered, the engine uses the budget constraint alone. In that case the result has not been checked against actual cash availability.

analyze() adds confirmed bills to protected reserves automatically. When a manual essential reserve and a confirmed bill have the same category, the engine protects the larger of the two, not their sum. The separate setting for Other unpaid cash obligations must therefore exclude confirmed bills. This is the corrected v1.1+ behavior.

plan() also distributes positive remaining budget headroom across historically observed discretionary categories in proportion to their historical spending. Manually set monthly category caps constrain individual category recommendations. These suggested allocations are not independent permissions to spend; overall cash and budget constraints still apply.

The daily allowance is calculated over the days remaining after the as-of date. It is zero on the final calendar day under the current implementation.
F. Formatting/output
Function	What it does
serialize(x)	Recursively converts Decimals and dates into strings suitable for JSON/API output.
to_json(x)	Converts a result object into formatted JSON text.


4. Main output of analyze()
The returned dictionary contains:
- current_month: spending totals and category/day breakdowns.
- quality: validation-related warnings and counts.
- historical_category_baselines: past category averages and medians.
- recurring_candidates: possible repeating expenses.
- forecast: month-end prediction, upcoming bills, projected variance, risk flag.
- budget_plan: safe spending limit, reserves, buffers, daily allowance, allocations.
- unusual_transactions_today: unusually large same-day entries.
- weekday_spending_patterns: weekday averages.
- warnings: limitations and cautionary information.
5. Worked example
Imagine the following November financial state:
Monthly budget:                     HK$2,500
Already recorded expenses:          HK$112
Confirmed bill due later this month: HK$600
Other manual reserves/buffers:      HK$0
Cash constraint:                    Not supplied
The budget-side safe discretionary limit is 2500 − 112 − 600 = HK$1,788. If there are only three days of spending history and no usable previous-month baseline, the month-end forecast is 112 / 3 × 30 + 600 = HK$1,720.

These numbers answer different questions: Safe to Spend is a budget guardrail; Month-End Forecast is an estimate of likely expenses.
6. Limitations of this prototype
- No trained machine-learning model; historical estimates and recurrence detection use rules/statistics.
- No live bank synchronization or automatic verified balance reconciliation.
- User-entered confirmed bills are single due-date records, not automatically renewed schedules.
- If a bill is paid early, edit or remove it so the engine does not continue treating it as unpaid.
- Pending payments do not count as posted expenses; include relevant pending commitments in cash obligations if needed.
- No currency conversion; the dashboard is configured for HKD.
- Forecasts are estimates, not guarantees. Limited transaction history reduces accuracy.
- Financial decisions are illustrative for the assignment, not professional financial advice.
7. Related source files
- storage.py: saving transactions, settings and confirmed bills to SQLite.
- server.py: REST API, month selection, chart data and the temporary transaction JSON → CLI import workflow.
- shopping_ai.py: shopping affordability cap, Tavily search, OpenRouter LLM, response validation.
- cli.py: terminal commands for imports, configuration and analysis.
- run_dashboard.py: starts the local browser application.