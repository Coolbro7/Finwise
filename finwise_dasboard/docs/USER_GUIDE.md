# Finwise — Application User Guide

**For:** Users of the Finwise local financial dashboard  
**Version described:** Finwise v1.3.1 (November 2026)  
**Currency:** Hong Kong dollars (HKD)  
**Purpose:** Learn how to run the app, manage transactions and bills, change financial settings, read charts, and use the optional AI shopping assistant.

> Finwise is a working **prototype**. Spending forecasts are estimates, not guaranteed future costs. The shopping assistant researches potential products, but it does not buy anything.

## 1. Start the application

1. Install **Python 3.10 or later**.
2. Open a terminal in the main Finwise project folder—the one containing `run_dashboard.py` and `.env`.
3. Run:

   ```bash
   python3 run_dashboard.py
   ```

   On Windows, `python run_dashboard.py` may be the appropriate command.
4. The browser should open automatically. Otherwise visit **http://127.0.0.1:8000**.
5. Leave the terminal running while using the dashboard.
(Currently, the app is a prototype, so it is locally hosted)

To stop: click inside the server's terminal window and press **Ctrl+C**. On macOS use **Control+C**, not Command+C. Closing the browser tab alone does not stop the server.

**Other startup options:**

```bash
# Change the port if 8000 is already taken
python3 run_dashboard.py --port 8001

# Don't automatically open the browser
python3 run_dashboard.py --no-browser

# Add synthetic transactions/settings to an EMPTY database
python3 run_dashboard.py --demo
```

For the last command, the `--demo` option does not overwrite an existing populated database.

### If you have reorganized your project

The folders may be named `backend/`, `frontend/`, `data/`, `examples/`, `tests/`, and `docs/`. You should still start the app using `run_dashboard.py` from the **project root**. This guide assumes the import and path adjustments described during the reorganization have already been made. If you have not reorganized it, the original root-level scripts and `static/` folder are also fine.

## 2. Understand the dashboard

Use the navigation bar:

| Section | What you can do |
|---|---|
| **Overview** | See income, expenses, Safe to Spend, the forecast, line chart, category donut and spending insights. |
| **Transactions** | Add, edit, delete, search, filter, and view transactions for the chosen month. |
| **Bills & insights** | Add/edit/delete confirmed bills, see possible recurring expenses and spending warnings. |
| **Budget settings** | Change monthly budget, cash, reserves, safety buffers, historical lookback and category limits. |
| **Can I afford it?** | Ask for shopping recommendations that respect the budget. |
| **Quick price checker** | Enter a known price and get an immediate affordability decision. |

The **Viewing** month selector near the top controls the financial month shown in the overview and transaction table. The shopping assistant deliberately uses the **current** financial situation even if you are browsing an older month.

The main summary cards are:

- **Total income:** Posted income received in the selected period.
- **Net expenses:** Posted purchases minus posted refunds.
- **Safe to Spend:** Budget-constrained spending allowance after remaining obligations and buffers; also limited by available cash if entered.
- **Month-end forecast:** Estimated total spending by the end of the selected month.

**Safe to Spend is not the same as the forecast.** The forecast predicts likely spending; the safe limit is a conservative spending guardrail.

## 3. Add a new transaction

1. Go to **Transactions**.
2. Click **+ Add transaction**.
3. Enter the **amount**, **type**, **date**, **status**, **category**, and optional **merchant/source** and **account label**.
4. Choose the right type:
   - `Expense` — money you spent.
   - `Income` — money you received.
   - `Refund` — money returned to you.
   - `Transfer` — money moved between accounts; not treated as spending.
5. For an actual completed payment, set **Status = Posted**.
6. Click **Save transaction**.

**Example:** HK$112 spent at a clothing shop on November 4. Choose `Expense`, `Posted`, category `Clothing`, and the appropriate date. The transaction appears in November and the cards/charts update.

