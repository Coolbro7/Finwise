# Finwise — AI Shopping Module Developer Documentation

**Source script:** `shopping_ai.py` (after reorganizing: `backend/shopping_ai.py`)  
**Audience:** Developers, project reviewers, and assignment evaluators  
**Purpose:** Explain how the shopping assistant connects budgeting results to live web research.  
**Code version reviewed:** Finwise v1.3.1 (November 2026)

## 1. Role in the application

`shopping_ai.py` implements the **Can I afford it? → AI shopping** feature. A user describes a product instead of entering its price. The module uses financial results already calculated by `budgeting_engine.py` to choose a conservative shopping cap. It can then use **Tavily** to retrieve web search results and **OpenRouter** to evaluate them with an LLM.

**The LLM does not decide financial affordability.** Python calculates the cap and rejects recommendations that exceed it. Neither Tavily search snippets nor LLM-generated text can guarantee a seller's current prices, shipping fees, availability or physical store inventory.

```text
Product description + optional location
    ↓
Existing budgeting analysis → deterministic shopping cap
    ↓
Tavily web search → cited source URLs/snippets
    ↓
OpenRouter LLM → suggested products/stores in JSON
    ↓
Python checks source links, price evidence and affordability
    ↓
Dashboard shows products, nearby store leads, sources or warnings
```

## 2. All functions and classes in `shopping_ai.py`

### A. Errors and configuration

| Name | Purpose |
|---|---|
| `ShoppingInputError` (exception) | Raised for invalid product descriptions, location, or shopping mode. |
| `ShoppingUnavailable` (exception) | Raised when search/LLM services, authentication, quotas or responses are unusable. |
| `load_private_env(path=None)` | Reads allowed settings from the server-side `.env` file, without overwriting existing environment variables. |
| `_has_key(name)` | Returns whether a configured API-key environment variable appears to contain a real value rather than a placeholder. |
| `config_status()` | Reports whether OpenRouter/Tavily keys are present, whether offline demo mode is enabled, and which model is selected. **Does not reveal the keys.** |

**Expected `.env` settings:**

```text
OPENROUTER_API_KEY=YOUR_OPENROUTER_KEY
TAVILY_API_KEY=YOUR_TAVILY_KEY
OPENROUTER_MODEL=openrouter/free
SHOPPING_DEMO=0
```

The `.env` file belongs beside `run_dashboard.py`. Never commit it to Git or include it in project submissions. A key set in the shell environment can override the value in `.env`.

### B. Shopping policy and input validation

| Function | Purpose |
|---|---|
| `shopping_policy(analysis)` | Uses the budget plan and forecast to calculate a conservative **maximum total purchase amount**. |
| `validate_request(data)` | Validates a 3–180 character product description, mode (`online`, `nearby`, `both`), optional area name, and optional latitude/longitude. |
| `valid_url(url)` | Accepts basic public HTTP(S) URLs and rejects malformed links, embedded credentials and obvious localhost targets. |

The shopping cap is **not** selected by the LLM. Its formula is:

```text
Forecast headroom = max(0, monthly budget − projected month-end spending)
Forecast allocation = 80% × forecast headroom
Short-term allocation = 3 × safe daily allowance

Maximum total purchase = min(
    safe discretionary spending limit,
    forecast allocation,
    short-term allocation
)
```

On the final day of the month, the short-term allocation uses the safe discretionary limit because the engine's `remaining_days_after_today` is zero. All amounts are HKD. The 80% and three-day multipliers are **prototype policy choices**, not results learned by an AI model.

If the calculated cap is zero, `recommend()` returns a **wait** decision without making a shopping search request.

### C. Accessing external search and LLM services

| Function | Purpose |
|---|---|
| `_post_json(url, payload, headers, transport=None, timeout=28)` | Sends JSON over HTTPS using the Python standard library; converts common HTTP/network errors into `ShoppingUnavailable`. |
| `search_tavily(query, transport=None)` | Searches Tavily for real web source results; keeps result titles, URLs and snippets. |
| `call_openrouter(context, transport=None)` | Asks an OpenRouter-hosted model to extract, compare, and rank products/stores found in the supplied Tavily results. |

The app can run with the free model-router identifier `openrouter/free`, or another valid model selected using `OPENROUTER_MODEL`. Free models can be unreliable or rate-limited. Version 1.3.1 requests a larger output budget than the original version and retries **once** when a model returns no visible text. If it still returns an empty response, it reports the model and completion reason.

**Important:** Tavily performs the current web retrieval. OpenRouter is used to analyze those retrieved sources. This module does **not** use Gemini or Google AI Studio.

Only a product description, optional location, financial purchase cap, and web search results are submitted to the shopping services. It does **not** submit the user's complete transaction history or banking information.

### D. Interpreting and validating model output

| Function | Purpose |
|---|---|
| `extract_json(s)` | Attempts to parse a JSON object from the LLM's text, including responses wrapped in Markdown code fences. |
| `normalize_response(model_response, policy, trusted_sources)` | Validates product and store suggestions against Tavily URLs; checks that claimed HKD prices appear in the retrieved snippets; rejects products over the cap. |

The LLM is instructed to return a JSON object containing:

