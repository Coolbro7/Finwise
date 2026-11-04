
"""Command-line interface for local budgeting. Usage: python cli.py --help"""
import argparse
import json
from datetime import date
from backend.budgeting_engine import analyze,to_json,purchase_check
from backend.storage import BudgetStore

def main():
    p=argparse.ArgumentParser(description="Local personal budgeting engine")
    p.add_argument("--db",default="budget.sqlite3",help="SQLite database path")
    sub=p.add_subparsers(dest="command",required=True)
    a=sub.add_parser("import",help="Import JSON list of transactions")
    a.add_argument("file")
    a=sub.add_parser("set-budget",help="Set monthly spending budget")
    a.add_argument("amount")
    a=sub.add_parser("set-config",help="Set configuration JSON object")
    a.add_argument("file")
    a=sub.add_parser("add-bill",help="Add confirmed one-time future bill JSON")
    a.add_argument("file")
    a=sub.add_parser("analyze",help="Analyze and print JSON")
    a.add_argument("--date",default=date.today().isoformat())
    a=sub.add_parser("purchase",help="Check financial affordability")
    a.add_argument("price")
    a.add_argument("--date",default=date.today().isoformat())
    args=p.parse_args()
    with BudgetStore(args.db) as store:
        if args.command=="import":
            rows=json.loads(open(args.file,encoding="utf-8").read())
            if not isinstance(rows,list): raise ValueError("JSON import must be a list")
            # Validate all records before writing any of them.
            from backend.budgeting_engine import Transaction
            for row in rows: Transaction.parse(row)
            for row in rows: store.upsert_transaction(row)
            print(f"Imported/updated {len(rows)} transactions")
        elif args.command=="set-budget":
            from backend.budgeting_engine import amount
            store.set_setting("monthly_budget",str(amount(args.amount)))
            print("Monthly budget saved")
        elif args.command=="set-config":
            cfg=json.loads(open(args.file,encoding="utf-8").read())
            if not isinstance(cfg,dict): raise ValueError("Config must be a JSON object")
            store.set_setting("config",cfg)
            print("Configuration saved")
        elif args.command=="add-bill":
            store.upsert_confirmed_bill(json.loads(open(args.file,encoding="utf-8").read()))
            print("Confirmed bill saved")
        else:
            budget=store.get_setting("monthly_budget")
            if budget is None: raise ValueError("Set budget first with set-budget")
            cfg=store.get_setting("config",{})
            currency=cfg.get("currency","HKD")
            result=analyze(store.transactions(),as_of=args.date,monthly_budget=budget,
                           currency=currency,confirmed_bills=store.confirmed_bills(currency),
                           essential_reserves=cfg.get("essential_reserves"),
                           expected_other_spending=cfg.get("expected_other_spending",0),
                           safety_buffer=cfg.get("safety_buffer",0),
                           spendable_cash=cfg.get("spendable_cash"),
                           unpaid_cash_obligations=cfg.get("unpaid_cash_obligations",0),
                           cash_buffer=cfg.get("cash_buffer",0),
                           category_caps=cfg.get("category_caps"),
                           lookback_months=cfg.get("lookback_months",3))
            if args.command=="analyze": print(to_json(result))
            else: print(to_json(purchase_check(args.price,result["budget_plan"])))
if __name__=="__main__": main()