**How saving works internally:** The browser sends the transaction to the Python server. The server creates the temporary file `data/new transaction.json`, imports its contents using the CLI into `data/budget.sqlite3`, and deletes the temporary JSON file. **SQLite keeps the transaction; the temporary file is not supposed to remain.**

## 4. View, search and filter saved transactions

1. Use the **Viewing** month selector at the top to choose a month.
2. Scroll to **Transactions** to see entries from that month.
3. Use the search box to find a merchant or category.
4. Use the transaction type dropdown to show all records, expenses, income, refunds, or transfers.

Only **posted** expense/refund transactions affect current net spending; pending and cancelled entries remain visible as records when included in the chosen month.

If a transaction seems missing, check the selected **month** first, then confirm that you started the dashboard using the correct database.

## 5. Edit or delete a transaction

**Edit:** Find the transaction in the table, click its **pencil/edit icon**, change fields, and save. The amount and charts will be recalculated.

**Delete:** Find the transaction, click its **delete (×) icon**, and confirm. The entry is removed from SQLite and the summaries update. Deletion is not reversible through the interface, so check the item before confirming.

Edits use the temporary JSON → CLI import workflow. Deletion operates directly on SQLite.

## 6. Change your monthly budget, cash and buffers

1. Go to **Budget settings**.
2. In **Financial overview**, modify the appropriate fields:

| Field | What it means |
|---|---|
| **Monthly spending budget** | Total spending target for a calendar month. |
| **Spendable cash (optional)** | Cash currently available for spending, entered manually. Finwise does not retrieve your bank balance. |
| **Expected other spending** | Additional likely future spending not already included in protected bill/reserve amounts. |
| **Budget safety buffer** | Amount of monthly budget you want to keep unspent for unexpected costs. |
| **Other unpaid cash obligations** | Unpaid cash commitments **other than** confirmed bills, which Finwise already protects automatically. |
| **Cash safety buffer** | Amount of actual cash you want to keep unavailable for discretionary purchases. |
| **History lookback (months)** | Number of prior completed months (1–24) used for category baseline estimates. |

3. Click **Save all settings**.
4. Return to **Overview** to see refreshed calculations.

**Important:** A positive budget remainder does not necessarily mean there is money in the bank. To have the cash constraint applied, enter an accurate **Spendable cash** amount.

## 7. Add, edit, or remove essential reserves

An essential reserve is money set aside for a future necessary expense (for example, grocery essentials, transport, or an outstanding utility payment).

1. Go to **Budget settings → Essential reserves**.
2. Click **+ Add reserve**.
3. Enter the category/name and amount, e.g. `Groceries — HK$400`.
4. Click **Save all settings**.
5. To change a reserve, edit its value. To remove it, use its row's removal control and save again.

These reserves reduce **Safe to Spend**. **Do not include already-paid transactions**. A bill that you also enter as a **confirmed bill** is automatically protected; you do not need to add it again as a reserve. If a manual reserve shares the confirmed bill's category, the larger amount is used instead of adding both amounts together.

## 8. Set category monthly limits

1. Go to **Budget settings → Category monthly limits**.
2. Click **+ Add limit**.
3. Enter a category (for example, `Shopping`) and a monthly spending ceiling (for example, `300`).
4. Click **Save all settings**.
5. Edit or remove a row later as needed.

The dashboard also shows **Remaining category allowances**, derived from historical category spending and available budget headroom. These are suggested ceilings, not instructions to spend the money. The overall Safe to Spend constraint still applies.

## 9. Add or manage confirmed future bills

1. Go to **Upcoming bills & insights**.
2. Click **+ Add bill**.
3. Enter **bill name**, **category**, **amount (HKD)**, and **due date**.
4. Click **Save bill**.
5. Use a confirmed bill's **edit icon** to change it or its **delete (×) icon** to remove it.

### How confirmed bills change the numbers

Suppose, on November 3:

```text
Monthly budget = HK$2,500
Posted spending = HK$112
Confirmed bill due November 20 = HK$600
No other reserves/buffers; no cash constraint entered
```

