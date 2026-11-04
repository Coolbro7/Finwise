"""Offline tests for Hong Kong-compatible Tavily + OpenRouter workflow."""
import json
import os
import threading
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from shopping_ai import (
    shopping_policy, validate_request, normalize_response, recommend,
    call_openrouter, search_tavily, config_status, ShoppingInputError,
    ShoppingUnavailable, extract_json,
)
from server import make_server
from storage import BudgetStore


def sample_analysis():
    return {'as_of': date(2026, 11, 15),
            'budget_plan': {'safe_discretionary_purchase_limit': Decimal('450'),
                            'safe_daily_allowance': Decimal('50'),
                            'spent': Decimal('1300'), 'budget': Decimal('2500'),
                            'cash_headroom': Decimal('600'),
                            'auto_confirmed_bill_total': Decimal('600'),
                            'remaining_days_after_today': 15},
            'forecast': {'projected_month_end': Decimal('2300')}}


SOURCES = [
    {'title': 'Graffiti shirt HK$95', 'url': 'https://example.org/tee',
     'content': 'Graffiti t-shirt HK$95 online sale, shipping extra', 'kind': 'online'},
    {'title': 'Hung Hom graphic apparel shop', 'url': 'https://example.org/store',
     'content': 'Graphic t-shirt store in Hung Hom, Hong Kong', 'kind': 'nearby'}]


