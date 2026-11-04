"""Integration tests of the real local browser-facing REST API."""
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import json
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from server import make_server

class DashboardApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=TemporaryDirectory()
        cls.db=Path(cls.tmp.name)/'api_test.sqlite3'
        cls.httpd=make_server(cls.db,port=0)
        cls.base=f'http://127.0.0.1:{cls.httpd.server_address[1]}'
        cls.thread=Thread(target=cls.httpd.serve_forever,daemon=True)
        cls.thread.start()
        cls.month=date.today().strftime('%Y-%m')
        cls.today=date.today().isoformat()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown();cls.httpd.server_close()
        cls.thread.join(timeout=2);cls.tmp.cleanup()

    def send(self,path,method='GET',payload=None,expected=200):
        data=json.dumps(payload).encode() if payload is not None else None
        req=Request(self.base+path,data=data,method=method,headers={'Content-Type':'application/json'} if data is not None else {})
        try:
            with urlopen(req,timeout=10) as r:
                status=r.status;content=r.read()
        except HTTPError as exc:
            status=exc.code;content=exc.read()
        self.assertEqual(status,expected,(path,content[:300]))
        return json.loads(content) if path.startswith('/api/') else content.decode()

    def test_01_website_and_bootstrap(self):
        self.assertIn('finwise',self.send('/'))
        self.assertIn('function',self.send('/app.js'))
        d=self.send(f'/api/bootstrap?month={self.month}')
        self.assertIn('chart',d)
        self.assertEqual(d['analysis']['current_month']['net_spending'],'0.00')

    def test_02_settings(self):
        settings={
            'monthly_budget':'4000.00',
            'config':{
                'currency':'HKD','lookback_months':3,
                'essential_reserves':{'Utilities':'120'},'category_caps':{'Food':'850'},
                'spendable_cash':'900','unpaid_cash_obligations':'100',
                'cash_buffer':'50','expected_other_spending':'200','safety_buffer':'150',
            }
        }
        saved=self.send('/api/settings','PUT',settings)
        self.assertEqual(saved['monthly_budget'],'4000.00')
        self.assertEqual(saved['config']['essential_reserves']['Utilities'],'120.00')
        d=self.send(f'/api/bootstrap?month={self.month}')
        self.assertEqual(d['analysis']['budget_plan']['safe_discretionary_purchase_limit'],'750.00')
        self.send('/api/settings','PUT',{'monthly_budget':'-10','config':settings['config']},400)
        self.assertEqual(self.send(f'/api/bootstrap?month={self.month}')['settings']['monthly_budget'],'4000.00')

    def test_03_transactions_crud_cli_tempfile(self):
        entry={'date':self.today,'amount':'32.50','kind':'expense',
               'category':'Food','merchant':'Campus Canteen','status':'posted','account':'Checking'}
        created=self.send('/api/transactions','POST',entry)
        tid=created['id']
        self.assertFalse((self.db.parent/'new transaction.json').exists())
        self.assertEqual(self.send(f'/api/bootstrap?month={self.month}')['analysis']['current_month']['net_spending'],'32.50')
        self.send(f'/api/transactions/{tid}','PUT',{'amount':'43.25'})
        d=self.send(f'/api/bootstrap?month={self.month}')
        self.assertEqual(d['analysis']['current_month']['net_spending'],'43.25')
        self.assertEqual(len(d['transactions']),1)
        self.assertFalse((self.db.parent/'new transaction.json').exists())
        self.send(f'/api/transactions/{tid}','DELETE')
        self.assertFalse((self.db.parent/'new transaction.json').exists())
        self.assertEqual(self.send(f'/api/bootstrap?month={self.month}')['analysis']['current_month']['net_spending'],'0.00')

    def test_04_bill_crud(self):
        bill={'name':'Internet','category':'Utilities','due':(date.today()+timedelta(days=10)).isoformat(),'amount':'120'}
        created=self.send('/api/bills','POST',bill)
        bid=created['id']
        d=self.send(f'/api/bootstrap?month={self.month}')
        self.assertIn(bid,[x['id'] for x in d['bills']])
        edited=self.send(f'/api/bills/{bid}','PUT',{'name':'Internet and phone','category':'Utilities','due':bill['due'],'amount':'130'})
        self.assertEqual(edited['amount'],'130.00')
        self.send(f'/api/bills/{bid}','DELETE')
        self.assertFalse(self.send(f'/api/bootstrap?month={self.month}')['bills'])

    def test_05_affordability_and_validation(self):
        response=self.send('/api/purchase','POST',{'month':self.month,'price':'100'})
        self.assertTrue(response['affordable'])
        self.send('/api/purchase','POST',{'month':self.month,'price':'-50'},400)
        self.send('/api/transactions','POST',{'date':self.today,'amount':'-4','kind':'expense'},400)
        self.send('/api/bootstrap?month=2099-01',expected=400)
        self.send('/api/settings','PUT',{'monthly_budget':'2000','config':{'lookback_months':0}},400)

if __name__=='__main__':unittest.main()
