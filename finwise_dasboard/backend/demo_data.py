"""Deterministic synthetic transaction history relative to the local calendar."""
from datetime import date,timedelta
from backend.budgeting_engine import add_months,amount


def seed(store):
    today=date.today()
    start=today.replace(day=1)
    categories=[('Groceries','Fresh Market',125),('Food & Dining','Campus Cafe',66),
                ('Transport','MTR',32),('Shopping','Everyday Store',160),
                ('Entertainment','Cinema',110)]
    count=0
    for ago in (3,2,1,0):
        month=add_months(start,-ago)
        next_month=add_months(month,1)
        end=next_month-timedelta(days=1)
        maxday=(today if ago==0 else end).day
        # Assorted expenses: deliberately regular enough to make attractive charts.
        for d in range(1,maxday+1):
            base=categories[(d+ago)%3]
            if d%2==0 or d%5==0:
                name, merchant,price=base
                v=price + (d*7+ago*11)%48
                store.upsert_transaction({'id':f'demo-{month:%Y%m}-{d}-daily',
                    'date':month.replace(day=d).isoformat(),'amount':str(v),
                    'kind':'expense','category':name,'merchant':merchant,
                    'account':'Checking','currency':'HKD','status':'posted'})
                count+=1
            if d%7==3:
                store.upsert_transaction({'id':f'demo-{month:%Y%m}-{d}-dining',
                    'date':month.replace(day=d).isoformat(),'amount':str(145+(d*11)%95),
                    'kind':'expense','category':'Food & Dining','merchant':'Restaurant',
                    'account':'Checking','currency':'HKD','status':'posted'})
                count+=1
            if d in (7,23) and d <= maxday:
                store.upsert_transaction({'id':f'demo-{month:%Y%m}-{d}-shop',
                    'date':month.replace(day=d).isoformat(),'amount':str(220+ago*23),
                    'kind':'expense','category':'Shopping','merchant':'Everyday Store',
                    'account':'Checking','currency':'HKD','status':'posted'})
                count+=1
        if maxday>=3:
            store.upsert_transaction({'id':f'demo-{month:%Y%m}-rent',
                'date':month.replace(day=3).isoformat(),'amount':'1250','kind':'expense',
                'category':'Rent','merchant':'Apartment Rent','account':'Checking',
                'currency':'HKD','status':'posted'})
            count+=1
        if maxday>=2:
            store.upsert_transaction({'id':f'demo-{month:%Y%m}-income',
                'date':month.replace(day=2).isoformat(),'amount':'6800','kind':'income',
                'category':'Salary','merchant':'Part-time Job','account':'Checking',
                'currency':'HKD','status':'posted'})
            count+=1
    store.set_setting('monthly_budget','6200.00')
    store.set_setting('config',{
        'currency':'HKD','lookback_months':3,
        'essential_reserves':{'Utilities':'210.00','Mobile':'100.00'},
        'expected_other_spending':'520.00','safety_buffer':'250.00',
        'spendable_cash':'4200.00','unpaid_cash_obligations':'0.00',
        'cash_buffer':'250.00',
        'category_caps':{'Groceries':'1600.00','Food & Dining':'1200.00',
                         'Transport':'500.00','Shopping':'850.00',
                         'Entertainment':'450.00'}})
    due=today+timedelta(days=9)
    store.upsert_confirmed_bill({'id':'demo-bill-utilities','name':'Utility bill',
         'category':'Utilities','due':due.isoformat(),'amount':'210.00'})
    due2=today+timedelta(days=15)
    store.upsert_confirmed_bill({'id':'demo-bill-mobile','name':'Mobile plan',
         'category':'Mobile','due':due2.isoformat(),'amount':'100.00'})
    store.set_setting('demo_mode',True)
    return count
