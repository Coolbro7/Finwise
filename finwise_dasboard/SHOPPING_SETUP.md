# Finwise v1.3: Shopping assistant setup for Hong Kong

This edition **does not use Google AI Studio or the Gemini API**. It uses:

- **Tavily Search API** to retrieve links and snippets for product listings and local shops.
- **OpenRouter free model API** to interpret and rank these sources.
- **The original Finwise Python budgeting engine** to compute and enforce the maximum purchase amount.

The offline demo still works without either API key. Transactions, bills, charts and
budgets are fully local and do not need any third-party service.

## Quick start

Requires Python 3.10+ and internet for live product research. No pip packages,
Node.js, or cloud deployment are required.

1. Download/extract the **complete** v1.3 ZIP to a fresh directory.
2. Preserve your existing transactions: copy `data/budget.sqlite3` from your OLD
   Finwise folder into `data/` of this new folder. **Do not delete or overwrite
   your original database without making a backup.** The ZIP contains no database.
3. In the new project folder, open a terminal and run:

   ```bash
   cp .env.example .env
   nano .env
   ```

4. Create two API keys:

   - **OpenRouter**: https://openrouter.ai/settings/keys — free model routing:
     https://openrouter.ai/openrouter/free
   - **Tavily**: https://app.tavily.com/ — search API documentation:
     https://docs.tavily.com/documentation/api-reference/endpoint/search

5. Replace the placeholders in `.env` with **your own private keys**:

   ```text
   OPENROUTER_API_KEY=sk-or-v1-YOUR_REAL_KEY
   TAVILY_API_KEY=tvly-YOUR_REAL_KEY
   OPENROUTER_MODEL=openrouter/free
   ```

   Do not paste API keys into the browser, JavaScript, GitHub or a message. The
   `.env` file is only read by the local Python server. Protect it with
   `chmod 600 .env` on macOS/Linux.

6. Save in nano: **Ctrl+O**, Enter, **Ctrl+X**. Then start:

   ```bash
   python3 run_dashboard.py
   ```

7. Open **http://127.0.0.1:8000**. The **Can I afford it?** section should
   report `OpenRouter + Tavily ready` when both keys are recognized.

On Windows, use `copy .env.example .env` in Command Prompt and
`python run_dashboard.py`. Ensure you have `.env` rather than `.env.txt`.

To use a different port: `python3 run_dashboard.py --port 8001`.

## Regional and pricing caveat

Google AI Studio does not list Hong Kong as an available Gemini Developer API
region. OpenRouter and Tavily advertise free tiers, but **we cannot verify
which account or provider routes work from your Hong Kong network without
using your keys from there**. Test both services once on your own machine.

As of November 2026, OpenRouter's `openrouter/free` is a $0 model-routing
option subject to limits (typically 50 free requests/day on a new account),
while Tavily offers 1,000 API credits/month without a credit card. A mixed
online+nearby search normally spends **two Tavily basic searches and one
OpenRouter inference request**. Prices/quotas can change.

OpenRouter's separate built-in **web search tool** can incur additional
charges even when the model itself is free. This app deliberately does not
invoke that paid tool; the Tavily free search tier supplies current results.

## How recommendations work

1. The user enters `graffiti print t-shirt` and chooses online, nearby, or both.
2. Finwise re-reads today's SQLite financial data and calculates:

   ```text
   forecast headroom = max(0, monthly budget - projected month-end spending)
   forecast shopping allocation = 80% of forecast headroom
   short-term shopping allocation = 3 x daily safe allowance
   purchase cap = min(safe discretionary balance,
                      forecast shopping allocation,
                      short-term shopping allocation)
   ```

   On the final calendar day, the short-term allocation is relaxed to the
   safe discretionary balance because the original engine reports zero days
   after today. All amounts are HKD. The percentages are prototype policies,
   **not** trained AI predictions.
3. Finwise searches Tavily for current results related to the product and,
   for nearby searches, the supplied area/location. Tavily is a web search
   engine, **not** a confirmed physical store inventory database.
4. The Tavily search results, a minimal shopping budget cap, the product
   description, and an optional approximate location are sent to an OpenRouter
   free model (default: `openrouter/free`).
5. The model proposes JSON product/store candidates and explanations.
6. Python accepts only product URLs present in Tavily search results and
   prices that are visibly present in those results' snippets. It independently
   rejects products exceeding the financial cap after listed shipping costs.
7. Finwise displays the product/store leads and the web source links.

**Do not treat these as guaranteed prices or stock.** Listings may be stale.
Unknown shipping fees, discounts, taxes and travelling costs are not reliably
included. A physical store mention doesn't confirm the item is there.

The current system does **not calculate exact walking distances**. It uses
location text for better web search and displays potentially nearby stores,
not a verified distance-ranked store search.

## Testing without live API keys (safe for presenting)

Set in `.env`:

```text
SHOPPING_DEMO=1
```

Then restart. Shopping responses will be explicitly marked **fictional**, and
no external web/LLM API calls will be made. To return to live mode, change
it to `SHOPPING_DEMO=0` and restart.

`python3 run_dashboard.py --demo` is *different*: it seeds an empty SQLite
financial database with synthetic transactions for the graphs and budget.

## Troubleshooting

- **Need both keys:** Ensure `.env` sits beside `run_dashboard.py` and contains
  working `OPENROUTER_API_KEY` and `TAVILY_API_KEY` values. Restart Python.
- **403 / unsupported region:** One external provider may reject the key,
  account, model/provider route, or network location. This is a service issue,
  not a bug in the financial engine. Check the provider account dashboard or
  use offline classroom mode. Do not assume a VPN is a compliant workaround.
- **429 / quota:** Review usage in OpenRouter and Tavily dashboards. The free
  model and search allowances have independent limits.
- **No product cards:** Products without an HKD price in a retrieved snippet,
  valid originating URL, or acceptable total price are excluded. The source
  links remain visible, so the feature is still useful without inventing prices.
- **AI unavailable but search works:** Results fall back to a `source_only`
  response with real Tavily links. You can still open and compare them.
- **Location denied:** Enter `Hung Hom, Hong Kong` or another area manually.
- **Port in use:** `python3 run_dashboard.py --port 8001`.
- **Old data missing:** You launched a new/empty `data/budget.sqlite3` file.
  Copy your original SQLite database into the new folder. Do not overwrite the
  old one without a backup.
- **UI looks wrong after update:** Use the entire v1.3 ZIP, including all
  files in `static/`, not a partial mix. Hard-refresh your browser.

## Privacy and scope

- API keys stay in `.env` on the Python server; never sent to the browser.
- The model gets only the product request, optional location, calculated cap,
  and third-party search results. **No full transaction history, account IDs,
  or bank records are sent.**
- The location is not stored by Finwise. If provided, it is sent to the
  external services to complete the request, subject to their own policies.
- Only standard Python HTTPS libraries are used; no dependencies need installing.
- Both APIs are external services; provider-side usage/data policies vary.
  Use fictional financial data for your coursework demo if privacy matters.

## Developer API

- `GET /api/shopping/status`: reports OpenRouter/Tavily setup status without keys.
- `GET /api/shopping/policy`: today's budget-derived purchase limit.
- `POST /api/shopping/recommend`: `{ "query": "graffiti print t-shirt", "mode": "both", "location": {"label":"Hung Hom, Hong Kong"} }`.

Run all tests:

```bash
python3 -m unittest discover -v
```

Tests simulate external API responses: **they do not demonstrate live
access from Hong Kong**, which must be checked using your own account.
