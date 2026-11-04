
"""Personal budgeting engine. Python 3.10+, standard library only.

Financial amounts are Decimal, persisted as strings. Calendar dates are local dates.
Predictions are estimates, not authoritative cash balances.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from statistics import median
from typing import Any
import calendar
import json
import re

CENT = Decimal("0.01")
Z = Decimal("0.00")
KINDS = {"expense", "income", "refund", "transfer"}
STATUSES = {"posted", "pending", "cancelled"}

def amount(x: Any, *, signed=False) -> Decimal:
    if isinstance(x, bool) or x is None:
        raise ValueError("Invalid monetary amount")
    try:
        v = Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Invalid monetary amount") from exc
    if not v.is_finite() or (v < 0 and not signed):
        raise ValueError("Amount must be finite and nonnegative")
    return v.quantize(CENT, rounding=ROUND_HALF_UP)

def day(x: Any) -> date:
    if isinstance(x, date) and not hasattr(x, "hour"):
        return x
    try:
        return date.fromisoformat(x)
    except (TypeError, ValueError) as exc:
        raise ValueError("Use YYYY-MM-DD dates") from exc

def norm(x: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", x.lower())).strip()

def add_months(d: date, n: int, anchor: int | None = None) -> date:
    i = d.year * 12 + d.month - 1 + n
    y, m = divmod(i, 12)
    m += 1
    return date(y, m, min(anchor or d.day, calendar.monthrange(y, m)[1]))

def month_range(d: date):
    return d.replace(day=1), d.replace(day=calendar.monthrange(d.year, d.month)[1])

def cash_round(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)

@dataclass(frozen=True)
class Transaction:
    id: str
    date: date
    amount: Decimal
    kind: str
    category: str
    merchant: str
    account: str
    status: str
    currency: str
    transfer_group: str = ""
    original_id: str = ""

    @classmethod
    def parse(cls, x: dict) -> "Transaction":
        if not isinstance(x, dict):
            raise ValueError("Transaction must be an object")
        for k in ("id", "date", "amount", "kind"):
            if k not in x or x[k] is None or x[k] == "":
                raise ValueError(f"Missing transaction field: {k}")
        kind = str(x["kind"]).lower().strip()
        status = str(x.get("status", "posted")).lower().strip()
        currency = str(x.get("currency", "HKD")).upper().strip()
        if kind not in KINDS or status not in STATUSES or not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("Invalid kind, status, or currency")
        if not str(x["id"]).strip():
            raise ValueError("Empty transaction id")
        return cls(str(x["id"]), day(x["date"]), amount(x["amount"]), kind,
                   str(x.get("category") or "Uncategorized").strip(),
                   str(x.get("merchant") or "").strip(),
                   str(x.get("account") or "default").strip(), status, currency,
                   str(x.get("transfer_group") or ""), str(x.get("original_id") or ""))

def load(rows: list[dict], currency: str = "HKD") -> list[Transaction]:
    tx = [Transaction.parse(x) for x in rows]
    ids = [t.id for t in tx]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate transaction IDs: reconcile before calculating")
    if any(t.currency != currency for t in tx):
        raise ValueError("Mixed currencies: convert externally with auditable FX records")
    return tx

def quality(tx: list[Transaction]) -> dict:
    groups = defaultdict(list)
    for t in tx:
        if t.status == "posted" and t.kind != "transfer":
            groups[(t.date, t.amount, t.kind, norm(t.merchant), norm(t.category), t.account)].append(t.id)
    return {"possible_duplicates": [ids for ids in groups.values() if len(ids)>1],
            "pending_count": sum(t.status=="pending" for t in tx),
            "cancelled_count": sum(t.status=="cancelled" for t in tx),
            "uncategorized_count": sum(t.category=="Uncategorized" and t.kind=="expense" for t in tx),
            "transaction_count": len(tx)}

def posted(tx: list[Transaction], start: date, end: date) -> list[Transaction]:
    return [t for t in tx if t.status == "posted" and start <= t.date <= end]

def net_expenses(tx: list[Transaction]) -> Decimal:
    return sum((t.amount if t.kind == "expense" else -t.amount if t.kind == "refund" else Z for t in tx), Z)

def breakdown(tx: list[Transaction], start: date, end: date) -> dict:
    items = posted(tx, start, end)
    categories = defaultdict(lambda: Z)
    merchants = defaultdict(lambda: Z)
    daily = defaultdict(lambda: Z)
    for t in items:
        if t.kind in {"expense", "refund"}:
            v = t.amount if t.kind == "expense" else -t.amount
            categories[t.category] += v
            daily[t.date.isoformat()] += v
            if t.kind == "expense":
                merchants[t.merchant or "Unknown"] += v
    return {"income": sum((t.amount for t in items if t.kind == "income"), Z),
            "gross_expenses": sum((t.amount for t in items if t.kind == "expense"), Z),
            "refunds": sum((t.amount for t in items if t.kind == "refund"), Z),
            "net_spending": net_expenses(items),
            "category_net": dict(categories), "merchant_gross": dict(merchants),
            "daily_net": dict(daily), "start": start, "end": end}

def recurring(tx: list[Transaction], as_of: date, min_count: int = 3) -> list[dict]:
    """Conservative heuristic; requires user confirmation before scheduling bills."""
    if min_count < 3:
        raise ValueError("min_count must be >=3")
    groups = defaultdict(list)
    for t in tx:
        if t.kind == "expense" and t.status == "posted" and t.date <= as_of and t.merchant:
            groups[(norm(t.merchant), norm(t.category))].append(t)
    found = []
    for key, rows in groups.items():
        # A single merchant may have multiple purchases per day; do not infer recurring
        # bills from these without a distinct descriptor or user confirmation.
        bydate = defaultdict(lambda: Z)
        for t in rows:
            bydate[t.date] += t.amount
        dates = sorted(bydate)
        if len(dates) < min_count:
            continue
        gaps = [(b-a).days for a,b in zip(dates, dates[1:])]
        candidates = [("weekly",7,2),("biweekly",14,3),("monthly",30,5),
                      ("quarterly",91,10),("annual",365,20)]
        choices = []
        for name, nominal, tol in candidates:
            fit = sum(abs(g-nominal)<=tol for g in gaps)/len(gaps)
            if fit >= .75:
                choices.append((fit, name, nominal))
        if not choices:
            continue
        fit, cadence, nominal = max(choices)
        values = list(bydate.values())
        med = cash_round(Decimal(str(median(values))))
        if med == 0:
            continue
        mad = Decimal(str(median([abs(v-med) for v in values])))
        variability = mad/med
        last = dates[-1]
        if cadence in {"monthly","quarterly","annual"}:
            nxt = add_months(last, {"monthly":1,"quarterly":3,"annual":12}[cadence], dates[0].day)
        else:
            nxt = last+timedelta(days=nominal)
        # Roll forward if missed payment; it remains only a candidate.
        while nxt <= as_of:
            if cadence in {"monthly","quarterly","annual"}:
                nxt = add_months(nxt, {"monthly":1,"quarterly":3,"annual":12}[cadence], dates[0].day)
            else:
                nxt += timedelta(days=nominal)
        found.append({"key":"|".join(key), "merchant":rows[-1].merchant,
                      "category":rows[-1].category, "cadence":cadence,
                      "typical_amount":med, "last_seen":last,
                      "next_expected":nxt, "occurrences":len(dates),
                      "confidence":"high" if fit >= .95 and variability <= Decimal(".15") else "medium",
                      "confirmed":False})
    return sorted(found, key=lambda x:(x["next_expected"], x["merchant"]))

def history(tx: list[Transaction], as_of: date, months: int = 3) -> dict:
    """Only full prior calendar months. Missing data is not treated as zero."""
    if not 1 <= months <= 24:
        raise ValueError("months must be 1..24")
    start = add_months(as_of.replace(day=1), -months)
    end = as_of.replace(day=1)-timedelta(days=1)
    bycat = defaultdict(dict)
    for t in posted(tx, start, end):
        if t.kind in {"expense","refund"}:
            month = t.date.strftime("%Y-%m")
            v = t.amount if t.kind=="expense" else -t.amount
            bycat[t.category][month] = bycat[t.category].get(month,Z)+v
    result={}
    for cat, month_map in bycat.items():
        vals = list(month_map.values())
        result[cat] = {"average_observed_month":cash_round(sum(vals,Z)/len(vals)),
                       "median_observed_month":cash_round(Decimal(str(median(vals)))),
                       "observed_months":len(vals),
                       "required_months":months,
                       "complete_history":len(vals)==months,
                       "monthly_values":month_map}
    return result

def upcoming_confirmed_bills(confirmed_bills: list[dict] | None, as_of: date) -> list[dict]:
    """Unpaid bill occurrences scheduled later this calendar month.

    Confirmation means the app expects this bill to be unpaid until the user
    records it as paid or its due date passes. Paying early requires removal
    or an edit of the confirmed bill in this simple prototype.
    """
    _, end = month_range(as_of)
    upcoming = []
    for bill in confirmed_bills or []:
        due = day(bill["due"])
        if as_of < due <= end:
            upcoming.append({"id": bill.get("id", ""),
                             "name": bill.get("name", bill["category"]),
                             "category": str(bill["category"]),
                             "amount": amount(bill["amount"]), "due": due})
    return upcoming


def bill_totals_by_category(bills: list[dict]) -> dict[str, Decimal]:
    totals = defaultdict(lambda: Z)
    for bill in bills:
        totals[bill["category"]] += bill["amount"]
    return dict(totals)


def forecast(tx: list[Transaction], as_of: date, budget: Decimal,
             baselines: dict, confirmed_bills: list[dict] | None = None) -> dict:
    """Estimate month-end spending, always including confirmed unpaid bills.

    For each category, subtract the confirmed bill amount from its historical
    expected future spending (to avoid counting the same category twice), then
    add the full confirmed amount outside the statistical blend. When there is
    no history, the forecast is current pace + future confirmed bills.
    """
    first, last = month_range(as_of)
    current = posted(tx, first, as_of)
    actual = net_expenses(current)
    elapsed = (as_of-first).days+1
    remaining = (last-as_of).days
    period_days = (last-first).days+1
    upcoming = upcoming_confirmed_bills(confirmed_bills, as_of)
    confirmed_by_cat = bill_totals_by_category(upcoming)
    bills_total = sum(confirmed_by_cat.values(), Z)
    historical_future = {}
    for cat, entry in baselines.items():
        historical_future[cat] = cash_round(
            entry["average_observed_month"] * Decimal(remaining) / Decimal(period_days))
    # Historical future amounts for a category may already anticipate the bill.
    # Preserve excess estimated variable spending, but never dilute commitments.
    variable_future = {
        cat: max(Z, historical - confirmed_by_cat.get(cat,Z))
        for cat, historical in historical_future.items()
    }
    remaining_by_cat = dict(variable_future)
    for cat, total in confirmed_by_cat.items():
        remaining_by_cat[cat] = remaining_by_cat.get(cat,Z) + total
    pace_projection = cash_round(actual * Decimal(period_days) / Decimal(elapsed))
    baseline_variable_projection = actual + sum(variable_future.values(), Z)
    if not baselines:
        projected = pace_projection + bills_total
        method = "current_pace_plus_confirmed_bills"
    else:
        variable_projection = cash_round(
            Decimal(".7")*baseline_variable_projection + Decimal(".3")*pace_projection)
        projected = variable_projection + bills_total
        method = "historical_and_pace_plus_confirmed_bills"
    projected = cash_round(max(actual + bills_total, projected))
    return {"actual_spending": actual,
            "forecast_remaining_by_category": remaining_by_cat,
            "confirmed_upcoming_bills": upcoming,
            "upcoming_confirmed_total": bills_total,
            "projected_month_end": projected, "monthly_budget":budget,
            "projected_variance":budget-projected,
            "over_budget_risk":projected>budget, "method":method,
            "days_elapsed":elapsed, "days_remaining":remaining,
            "confidence":"low" if not baselines or elapsed<7 else "medium",
            "note":"Confirmed future bills are included. Variable spending forecasts remain estimates."}

def anomalies(tx: list[Transaction], as_of: date, window: int=120) -> list[dict]:
    """Flag same-day category outliers using preceding history only."""
    previous=defaultdict(list)
    for t in tx:
        if t.status=="posted" and t.kind=="expense" and as_of-timedelta(days=window)<=t.date<as_of:
            previous[t.category].append(t.amount)
    result=[]
    for t in tx:
        if t.status!="posted" or t.kind!="expense" or t.date!=as_of:
            continue
        vals=previous[t.category]
        if len(vals)<5:
            continue
        med=Decimal(str(median(vals)))
        mad=Decimal(str(median([abs(v-med) for v in vals])))
        threshold=max(med*3, med+3*mad)
        if threshold>0 and t.amount>threshold:
            result.append({"transaction_id":t.id,"category":t.category,
                           "amount":t.amount,"historical_median":cash_round(med),
                           "review_only":True})
    return result

def spending_rhythm(tx: list[Transaction], as_of: date, window: int=90) -> dict:
    start=as_of-timedelta(days=window-1)
    totals=defaultdict(lambda:Z)
    for t in posted(tx,start,as_of):
        if t.kind=="expense": totals[t.date]+=t.amount
        elif t.kind=="refund": totals[t.date]-=t.amount
    days=defaultdict(list)
    for i in range(window):
        d=start+timedelta(days=i)
        days[d.strftime("%A")].append(max(Z,totals[d]))
    return {name:{"average_per_calendar_day":cash_round(sum(v,Z)/len(v)),
                  "days_observed":len(v)} for name,v in days.items()}

def plan(tx: list[Transaction], as_of: date, budget: Decimal,
         reserves: dict[str, Any] | None = None, expected_variable: Any = 0,
         buffer: Any = 0, spendable_cash: Any | None = None,
         unpaid_cash_obligations: Any = 0, cash_buffer: Any = 0,
         category_caps: dict[str, Any] | None = None, baselines: dict | None = None) -> dict:
    """Independent budget and cash constraints; do not double count inside either."""
    first,last=month_range(as_of)
    spent=net_expenses(posted(tx,first,as_of))
    res={str(k):amount(v) for k,v in (reserves or {}).items()}
    caps={str(k):amount(v) for k,v in (category_caps or {}).items()}
    future=amount(expected_variable)
    reserve_total=sum(res.values(),Z)
    safety=amount(buffer)
    budget_headroom=budget-spent-reserve_total-future-safety
    cash_headroom=None
    if spendable_cash is not None:
        cash_headroom=amount(spendable_cash)-amount(unpaid_cash_obligations)-amount(cash_buffer)
    safe=max(Z,budget_headroom)
    if cash_headroom is not None:
        safe=min(safe,max(Z,cash_headroom))
    days_left=(last-as_of).days
    cat_spend=breakdown(tx,first,as_of)["category_net"]
    weights={}
    reserve_keys={norm(k) for k in res}
    for cat, entry in (baselines or {}).items():
        if norm(cat) not in reserve_keys:
            w=max(Z,entry["average_observed_month"])
            if w>0: weights[cat]=w
    total_weights=sum(weights.values(),Z)
    dynamic={}
    pool=max(Z,budget_headroom)
    if total_weights:
        remaining=pool
        ordered=sorted(weights)
        for cat in ordered[:-1]:
            v=cash_round(pool*weights[cat]/total_weights)
            dynamic[cat]=v
            remaining-=v
        dynamic[ordered[-1]]=remaining
    limits={}
    for cat in sorted(set(caps)|set(dynamic)):
        spent_cat=cat_spend.get(cat,Z)
        manual_remaining=caps[cat]-spent_cat if cat in caps else None
        recommended=dynamic.get(cat,Z)
        if manual_remaining is not None:
            recommended=min(recommended,max(Z,manual_remaining))
        limits[cat]={"spent":spent_cat,"monthly_cap":caps.get(cat),
                     "manual_remaining":manual_remaining,
                     "dynamic_remaining":dynamic.get(cat,Z),
                     "recommended_remaining":recommended}
    return {"budget":budget,"spent":spent,
            "nominal_remaining":budget-spent,
            "remaining_essential_reserves":res,
            "reserve_total":reserve_total,
            "expected_other_future_spending":future,"budget_buffer":safety,
            "budget_headroom":budget_headroom,
            "budget_shortfall":max(Z,-budget_headroom),
            "cash_headroom":cash_headroom,
            "safe_discretionary_purchase_limit":safe,
            "remaining_days_after_today":days_left,
            "safe_daily_allowance":cash_round(safe/Decimal(days_left)) if days_left else Z,
            "dynamic_category_allowances":limits,
            "unallocated_pool_if_no_history":pool if not weights else Z,
            "binding_constraint":"cash" if cash_headroom is not None and cash_headroom<budget_headroom else "budget",
            "assumptions":[
                "Reserves are unpaid future costs; do not include paid expenses.",
                "Expected variable spending excludes reserves and the proposed purchase.",
                "Cash balance excludes unavailable funds; future income is not spendable until received.",
                "Pending authorizations must be included in cash obligations when applicable.",
                "Dynamic category allowances are ceilings, not spending targets.",
            ]}

def purchase_check(price: Any, p: dict, policy_cap: Any | None = None) -> dict:
    v=amount(price)
    limit=p["safe_discretionary_purchase_limit"]
    if policy_cap is not None:
        limit=min(limit,amount(policy_cap))
    return {"price":v,"safe_limit":limit,"affordable":v<=limit,
            "headroom_after_purchase":limit-v,
            "binding_constraint":p["binding_constraint"]}

def analyze(rows: list[dict], *, as_of: str, monthly_budget: Any,
            currency: str="HKD", lookback_months: int=3,
            confirmed_bills: list[dict] | None=None,
            essential_reserves: dict | None=None,
            expected_other_spending: Any=0, safety_buffer: Any=0,
            spendable_cash: Any | None=None, unpaid_cash_obligations: Any=0,
            cash_buffer: Any=0, category_caps: dict | None=None) -> dict:
    today=day(as_of)
    budget=amount(monthly_budget)
    tx=load(rows,currency)
    h=history(tx,today,lookback_months)
    rec=recurring(tx,today)
    first,_=month_range(today)
    due_bills = upcoming_confirmed_bills(confirmed_bills,today)
    by_cat = bill_totals_by_category(due_bills)
    due_total = sum(by_cat.values(),Z)

    # Keep manually entered essential reserves, but if a confirmed bill and a
    # manual reserve use the same category, protect at least the larger amount
    # rather than double-counting them.
    merged_reserves={str(cat):amount(v) for cat,v in (essential_reserves or {}).items()}
    for category, bill_total in by_cat.items():
        prior=next((k for k in merged_reserves if norm(k)==norm(category)),None)
        key=prior if prior is not None else category
        merged_reserves[key]=max(merged_reserves.get(key,Z),bill_total)

    # Cash obligations entered manually are *other* obligations, excluding
    # confirmed bills. Automatically protect confirmed bills in cash as well.
    other_cash_obligations=amount(unpaid_cash_obligations)
    p=plan(tx,today,budget,merged_reserves,
           expected_other_spending,safety_buffer,
           spendable_cash,other_cash_obligations+due_total,
           cash_buffer,category_caps,h)
    p["auto_confirmed_bill_total"]=due_total
    p["auto_confirmed_bill_reserves_by_category"]=by_cat
    p["other_unpaid_cash_obligations"]=other_cash_obligations
    p["total_cash_obligations_including_bills"]=other_cash_obligations+due_total
    return {"currency":currency,"as_of":today,
            "quality":quality(tx),
            "current_month":breakdown(tx,first,today),
            "historical_category_baselines":h,
            "recurring_candidates":rec,
            "forecast":forecast(tx,today,budget,h,confirmed_bills),
            "budget_plan":p,
            "unusual_transactions_today":anomalies(tx,today),
            "weekday_spending_patterns":spending_rhythm(tx,today),
            "warnings":[
                "Confirmed bills due later this month are automatically protected in budget and cash constraints.",
                "Do not also include confirmed bills in the manually entered OTHER cash obligations.",
                "When a manual essential reserve matches a bill category, the larger amount is used, not their sum.",
                "Recurring candidates are not guaranteed bills; confirm them first.",
                "Forecasts can be inaccurate when transactions are missing or historical months are incomplete.",
                "Bills paid early require manual update or removal to avoid counting them as still unpaid.",
                "No automatic FX conversion, bank sync, or persistent account reconciliation.",
            ]}


def serialize(x: Any) -> Any:
    if isinstance(x, Decimal): return str(x)
    if isinstance(x,date): return x.isoformat()
    if isinstance(x,dict): return {str(k):serialize(v) for k,v in x.items()}
    if isinstance(x,(tuple,list)): return [serialize(v) for v in x]
    return x

def to_json(x: Any) -> str:
    return json.dumps(serialize(x),indent=2,ensure_ascii=False)