- `summary`: explanation of the recommendations.
- `products`: suggested products with name, HKD price, shipping estimate, seller, source URL and note.
- `stores`: possible nearby physical stores with name, area, source URL and note.

`normalize_response()` independently applies important safeguards:

1. The product URL must exactly match a Tavily result URL.
2. The product's HKD price must be supported by a number in the corresponding search snippet.
3. Product amount plus stated shipping must fit the shopping cap.
4. Invalid, unpriced, unaffordable or unsupported listings are excluded.
5. Suggested physical stores are **leads**, not verified places where the item is in stock.

**Limitation:** A price shown in a search snippet may still be stale or incomplete. Unknown shipping, taxes, size availability, and travel costs are not reliably verified; the user should confirm costs with the seller.

### E. Search planning and orchestration

| Function | Purpose |
|---|---|
| `_queries(user)` | Builds one or two Tavily search phrases depending on whether the user wants online, nearby, or both. Includes an entered location or approximate browser coordinates where relevant. |
| `offline_demo(user, policy)` | Creates clearly labeled **fictional** product examples without contacting external services. |
| `recommend(data, analysis, search_call=search_tavily, model_call=call_openrouter)` | **Main shopping function:** validates request, calculates cap, handles offline mode, searches Tavily, calls OpenRouter, filters results, and returns a user-facing response. |

`recommend()` can return several outcomes:

| `status` | Meaning | What the user sees |
|---|---|---|
| `ok` | Tavily search and OpenRouter processing succeeded. | Validated product/store leads and source links. |
| `source_only` | Search results are available, but AI evaluation failed or didn't produce usable text; or no product listings were found. | Source links or an explanation instead of invented recommendations. |
| `demo` | `SHOPPING_DEMO=1`. | Explicitly fictional shopping examples with no external API calls. |
| `wait` | Shopping cap is zero. | Recommendation to postpone the purchase. |

An exception may also be raised if required API keys are missing or all external search attempts fail.

## 3. How this connects to the browser

The shopping tab is implemented by `static/shopping.js` (or `frontend/shopping.js` after reorganizing). The server exposes:

| Method and route | Purpose |
|---|---|
| `GET /api/shopping/status` | Check whether both API keys are configured and whether demo mode is on. |
| `GET /api/shopping/policy` | Calculate today's shopping cap from current financial records. |
| `POST /api/shopping/recommend` | Accept a product description and optional location, then return shopping results. |

Example request body:

```json
{
  "query": "black graffiti-print t-shirt",
  "mode": "both",
  "location": {"label": "Hung Hom, Hong Kong"}
}
```

Location can alternatively be collected through the browser's permission dialog. The system uses location for search relevance only; it does not currently calculate precise store distances or independently verify stock at a particular branch.

The shopping request uses **today's** financial state regardless of any older month selected for viewing in the dashboard. This prevents users from getting a larger shopping cap by selecting a past month.

## 4. Running live searches vs. demo mode

**Live search:** Put valid OpenRouter/Tavily keys in `.env` and set `SHOPPING_DEMO=0`, then restart the server. Internet, provider account access, model availability, and unused free-tier quotas are required.

**Offline class demonstration:** Set `SHOPPING_DEMO=1` and restart. Results are labeled fictional; **no external Tavily or OpenRouter calls are made**.

Note that `python3 run_dashboard.py --demo` is a **different** option. It adds fictional **financial transactions** to an empty database for chart demonstrations. It does not enable shopping offline mode by itself.

## 5. Common failures

| Message or symptom | Explanation / next step |
|---|---|
| `Fictional classroom demo` | `SHOPPING_DEMO=1`; change to `0` and restart for live results. |
| Shopping keys missing | Configure both keys in `.env` beside `run_dashboard.py`. |
| Cannot reach external shopping services | Network, proxy, DNS, TLS/certificate or timeout issue; check Python HTTPS connectivity. |
| OpenRouter returned no visible text | Free model may have consumed output tokens for reasoning or returned an empty response; select a specific available free chat model and restart. |
| HTTP 401/403 | API key, account entitlement or region may be rejected. |
| HTTP 429 | Free quota or rate limit reached. |
| Tavily links but no product cards | No adequately evidenced HKD listing price, product above cap, or an unusable model response. |
| Cap is HK$0 | Financial data does not support a discretionary shopping budget; check forecast, reserves, bills and available cash. |

Never disable SSL verification or put API keys in the frontend to work around a provider error.

## 6. Boundaries and limitations

- This is an **assignment prototype**, not an e-commerce purchase service.
- Recommendations are based on **third-party search snippets**, not guaranteed live checkout prices.
- Nearby searches use an approximate area, not validated distance ranking or inventory checks.
- Real search results may be empty if the calculated safe price is too low or price evidence is unavailable.
- External providers have independent accounts, availability requirements, data policies and quotas.
- Source URLs and descriptions must be reviewed before a purchase.

## 7. Related source files

- `budgeting_engine.py`: financial calculations and safe discretionary spending.
- `server.py`: local REST endpoints used by the shopping interface.
- `static/shopping.js` / `frontend/shopping.js`: shopping form, geolocation permission and result cards.
- `.env`: private API settings. Never publish.
