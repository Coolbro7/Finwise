
import unittest
from datetime import date
from decimal import Decimal
from backend.budgeting_engine import *

def t(i,d,v,kind="expense",category="Food",merchant="Cafe",status="posted",currency="HKD"):
    return {"id":str(i),"date":d,"amount":str(v),"kind":kind,"category":category,
            "merchant":merchant,"status":status,"currency":currency}

class BudgetTests(unittest.TestCase):
    def test_invalid_money(self):
        for v in [None, True, "-1", "NaN", "Infinity", "abc"]:
            with self.assertRaises(ValueError): amount(v)
    def test_cents(self):
        self.assertEqual(amount("2.345"),Decimal("2.35"))
    def test_transfer_not_spending(self):
        tx=load([t(1,"2026-11-01",500,"transfer"),t(2,"2026-11-02",50)])
        self.assertEqual(net_expenses(tx),Decimal("50"))
    def test_refund_reduces_spending(self):
        tx=load([t(1,"2026-11-01",100),t(2,"2026-11-02",25,"refund")])
        self.assertEqual(net_expenses(tx),Decimal("75"))
    def test_pending_not_posted(self):
        tx=load([t(1,"2026-11-01",100,status="pending")])
        self.assertEqual(net_expenses(posted(tx,date(2026,11,1),date(2026,11,30))),Decimal("0"))
    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError): load([t(1,"2026-11-01",10),t(1,"2026-11-02",20)])
    def test_currency_rejected(self):
        with self.assertRaises(ValueError): load([t(1,"2026-11-01",10,currency="USD")])
    def test_recurring_monthly(self):
        tx=load([t(i,f"2026-{i:02d}-05",100,category="Rent",merchant="Landlord") for i in (7,8,9)])
        r=recurring(tx,date(2026,10,1))
        self.assertEqual(len(r),1)
        self.assertEqual(r[0]["cadence"],"monthly")
        self.assertEqual(r[0]["next_expected"],date(2026,10,5))
        self.assertFalse(r[0]["confirmed"])
    def test_no_recurring_two(self):
        tx=load([t(1,"2026-08-01",100),t(2,"2026-09-01",100)])
        self.assertEqual(recurring(tx,date(2026,10,1)),[])
    def test_history_completed_month(self):
        tx=load([t(1,"2026-09-01",100),t(2,"2026-10-01",500)])
        h=history(tx,date(2026,10,15),1)
        self.assertEqual(h["Food"]["average_observed_month"],Decimal("100"))
    def test_forecast_no_negative_below_actual(self):
        tx=load([t(1,"2026-10-01",2000)])
        f=forecast(tx,date(2026,10,15),Decimal("3000"),{})
        self.assertGreaterEqual(f["projected_month_end"],Decimal("2000"))
    def test_confirmed_bills_in_forecast(self):
        f=forecast([],date(2026,10,15),Decimal("3000"),{},
                   [{"name":"Rent","category":"Rent","amount":"800","due":"2026-10-25"}])
        self.assertEqual(f["forecast_remaining_by_category"]["Rent"],Decimal("800"))
    def test_budget_and_cash_both_bind(self):
        tx=load([t(1,"2026-10-01",2000)])
        p=plan(tx,date(2026,10,15),Decimal("3000"),{"Rent":"500"},
               buffer="100",spendable_cash="700",unpaid_cash_obligations="300",cash_buffer="100")
        self.assertEqual(p["budget_headroom"],Decimal("400"))
        self.assertEqual(p["cash_headroom"],Decimal("300"))
        self.assertEqual(p["safe_discretionary_purchase_limit"],Decimal("300"))
    def test_negative_budget_headroom_visible(self):
        p=plan([],date(2026,10,15),Decimal("1000"),{"Rent":"1200"})
        self.assertEqual(p["budget_shortfall"],Decimal("200"))
        self.assertEqual(p["safe_discretionary_purchase_limit"],Decimal("0"))
    def test_category_allocations_sum(self):
        baselines={"Food":{"average_observed_month":Decimal("200")},
                   "Transport":{"average_observed_month":Decimal("100")}}
        p=plan([],date(2026,10,15),Decimal("900"),baselines=baselines)
        d=p["dynamic_category_allowances"]
        self.assertEqual(sum((v["dynamic_remaining"] for v in d.values()),Decimal("0")),Decimal("900"))
    def test_purchase_guard(self):
        p=plan([],date(2026,10,15),Decimal("100"),spendable_cash="50")
        self.assertFalse(purchase_check("60",p)["affordable"])
    def test_end_of_month_daily_zero(self):
        p=plan([],date(2026,10,31),Decimal("100"))
        self.assertEqual(p["safe_daily_allowance"],Decimal("0"))
    def test_anomaly(self):
        tx=load([t(i,f"2026-09-{i:02d}",10) for i in range(1,7)]
                +[t("big","2026-10-01",100)])
        self.assertEqual(len(anomalies(tx,date(2026,10,1))),1)
    def test_end_to_end(self):
        a=analyze([t(1,"2026-10-01",100)],as_of="2026-10-15",monthly_budget="3000")
        self.assertIn("budget_plan",a)
        self.assertIn("recurring_candidates",a)
        self.assertIn("forecast",a)
        self.assertIn("weekday_spending_patterns",a)
        self.assertIn("unusual_transactions_today",a)
        self.assertIn('"currency": "HKD"',to_json(a))
if __name__=="__main__": unittest.main()
