
"""Local SQLite transaction storage and budget configuration.

No bank credentials or external services. SQLite database is local; protect it
with operating-system permissions. This is not encrypted at rest.
"""
import json
import sqlite3
from pathlib import Path
from budgeting_engine import Transaction, amount, day

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS transactions (
  id TEXT PRIMARY KEY, date TEXT NOT NULL, amount TEXT NOT NULL,
  kind TEXT NOT NULL, category TEXT NOT NULL, merchant TEXT NOT NULL,
  account TEXT NOT NULL, status TEXT NOT NULL, currency TEXT NOT NULL,
  transfer_group TEXT NOT NULL DEFAULT '', original_id TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS confirmed_bills (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL,
  due TEXT NOT NULL, amount TEXT NOT NULL, currency TEXT NOT NULL
);
"""

class BudgetStore:
    def __init__(self, path):
        self.path=str(path)
        self.conn=sqlite3.connect(self.path)
        self.conn.executescript(SCHEMA)
    def close(self): self.conn.close()
    def __enter__(self): return self
    def __exit__(self,*args): self.close()
    def upsert_transaction(self,row):
        t=Transaction.parse(row)
        with self.conn:
            self.conn.execute(
                """INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET date=excluded.date, amount=excluded.amount,
                kind=excluded.kind, category=excluded.category, merchant=excluded.merchant,
                account=excluded.account, status=excluded.status, currency=excluded.currency,
                transfer_group=excluded.transfer_group, original_id=excluded.original_id""",
                (t.id,t.date.isoformat(),str(t.amount),t.kind,t.category,t.merchant,
                 t.account,t.status,t.currency,t.transfer_group,t.original_id))
    def delete_transaction(self,tx_id):
        with self.conn:
            self.conn.execute("DELETE FROM transactions WHERE id=?",(tx_id,))
    def transactions(self):
        cur=self.conn.execute("""SELECT id,date,amount,kind,category,merchant,account,
        status,currency,transfer_group,original_id FROM transactions ORDER BY date,id""")
        cols=[x[0] for x in cur.description]
        return [dict(zip(cols,row)) for row in cur.fetchall()]
    def set_setting(self,key,value):
        with self.conn:
            self.conn.execute("""INSERT INTO settings(key,value_json) VALUES (?,?)
                ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json""",
                (key,json.dumps(value)))
    def get_setting(self,key,default=None):
        row=self.conn.execute("SELECT value_json FROM settings WHERE key=?",(key,)).fetchone()
        return json.loads(row[0]) if row else default
    def upsert_confirmed_bill(self,bill):
        for k in ("id","name","category","due","amount"):
            if k not in bill: raise ValueError(f"Missing confirmed bill field {k}")
        due=day(bill["due"]).isoformat()
        v=amount(bill["amount"])
        currency=str(bill.get("currency","HKD")).upper()
        if len(currency)!=3 or not currency.isalpha():
            raise ValueError("Invalid bill currency")
        with self.conn:
            self.conn.execute("""INSERT INTO confirmed_bills VALUES (?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,category=excluded.category,
                due=excluded.due,amount=excluded.amount,currency=excluded.currency""",
                (str(bill["id"]),str(bill["name"]),str(bill["category"]),due,str(v),currency))
    def delete_confirmed_bill(self,bill_id):
        with self.conn:
            cur=self.conn.execute("DELETE FROM confirmed_bills WHERE id=?",(bill_id,))
            return cur.rowcount > 0

    def confirmed_bills(self,currency="HKD"):
        cur=self.conn.execute("SELECT id,name,category,due,amount,currency FROM confirmed_bills WHERE currency=?",(currency,))
        cols=[x[0] for x in cur.description]
        return [dict(zip(cols,row)) for row in cur.fetchall()]
