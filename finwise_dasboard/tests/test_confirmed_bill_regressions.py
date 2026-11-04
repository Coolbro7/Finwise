"""Regression tests: previously bills did not change the dashboard's calculations."""
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date, timedelta
import unittest

from backend.budgeting_engine import analyze
from backend.server import Service
from backend.storage import BudgetStore

ROW = {'id':'lunch','date':'2026-11-03','amount':'112',
       'kind':'expense','category':'Food','merchant':'Cafe','currency':'HKD'}
BILL = {'id':'internet','name':'Internet','category':'Utilities',
        'amount':'600','due':'2026-11-20','currency':'HKD'}

def inspect(*, bills=None, reserves=None, spendable_cash=None, unpaid_cash_obligations=0):
    return analyze([ROW], as_of='2026-11-03', monthly_budget='2500',
                   confirmed_bills=bills or [], essential_reserves=reserves,
                   spendable_cash=spendable_cash,
                   unpaid_cash_obligations=unpaid_cash_obligations)

class ConfirmedBillRegressionTests(unittest.TestCase):
    def test_exact_reported_case(self):
        before=inspect()
        self.assertEqual(before['forecast']['projected_month_end'], Decimal('1120.00'))
        self.assertEqual(before['budget_plan']['safe_discretionary_purchase_limit'], Decimal('2388.00'))
        after=inspect(bills=[BILL])
        self.assertEqual(after['forecast']['projected_month_end'], Decimal('1720.00'))
        self.assertEqual(after['forecast']['upcoming_confirmed_total'], Decimal('600.00'))
        self.assertEqual(after['budget_plan']['safe_discretionary_purchase_limit'], Decimal('1788.00'))
        self.assertEqual(after['budget_plan']['auto_confirmed_bill_total'], Decimal('600.00'))

    def test_multiple_bills_same_category_are_added(self):
        extra = {**BILL, 'id':'water', 'name':'Water', 'amount':'200', 'due':'2026-11-21'}
        r=inspect(bills=[BILL,extra])
        self.assertEqual(r['budget_plan']['reserve_total'],Decimal('800.00'))
        self.assertEqual(r['forecast']['projected_month_end'],Decimal('1920.00'))
        self.assertEqual(r['budget_plan']['safe_discretionary_purchase_limit'],Decimal('1588.00'))

    def test_manual_category_reserve_not_counted_twice(self):
        r=inspect(bills=[BILL], reserves={'utilities':'650'})
        self.assertEqual(r['budget_plan']['reserve_total'],Decimal('650.00'))
        self.assertEqual(r['budget_plan']['safe_discretionary_purchase_limit'],Decimal('1738.00'))

    def test_other_category_reserve_stacks(self):
        r=inspect(bills=[BILL],reserves={'Groceries':'200'})
        self.assertEqual(r['budget_plan']['reserve_total'], Decimal('800.00'))

    def test_cash_reserves_confirmed_bills(self):
        r=inspect(bills=[BILL],spendable_cash='1000',unpaid_cash_obligations='100')
        self.assertEqual(r['budget_plan']['cash_headroom'], Decimal('300.00'))
        self.assertEqual(r['budget_plan']['safe_discretionary_purchase_limit'], Decimal('300.00'))

    def test_past_or_next_month_bills_not_counted(self):
        earlier={**BILL,'id':'earlier','due':'2026-11-01'}
        later={**BILL,'id':'later','due':'2026-12-01'}
        r=inspect(bills=[earlier,later])
        self.assertEqual(r['budget_plan']['reserve_total'],Decimal('0.00'))
        self.assertEqual(r['forecast']['projected_month_end'],Decimal('1120.00'))

    def test_baselines_do_not_dilute_confirmed_bill(self):
        # With completed prior-month history, the full confirmed bill must be
        # reflected as an obligation, not only 70% or less of its amount.
        rows=[ROW, {**ROW,'id':'september_food','date':'2026-09-01','amount':'800'}]
        r=analyze(rows,as_of='2026-11-03',monthly_budget='2500',confirmed_bills=[BILL])
        self.assertGreaterEqual(r['forecast']['projected_month_end'],Decimal('712'))
        self.assertEqual(r['budget_plan']['safe_discretionary_purchase_limit'],Decimal('1788.00'))

    def test_saved_bill_updates_real_dashboard_report(self):
        with TemporaryDirectory() as td:
            db=Path(td)/'test.db'
            service=Service(db)
            with BudgetStore(db) as store:
                store.set_setting('monthly_budget','2500')
                # This compares before/after in whichever calendar month the test runs.
                today=date.today()
                tomorrow=today+timedelta(days=1)
                if tomorrow.month!=today.month:
                    return
                store.upsert_transaction({**ROW,'date':today.isoformat()})
            before=service.bootstrap(today.strftime('%Y-%m'))
            with BudgetStore(db) as store:
                store.upsert_confirmed_bill({**BILL, 'due':tomorrow.isoformat()})
            after=service.bootstrap(today.strftime('%Y-%m'))
            self.assertEqual(Decimal(after['analysis']['budget_plan']['safe_discretionary_purchase_limit']),
                             Decimal(before['analysis']['budget_plan']['safe_discretionary_purchase_limit'])-Decimal('600'))
            self.assertEqual(Decimal(after['analysis']['forecast']['projected_month_end']),
                             Decimal(before['analysis']['forecast']['projected_month_end'])+Decimal('600'))

if __name__=='__main__': unittest.main()
