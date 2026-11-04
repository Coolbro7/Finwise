
import tempfile
import unittest
from pathlib import Path
from storage import BudgetStore

class StorageTests(unittest.TestCase):
    def test_upsert_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            with BudgetStore(Path(d)/"test.sqlite3") as db:
                row={"id":"x","date":"2026-10-01","amount":"10","kind":"expense"}
                db.upsert_transaction(row)
                db.upsert_transaction({**row,"amount":"12"})
                self.assertEqual(len(db.transactions()),1)
                self.assertEqual(db.transactions()[0]["amount"],"12.00")
                db.set_setting("monthly_budget","3000")
                self.assertEqual(db.get_setting("monthly_budget"),"3000")
                db.upsert_confirmed_bill({"id":"bill1","name":"Rent","category":"Rent","due":"2026-10-20","amount":"500"})
                self.assertEqual(db.confirmed_bills()[0]["amount"],"500.00")
if __name__=="__main__":unittest.main()