class ShoppingUnitTests(unittest.TestCase):
    def test_price_policy(self):
        p = shopping_policy(sample_analysis())
        self.assertEqual(p['maximum_total_purchase_hkd'], '150.00')
        self.assertEqual(p['forecast_headroom_hkd'], '200.00')
        self.assertTrue(p['cash_verified'])

    def test_price_policy_not_over_safe(self):
        a=sample_analysis()
        a['budget_plan']['safe_discretionary_purchase_limit'] = Decimal('25')
        self.assertEqual(shopping_policy(a)['maximum_total_purchase_hkd'],'25.00')

    def test_price_policy_forecast_overspend(self):
        a=sample_analysis()
        a['forecast']['projected_month_end']=Decimal('2700')
        self.assertEqual(shopping_policy(a)['maximum_total_purchase_hkd'],'0')

    def test_price_policy_final_day(self):
        a=sample_analysis()
        a['budget_plan']['remaining_days_after_today']=0
        a['budget_plan']['safe_daily_allowance']=Decimal('0')
        self.assertEqual(shopping_policy(a)['maximum_total_purchase_hkd'],'160.00')

    def test_validate_inputs(self):
        with self.assertRaises(ShoppingInputError):
            validate_request({'query':'x','mode':'online'})
        with self.assertRaises(ShoppingInputError):
            validate_request({'query':'Nice shirt','mode':'nearby'})
        with self.assertRaises(ShoppingInputError):
            validate_request({'query':'Nice shirt','mode':'online','location':{'latitude':91,'longitude':0}})
        v=validate_request({'query':'Graffiti shirt','mode':'both','location':{'latitude':22.30134,'longitude':114.17131}})
        self.assertEqual(v['coordinates']['longitude'],114.171)

    def test_extract_json(self):
        self.assertEqual(extract_json('```json\n{"products":[]}\n```')['products'],[])

    def test_mock_tavily_contract(self):
        def transport(request,payload):
            self.assertEqual(request.get_method(),'POST')
            self.assertEqual(request.full_url,'https://api.tavily.com/search')
            self.assertEqual(payload['search_depth'],'basic')
            self.assertNotIn('TAVILY_API_KEY',json.dumps(payload))
            self.assertTrue(request.get_header('Authorization').startswith('Bearer '))
            return {'results':[{'title':'Graffiti shirt HK$95',
                                'url':'https://example.org/tee','content':'HK$95 shirt'}]}
        with patch.dict(os.environ,{'TAVILY_API_KEY':'fake-key'}):
            results=search_tavily('graphic tee',transport=transport)
        self.assertEqual(results[0]['url'],'https://example.org/tee')
        self.assertEqual(results[0]['content'],'HK$95 shirt')

    def test_mock_openrouter_contract(self):
        def transport(request,payload):
            self.assertEqual(request.full_url,'https://openrouter.ai/api/v1/chat/completions')
            self.assertEqual(payload['model'],'openrouter/free')
            self.assertNotIn('OPENROUTER_API_KEY',json.dumps(payload))
            self.assertEqual(payload['messages'][0]['role'],'system')
            self.assertTrue(request.get_header('Authorization').startswith('Bearer '))
            return {'model':'openrouter/free',
                    'choices':[{'message':{'content':'{"products":[],"stores":[]}'}}]}
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'fake-key','OPENROUTER_MODEL':'openrouter/free'}):
            r=call_openrouter({'product_description':'shirt','source_results':SOURCES},transport=transport)
        self.assertEqual(extract_json(r['text']),{'products':[],'stores':[]})

    def test_price_validation_link_and_evidence(self):
        payload={'summary':'Two products', 'products':[
            {'name':'Sourced and priced','price_hkd':95,'shipping_hkd':0,'store':'Example','url':'https://example.org/tee'},
            {'name':'Invented link','price_hkd':95,'store':'Fake','url':'https://fake-site.com/tee'},
            {'name':'Invented price','price_hkd':125,'store':'Example','url':'https://example.org/tee'},
            {'name':'Unpriced','price_hkd':'unknown','store':'Example','url':'https://example.org/tee'},
            {'name':'Over the cap','price_hkd':200,'store':'Example','url':'https://example.org/tee'}],
            'stores':[{'name':'Hong Kong store','area':'Hung Hom','url':'https://example.org/store'}]}
        out=normalize_response({'text':json.dumps(payload)},shopping_policy(sample_analysis()),SOURCES)
        self.assertEqual([x['name'] for x in out['products']],['Sourced and priced'])
        self.assertEqual(out['products'][0]['total_hkd'],'95.00')
        self.assertEqual(len(out['stores']),1)
        self.assertEqual(len(out['excluded']),4)

    def test_live_search_and_llm_mock(self):
        searches=[]; models=[]
        def fake_search(query):
            searches.append(query)
            return SOURCES if len(searches)==1 else SOURCES[1:]
        def fake_llm(context):
            models.append(context)
            return {'text':json.dumps({'summary':'One candidate',
                'products':[{'name':'Graffiti shirt','price_hkd':95,'shipping_hkd':0,
                             'store':'Example','url':'https://example.org/tee'}],
                'stores':[{'name':'Hung Hom shop','area':'Hung Hom','url':'https://example.org/store'}]}),
                'model':'openrouter/free'}
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'a','TAVILY_API_KEY':'b','SHOPPING_DEMO':'0'}):
            result=recommend({'query':'graffiti print shirt','mode':'both',
                              'location':{'label':'Hung Hom'}},sample_analysis(),
                             search_call=fake_search,model_call=fake_llm)
        self.assertEqual(result['status'],'ok')
        self.assertEqual(len(searches),2)
        self.assertEqual(len(models),1)
        self.assertEqual(models[0]['maximum_total_purchase_hkd'],'150.00')
        self.assertNotIn('full_transaction_history',str(models[0]))
        self.assertEqual(result['products'][0]['total_hkd'],'95.00')
        self.assertEqual(result['stores'][0]['name'],'Hung Hom shop')

    def test_model_rate_limit_returns_search_links(self):
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'a','TAVILY_API_KEY':'b','SHOPPING_DEMO':'0'}):
            result=recommend({'query':'graffiti shirt','mode':'online'},sample_analysis(),
                             search_call=lambda _:SOURCES[:1],
                             model_call=lambda _: (_ for _ in ()).throw(ShoppingUnavailable('LLM quota')))
        self.assertEqual(result['status'],'source_only')
        self.assertEqual(result['sources'][0]['url'],'https://example.org/tee')

    def test_missing_keys_graceful(self):
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'','TAVILY_API_KEY':'','SHOPPING_DEMO':'0'}):
            with self.assertRaises(ShoppingUnavailable):
                recommend({'query':'graffiti shirt','mode':'online'},sample_analysis())

    def test_wait_no_api_call(self):
        a=sample_analysis();a['forecast']['projected_month_end']=Decimal('2700')
        result=recommend({'query':'graffiti shirt','mode':'online'},a,
                         search_call=lambda _:self.fail('should not search'))
        self.assertEqual(result['status'],'wait')


class ShoppingApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.db=Path(self.temp.name)/'shopping.sqlite3'
        with BudgetStore(self.db) as store:
            store.set_setting('monthly_budget','2500')
            store.set_setting('config',{'currency':'HKD','lookback_months':3,
                    'essential_reserves':{},'expected_other_spending':'0',
                    'safety_buffer':'0','spendable_cash':None,
                    'unpaid_cash_obligations':'0','cash_buffer':'0','category_caps':{}})
        self.srv=make_server(self.db,port=0)
        self.thread=threading.Thread(target=self.srv.serve_forever,daemon=True)
        self.thread.start()
        self.base='http://127.0.0.1:'+str(self.srv.server_address[1])

    def tearDown(self):
        self.srv.shutdown();self.thread.join(timeout=3);self.srv.server_close();self.temp.cleanup()

    def fetch(self,path,body=None):
        request=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,
                        headers={'Content-Type':'application/json'} if body is not None else {},
                        method='POST' if body is not None else 'GET')
        with urlopen(request,timeout=5) as r:
            return json.load(r)

    def test_policy_get(self):
        r=self.fetch('/api/shopping/policy')
        self.assertIn('maximum_total_purchase_hkd',r)

    def test_private_key_status(self):
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'private','TAVILY_API_KEY':'private2','SHOPPING_DEMO':'0'}):
            status=self.fetch('/api/shopping/status')
        self.assertTrue(status['configured'])
        self.assertNotIn('private',json.dumps(status))
        self.assertEqual(status['provider'],'OpenRouter + Tavily')

    def test_demo_route_and_assets(self):
        with patch.dict(os.environ,{'SHOPPING_DEMO':'1'}):
            out=self.fetch('/api/shopping/recommend',{'query':'graffiti print t-shirt','mode':'online'})
        self.assertEqual(out['status'],'demo')
        self.assertTrue(out['products'])
        for filename in ('/shopping.js','/style.css','/'):
            with urlopen(self.base+filename,timeout=5) as response:
                self.assertEqual(response.status,200)

    def test_confirmed_bill_reduces_shopping_cap(self):
        today=date.today()
        if (today+timedelta(days=1)).month != today.month:
            self.skipTest('No future bill date remaining in month')
        baseline=Decimal(self.fetch('/api/shopping/policy')['maximum_total_purchase_hkd'])
        with BudgetStore(self.db) as store:
            store.upsert_confirmed_bill({'id':'test-bill','name':'Upcoming payment',
                'category':'Utilities','due':(today+timedelta(days=1)).isoformat(),
                'amount':'600.00','currency':'HKD'})
        updated=Decimal(self.fetch('/api/shopping/policy')['maximum_total_purchase_hkd'])
        self.assertLess(updated,baseline)

    def test_http_validation(self):
        with self.assertRaises(HTTPError) as exc:
            self.fetch('/api/shopping/recommend',{'query':'x','mode':'online'})
        self.assertEqual(exc.exception.code,400)

    def test_http_missing_keys(self):
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'','TAVILY_API_KEY':'','SHOPPING_DEMO':'0'}):
            with self.assertRaises(HTTPError) as exc:
                self.fetch('/api/shopping/recommend',{'query':'graffiti shirt','mode':'online'})
        self.assertEqual(exc.exception.code,503)

if __name__=='__main__': unittest.main()
