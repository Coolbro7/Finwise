# Finwise — Budgeting Dashboard + HK Shopping (v1.3)

**Start here for AI shopping:** [SHOPPING_SETUP.md](SHOPPING_SETUP.md). This edition works without Google AI Studio. It uses optional **Tavily web search** plus **OpenRouter free LLM inference** (two account keys) to find and evaluate shopping leads. The local Python engine computes affordability.

Everything else remains included: transactions, confirmed bills, cash/buffers, monthly budgets, dynamic forecasts and charts. **The ZIP does not contain your SQLite data**; copy `data/budget.sqlite3` from your old Finwise folder when updating.

No Node.js or pip requirements. Start with `python3 run_dashboard.py` (Python 3.10+). For an offline, fictional shopping demonstration set `SHOPPING_DEMO=1` in `.env`.

---

# Finwise — Local Budgeting Dashboard

A **working browser frontend** for the Python/SQLite budgeting framework. Designed as an assignment prototype; **no external packages or npm required for the financial dashboard. Live shopping research needs internet and two free-tier API keys.**

## Start here

Requires **Python 3.10+**.

1. Unzip the package.
2. Open a terminal in the extracted `finwise_budgeting_dashboard` folder.
3. Run:

   ```bash
   python run_dashboard.py --demo
   ```

   On macOS/Linux if `python` is unavailable, use `python3`.

4. Your web browser will open automatically at **http://127.0.0.1:8000**. If it does not open, enter that address manually.
5. To stop, press **Ctrl+C** in the terminal.

`--demo` seeds an **empty database** with fictional transactions and settings; it never overwrites existing transactions. For an empty personal workspace, launch without `--demo`:

```bash
python run_dashboard.py
```

The app creates and stores its SQLite database at `data/budget.sqlite3`.

If port 8000 is busy, use `python run_dashboard.py --demo --port 8010` and open http://127.0.0.1:8010.

## What you can do in the browser

| Task | Where to go |
|---|---|
| Add a transaction | **Transactions → Add transaction** |
| Edit a transaction | **Transactions → pencil icon** next to the entry |
| Delete a transaction | **Transactions → × icon**, then confirm |
| View transactions from a month | **Viewing** month selector in the top-right |
| Search/filter transactions | Search box and type filter above the transaction table |
| Update your monthly budget | **Budget settings → Monthly spending budget → Save all settings** |
| Set cash/buffers/expected spending | **Budget settings → Financial overview** |
| Add/edit/delete essential reserves | **Budget settings → Essential reserves** |
| Add/edit/delete category monthly limits | **Budget settings → Category monthly limits** |
| Add a confirmed bill | **Upcoming bills & insights → Add bill** |
| Edit/delete a bill | Pencil/× icons in Confirmed bills list |
| See recurring expense candidates | **Recurring pattern candidates** |
| See spending charts | **Spending overview** and **Expense breakdown** |
| See daily allowance and budget shortfall | Summary cards and Spending insights |
| Check a planned purchase | **Purchase affordability checker** |

The dashboard **recalculates immediately after changes** and also refreshes the analysis **every 15 seconds while the tab is visible**, provided the transaction/bill dialog isn't open.

### The requested temporary JSON file workflow

When you click **Save transaction** in the browser:

1. The browser sends the transaction to `POST /api/transactions`, or `PUT /api/transactions/{id}` if editing.
2. The local Python server validates the transaction and creates a file named **`data/new transaction.json`** with a JSON array holding that transaction.
3. The server executes the existing CLI importer via a subprocess:

   ```bash
   python cli.py --db data/budget.sqlite3 import "data/new transaction.json"
   ```

   (The code passes absolute file paths to avoid working-directory issues.)

4. The CLI imports the transaction into **SQLite** using the same ID on edits.
5. The server deletes `data/new transaction.json` **even if import fails**.
6. The browser fetches fresh analytics and updates the graphs and totals.

The temporary JSON file disappears very quickly, by design. Your saved transaction stays in `data/budget.sqlite3`.

Deleting a transaction is handled directly through `BudgetStore.delete_transaction()`; it does not require a JSON import.

## Running the backend CLI independently

All the original `cli.py` commands still work when pointed at the same database:

```bash
python cli.py --db data/budget.sqlite3 analyze --date 2026-11-03
python cli.py --db data/budget.sqlite3 set-budget 5000
python cli.py --db data/budget.sqlite3 import sample_transactions.json
```

If you have a database from the earlier prototype, run the dashboard using its path:

```bash
python run_dashboard.py --db /path/to/existing/demo.sqlite3
```

**Important:** The original CLI and dashboard must point at the **same SQLite file** to share data. Avoid writing to the database simultaneously from the terminal and dashboard.