**Safe to Spend** becomes `2500 − 112 − 600 = HK$1,788`.

With no usable historical baseline, the current-pace month-end estimate becomes `(112 / 3 × 30) + 600 = HK$1,720`.

Finwise automatically includes confirmed bills **due after the analysis date and before the end of that month**. A bill due earlier is not treated as a future bill for that date. **If a bill is paid early, update or delete its confirmed-bill entry** so it is no longer reserved as unpaid. The prototype does not automatically match bills to payments or renew monthly bills for future months.

**Avoid double-counting:** Do not enter confirmed-bill amounts again in **Other unpaid cash obligations**.

## 10. Read recurring-pattern suggestions and insights

Under **Upcoming bills & insights → Recurring pattern candidates**, Finwise looks for merchants paid on reasonably regular dates. Three or more occurrences are needed before it suggests a repeating pattern.

The suggestions are **not automatically confirmed bills**. For example, repeated Friday restaurant orders should not automatically become a required weekly commitment. Add a real obligation manually using **+ Add bill**.

**Spending insights** can also warn about projected overspending, missing cash information, unusual large transactions, pending transactions and possible duplicates.

## 11. Understand the graphs and forecast

- **Spending overview** is a line chart. Choose **Cumulative** to see spending accumulate across the month, or **Daily** for daily changes.
- **Expense breakdown** is a donut chart showing where recorded spending occurred.
- **Month-end forecast** estimates final monthly spending using past category spending, current spending pace and confirmed upcoming bills.
- **Daily safe allowance** divides remaining safe discretionary spending by the days remaining **after today**.
- **Cash headroom** appears only when a spendable cash value is entered.

Changing the month alters the period shown. Historical months show recorded data through the end of that month; the selected current month uses today's date. The dashboard refreshes after edits and periodically while the browser tab is active.

## 12. Check a known purchase price

If you already know the price of something:

1. Find **Quick price checker** under the budget settings/allowances area.
2. Enter the total intended purchase price in HKD.
3. Click **Check affordability**.
4. Read whether the amount is within the calculated safe discretionary limit.

This checker does **not** search for products. It compares a known amount with your current budget/cash constraints.

## 13. Use the AI shopping assistant

The **Can I afford it?** shopping section is for users who know *what* they want, but not necessarily *what it costs*.

1. Open **Can I afford it?**.
2. Under **What would you like to buy?**, type a specific description, e.g. `black graffiti-print t-shirt`.
3. Choose **Online only**, **Nearby shops only**, or **Online + nearby shops**.
4. For nearby results, enter an area such as `Hung Hom, Hong Kong`, or click **Use my current location** and allow the browser's permission request.
5. Review the **Suggested maximum total purchase** calculated by Finwise.
6. Click **Find affordable options**.
7. Review product leads, store leads, source links, explanatory notes and any warnings.

The engine calculates the price ceiling from Safe to Spend, forecast headroom and daily allowance. Tavily then retrieves web results, and OpenRouter analyzes them. Product prices, store locations and stock remain **unverified** until you check with the seller. Finwise never makes a purchase on your behalf.

**Location privacy:** You can choose manual area entry instead of sharing your device location. Location is used for the shopping request and is not saved as a permanent location profile by this prototype.

## 14. Configure optional live AI shopping (private API keys)

**You do not need API keys to use the budgeting, transaction, bill or chart features.** For live shopping, you need a Tavily key and an OpenRouter key.

1. Create keys at:
   - **Tavily:** https://app.tavily.com/
   - **OpenRouter:** https://openrouter.ai/settings/keys
2. In the same folder as `run_dashboard.py`, make a private `.env` file if one does not already exist. On macOS:

   ```bash
   cp .env.example .env
   nano .env
   ```

3. Fill in your **own** keys:

   ```text
   OPENROUTER_API_KEY=YOUR_ACTUAL_OPENROUTER_KEY
   TAVILY_API_KEY=YOUR_ACTUAL_TAVILY_KEY
   OPENROUTER_MODEL=openrouter/free
   SHOPPING_DEMO=0
   ```