## Source structure

```text
finwise_budgeting_dashboard/
├── run_dashboard.py          # One-command local launcher
├── server.py                 # REST API, dashboard reporting, CLI import bridge
├── budgeting_engine.py       # Existing financial analysis and calculations
├── storage.py                # Existing SQLite storage, plus bill deletion method
├── cli.py                    # Existing CLI importer and utilities
├── demo_data.py              # Synthetic monthly history (optional)
├── static/
│   ├── index.html            # Dashboard layout, forms, modal dialogs
│   ├── style.css             # Screenshot-inspired lime/green/cream visual theme
│   ├── app.js                # Browser interactions, SVG line graph, doughnut chart
│   └── shopping.js           # Shopping UI, permissions, recommendation cards
├── data/                     # Local .sqlite3 and temporary JSON imports
├── DASHBOARD_USER_GUIDE.txt  # Detailed demonstration guide
├── BACKEND_README.md         # Original backend documentation
└── test_*.py                 # Unit and REST API integration tests
```

## REST API reference

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/bootstrap?month=YYYY-MM` | Selected month's analysis, chart series, transactions, settings, and bills |
| PUT | `/api/settings` | Update budget and full settings configuration |
| POST | `/api/transactions` | Create transaction through temporary JSON + CLI |
| PUT | `/api/transactions/{id}` | Update a transaction through temporary JSON + CLI |
| DELETE | `/api/transactions/{id}` | Delete a transaction |
| POST | `/api/bills` | Add a confirmed bill |
| PUT | `/api/bills/{id}` | Update a confirmed bill |
| DELETE | `/api/bills/{id}` | Delete a confirmed bill |
| POST | `/api/purchase` | Check proposed purchase against Python safe spending limit |
| POST | `/api/demo/seed` | Load fictional data (empty database only) |
| GET | `/api/shopping/status` | Provider configuration status |
| GET | `/api/shopping/policy` | Calculated shopping price cap |
| POST | `/api/shopping/recommend` | Shopping web search + LLM evaluation |

API responses and request bodies are JSON. The app is served only on `127.0.0.1`, not on the public internet.

## Calculation and data limitations

- One **HKD** currency only; no live bank integration.
- A single **monthly budget setting** applies when you browse any month; this prototype does not store different budgets per historical month.
- Recurring expenses are **candidates** based on past payments. They are not automatically added to confirmed bills.
- Confirmed bills due later in the selected month **automatically reduce Safe to Spend** and are **included in the forecast**. You do not need to enter them separately as essential reserves. If you have a manual reserve with a matching category, the larger reserve amount is used (not their sum).
- Monthly spending forecasts are rule-based approximations, not trained AI predictions.
- Category allowances use historical proportions and may sum to more than the cash-constrained safe limit; **safe total limit always takes priority**.
- Past months are analyzed as of their month-end; current month as of today's date. Future months are not selectable.
- Transaction changes and bills are **permanent in the local SQLite database**. Create a backup of `data/budget.sqlite3` before deleting data.
- Local-only coursework prototype with **no authentication or encrypted database**. Do not store real banking passwords or financial account credentials. Run only on a trusted computer.

For details of the original financial formulas, see `BACKEND_README.md`.

## Testing

```bash
python -m unittest discover -v
```

The project includes unit tests from the original engine, storage tests, and tests for the web API, transaction JSON/CLI round trips, validation, and bill CRUD. Local HTTP API tests and JavaScript syntax checks are included. Live Hong Kong provider access still requires keys and a local network test.

## Confirmed-bill calculation fix (v1.1)

When a bill is due later in the current month, the app automatically includes it
in the month-end forecast, protects its unpaid cost in the remaining budget,
and reserves it against entered cash (if cash is provided). The former
implementation ignored confirmed bills in the pace-only forecast and required
manual essential reserves. Both behaviors were corrected.

- **Example (November 3):** budget 2500, posted expense 112, future bill 600
  on November 20, no cash constraint or other reserves -> Safe to Spend
  **1788**, projected month end **1720** when no historical baseline exists.
- The **Other unpaid cash obligations** field means obligations *other than*
  bills entered in the confirmed bill list. Do not include those bills twice.
- For manually entered essential reserves in the *same category* as a bill,
  the system protects whichever amount is larger to avoid obvious double counts.
- This is a simple prototype; a bill marked paid before its due date still
  remains scheduled until deleted/updated. Remove it or update it after an
  early payment. Bills due on or before the as-of date are not counted as future bills.
- Historical projections use category-level offsets for upcoming bills to avoid
  obvious double-counting, but the forecasting heuristic is not bank-grade.