4. Save the file, restart the Python server, and reload the page.
5. In the shopping area, check for **OpenRouter + Tavily ready** before searching.

**Never share the `.env` file, paste API keys into chats, or include keys in screenshots or source control.** If you think a key was accidentally exposed, revoke it and issue a new one.

### Offline shopping demonstration

For a classroom demo without internet or API access, set:

```text
SHOPPING_DEMO=1
```

Restart the server. Shopping then shows **fictional classroom examples**, and **no external search or LLM calls** are made. Set it back to `0` and restart for live mode.

**This is separate from** the launcher flag `--demo`, which loads fictional financial transactions into an empty database for charts.

## 15. Data storage and backup

Finwise stores local financial records in:

```text
data/budget.sqlite3
```

The database contains transactions, settings and confirmed bills. **Back up this file before reinstalling the project or moving to a new version.** When upgrading, copy it into the new project's `data/` folder rather than replacing all your application files with old versions.

The transaction import file `data/new transaction.json` is **temporary** and is deleted automatically after each import; you do not need to create it manually.

The app has no cloud synchronization. Keeping the database file safe is your responsibility.

## 16. Troubleshooting

| Problem | What to try |
|---|---|
| Browser page won't open | Check that the server is still running; open `http://127.0.0.1:8000`. |
| Port 8000 already in use | Run `python3 run_dashboard.py --port 8001` and open port 8001. |
| Dashboard has no styles or graphs | Run the Python server instead of opening `index.html` directly. Ensure the frontend JS/CSS files are present and paths are correct; hard-refresh. |
| Dashboard totals are zero | Check the selected month, database path and whether transactions have `Posted` status. |
| Added bill doesn't reduce Safe to Spend | Ensure you're running the corrected v1.1+ budgeting engine; verify bill due date is later than the current analysis date. |
| Shopping says `Fictional classroom demo` | Set `SHOPPING_DEMO=0` in `.env`, restart, and confirm keys are configured. |
| Shopping says cannot reach services | Check Python HTTPS connection, DNS, proxy, firewall, or certificates. |
| Shopping says OpenRouter response is empty | Use the v1.3.1+ shopping module; try a specific currently available free model in `.env`. |
| Shopping returns only source links | Search results were obtained, but the LLM or evidence checks could not produce reliable product cards. |
| API key error or quota exceeded | Check both provider account dashboards and the server's terminal output. |
| Unusually low shopping price ceiling | Check confirmed bills, buffers, cash input, forecast and category constraints. |
| Newly installed version has no saved transactions | Copy your existing `data/budget.sqlite3` from the old version. |

Do not disable SSL certificate checks as a workaround. Do not paste private keys into error reports.

## 17. Five-minute assignment demonstration

1. **Launch:** Start with `python3 run_dashboard.py --demo` on a previously empty test database.
2. **Overview:** Show four summary cards, the monthly spending line graph and category donut.
3. **Transactions:** Add a posted expense, then edit its amount and delete it; show the figures update after each action.
4. **Budget settings:** Change monthly budget, add a reserve and show Safe to Spend decrease.
5. **Confirmed bills:** Add a future bill and show both Safe to Spend and the month-end forecast reflect it.
6. **Shopping:** Describe a graffiti-print t-shirt, display the computed price cap, then show either real Tavily/OpenRouter source-based results or clearly labeled offline demo results.

The core idea to explain to your instructor: **Python makes the financial decisions; the AI/search tools help research and explain shopping options.**

## 18. Where to find technical explanations

- `docs/BUDGETING_ENGINE.md`: every function in `budgeting_engine.py`, formulas and financial logic.
- `docs/SHOPPING_AI.md`: every function in `shopping_ai.py`, APIs, input validation and source filtering.
- This file: operating the dashboard from a user's perspective.
