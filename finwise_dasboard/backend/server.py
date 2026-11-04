"""REST API and local static HTTP server for the budgeting prototype.

Python 3.10+ standard library only. Binds only to 127.0.0.1 by default.
Core financial calculations remain in budgeting_engine.py.
"""
from __future__ import annotations
import calendar
import json
import os
from datetime import date, timedelta
from decimal import Decimal
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import threading
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import uuid4

from backend.budgeting_engine import (Transaction, amount, analyze, breakdown, day,
                              load, month_range, posted, purchase_check, serialize)
from backend.storage import BudgetStore
from backend.shopping_ai import (config_status, shopping_policy, recommend as shopping_recommend,
                         ShoppingInputError, ShoppingUnavailable)

ROOT = Path(__file__).resolve().parent.parent
ASSETS = {
    '/': ('Frontend/index.html', 'text/html; charset=utf-8'),
    '/index.html': ('Frontend/index.html', 'text/html; charset=utf-8'),
    '/style.css': ('Frontend/style.css', 'text/css; charset=utf-8'),
    '/app.js': ('Frontend/app.js', 'application/javascript; charset=utf-8'),
    '/shopping.js': ('Frontend/shopping.js', 'application/javascript; charset=utf-8'),
}
CONFIG_DEFAULT = {
    'currency': 'HKD', 'lookback_months': 3,
    'essential_reserves': {}, 'expected_other_spending': '0.00',
    'safety_buffer': '0.00', 'spendable_cash': None,
    'unpaid_cash_obligations': '0.00', 'cash_buffer': '0.00',
    'category_caps': {},
}

class InputError(ValueError):
    """Client-safe validation error."""


def validated_month(value):
    if not isinstance(value, str) or len(value) != 7 or value[4] != '-':
        raise InputError('Month must be YYYY-MM')
    try:
        chosen = date.fromisoformat(value+'-01')
    except ValueError as exc:
        raise InputError('Invalid month') from exc
    if chosen > date.today().replace(day=1):
        raise InputError('Future months are not supported by this demo')
    return chosen


def clean_mapping(value, label):
    if not isinstance(value, dict):
        raise InputError(f'{label} must be a collection of name/amount pairs')
    result = {}
    for name, v in value.items():
        if not isinstance(name, str) or not name.strip() or len(name)>80:
            raise InputError(f'Invalid label in {label}')
        if name.strip() in result:
            raise InputError(f'Duplicate label in {label}')
        result[name.strip()] = str(amount(v))
    return result


def validate_settings(body):
    if not isinstance(body, dict):
        raise InputError('Expected settings object')
    budget = str(amount(body.get('monthly_budget')))
    cfg = body.get('config')
    if not isinstance(cfg,dict):
        raise InputError('Missing configuration')
    if cfg.get('currency', 'HKD') != 'HKD':
        raise InputError('This prototype supports HKD only')
    try:
        lookback = int(cfg.get('lookback_months',3))
    except (TypeError,ValueError) as exc:
        raise InputError('Invalid lookback months') from exc
    if not (1 <= lookback <= 24):
        raise InputError('Lookback months must be between 1 and 24')
    result = {'currency':'HKD','lookback_months': lookback}
    result['essential_reserves'] = clean_mapping(cfg.get('essential_reserves',{}), 'essential reserves')
    result['category_caps'] = clean_mapping(cfg.get('category_caps',{}), 'category caps')
    for key in ('expected_other_spending','safety_buffer','unpaid_cash_obligations','cash_buffer'):
        result[key] = str(amount(cfg.get(key,0)))
    cash = cfg.get('spendable_cash')
    result['spendable_cash'] = None if cash is None or cash=='' else str(amount(cash))
    return budget, result

class Service:
    """Per-app service, with one SQLite connection per operation."""
    def __init__(self,db_path=None):
        self.db = Path(db_path or ROOT/'data'/'budget.sqlite3').resolve()
        self.db.parent.mkdir(parents=True,exist_ok=True)
        self._import_lock=threading.Lock()
        with BudgetStore(self.db):
            pass

    def _settings(self,store):
        cfg = dict(CONFIG_DEFAULT)
        cfg.update(store.get_setting('config',{}) or {})
        return {'monthly_budget': store.get_setting('monthly_budget','0.00'), 'config':cfg}

    def _analysis(self, store, month):
        m = validated_month(month)
        now = date.today()
        as_of = now if m.year == now.year and m.month == now.month else month_range(m)[1]
        settings = self._settings(store)
        cfg=settings['config']
        rows=store.transactions()
        analysis=analyze(rows,as_of=as_of.isoformat(),monthly_budget=settings['monthly_budget'],
                         currency='HKD',lookback_months=cfg['lookback_months'],
                         confirmed_bills=store.confirmed_bills('HKD'),
                         essential_reserves=cfg['essential_reserves'],
                         expected_other_spending=cfg['expected_other_spending'],
                         safety_buffer=cfg['safety_buffer'],spendable_cash=cfg['spendable_cash'],
                         unpaid_cash_obligations=cfg['unpaid_cash_obligations'],
                         cash_buffer=cfg['cash_buffer'],category_caps=cfg['category_caps'])
        start,end=month_range(m)
        month_rows=sorted((row for row in rows if start.isoformat()<=row['date']<=end.isoformat()),
                          key=lambda row:(row['date'],row['id']),reverse=True)
        tx=load(rows,'HKD')
        prior=month_range(start-timedelta(days=1))
        prev=breakdown(tx,*prior)
        actual_daily=analysis['current_month']['daily_net']
        days=calendar.monthrange(m.year,m.month)[1]
        chart=[]
        cumulative=Decimal('0')
        for i in range(1,days+1):
            d=date(m.year,m.month,i)
            today_row=d<=as_of
            v=Decimal(str(actual_daily.get(d.isoformat(),'0'))) if today_row else Decimal('0')
            if today_row: cumulative+=v
            chart.append({'day':i,'date':d.isoformat(),
                          'daily_net':str(v) if today_row else None,
                          'cumulative_net':str(cumulative) if today_row else None})
        return {
            'as_of':as_of.isoformat(), 'month':month, 'settings':settings,
            'analysis':analysis,'transactions':month_rows,
            'bills':sorted(store.confirmed_bills('HKD'),key=lambda b:b['due']),
            'comparison': {'previous_month_spending':prev['net_spending'],
                           'previous_month_income':prev['income']},
            'chart':chart, 'demo':bool(store.get_setting('demo_mode',False)),
        }

    def bootstrap(self,month):
        with BudgetStore(self.db) as store:
            return serialize(self._analysis(store,month))

    def settings(self,body=None):
        with BudgetStore(self.db) as store:
            if body is not None:
                budget,cfg=validate_settings(body)
                # Both changes are transactional, avoiding half-written settings.
                with store.conn:
                    store.conn.execute("""INSERT INTO settings(key,value_json) VALUES (?,?)
                        ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json""",
                        ('monthly_budget',json.dumps(budget)))
                    store.conn.execute("""INSERT INTO settings(key,value_json) VALUES (?,?)
                        ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json""",
                        ('config',json.dumps(cfg)))
            return self._settings(store)

    def import_through_cli(self,row):
        """Create the requested temporary new transaction.json, invoke original CLI, remove it."""
        tx=Transaction.parse(row)
        if tx.currency != 'HKD':
            raise InputError('This prototype supports HKD only')
        temp = self.db.parent/'new transaction.json'
        with self._import_lock:
            try:
                # Recover safely from previous interrupted import.
                temp.unlink(missing_ok=True)
                with temp.open('x',encoding='utf-8') as f:
                    json.dump([serialize(tx.__dict__)],f,indent=2)
                result = subprocess.run(
                    [
                        sys.executable,
                        '-m',
                        'backend.cli',
                        '--db',
                        str(self.db),
                        'import',
                        str(temp)
                    ],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    timeout=20
                    )
                if result.returncode != 0:
                    raise RuntimeError('CLI import failed: '+result.stderr[-400:])
            finally:
                temp.unlink(missing_ok=True)
        return serialize(tx.__dict__)

    def create_tx(self,body):
        if not isinstance(body,dict): raise InputError('Expected transaction object')
        row={**body,'id':'tx-'+uuid4().hex[:16],'currency':'HKD'}
        return self.import_through_cli(row)

    def edit_tx(self,tx_id,body):
        if not isinstance(body,dict): raise InputError('Expected transaction object')
        with BudgetStore(self.db) as store:
            existing=next((x for x in store.transactions() if x['id']==tx_id),None)
            if existing is None: raise InputError('Transaction not found')
        # Keep all original fields when form submits a partial update.
        row={**existing,**body,'id':tx_id,'currency':'HKD'}
        return self.import_through_cli(row)

    def delete_tx(self,tx_id):
        with BudgetStore(self.db) as store:
            if not any(x['id']==tx_id for x in store.transactions()):
                raise InputError('Transaction not found')
            store.delete_transaction(tx_id)
        return {'deleted':tx_id}

    def bills(self):
        with BudgetStore(self.db) as store:
            return store.confirmed_bills('HKD')

    def save_bill(self,body,bill_id=None):
        if not isinstance(body,dict): raise InputError('Expected bill object')
        with BudgetStore(self.db) as store:
            if bill_id and not any(x['id']==bill_id for x in store.confirmed_bills('HKD')):
                raise InputError('Bill not found')
            b={**body,'id':bill_id or 'bill-'+uuid4().hex[:12],'currency':'HKD'}
            store.upsert_confirmed_bill(b)
            return next(x for x in store.confirmed_bills('HKD') if x['id']==b['id'])

    def delete_bill(self,bill_id):
        with BudgetStore(self.db) as store:
            if not store.delete_confirmed_bill(bill_id): raise InputError('Bill not found')
        return {'deleted':bill_id}

    def purchase(self,month,price):
        with BudgetStore(self.db) as store:
            a=self._analysis(store,month)['analysis']
            return serialize(purchase_check(price,a['budget_plan']))

    def shopping_policy(self):
        # Shopping is a current-date decision, independent of the displayed history month.
        with BudgetStore(self.db) as store:
            financial = self._analysis(store, date.today().strftime('%Y-%m'))['analysis']
        return shopping_policy(financial)

    def shopping_recommend(self, body):
        if not isinstance(body, dict):
            raise InputError('Expected a shopping request object')
        # Use the current financial state; do not let a caller select an old month
        # with a larger discretionary allowance.
        with BudgetStore(self.db) as store:
            financial = self._analysis(store, date.today().strftime('%Y-%m'))['analysis']
        return shopping_recommend(body, financial)

    def seed_demo(self):
        from backend.demo_data import seed
        with BudgetStore(self.db) as store:
            if store.transactions():
                raise InputError('Demo data can only be loaded into an empty database')
            seed(store)
        return {'seeded':True}

class Handler(BaseHTTPRequestHandler):
    server_version='BudgetLocal/1.0'
    def log_message(self, fmt, *args):
        print('[local dashboard]', fmt % args)

    @property
    def service(self): return self.server.service

    def json_response(self,status,payload):
        raw=json.dumps(serialize(payload),ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        self.wfile.write(raw)

    def request_body(self):
        if 'application/json' not in self.headers.get('Content-Type',''):
            raise InputError('Content-Type must be application/json')
        try:
            n=int(self.headers.get('Content-Length',0))
            if n<1 or n>131072: raise InputError('Request body must be 1..131072 bytes')
            return json.loads(self.rfile.read(n))
        except (ValueError,json.JSONDecodeError) as exc:
            raise InputError('Invalid JSON body') from exc

    def path_parts(self):
        return urlsplit(self.path)

    def dispatch(self):
        info=self.path_parts()
        path=info.path
        if self.command=='GET' and path in ASSETS:
            file_name,content_type=ASSETS[path]
            raw=(ROOT/file_name).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers()
            self.wfile.write(raw)
            return
        if not path.startswith('/api/'):
            return self.json_response(404,{'error':'Not found'})
        month=parse_qs(info.query).get('month',[date.today().strftime('%Y-%m')])[0]
        body=self.request_body() if self.command in ('POST','PUT','PATCH') else None
        if path=='/api/shopping/status' and self.command=='GET':
            result=config_status()
        elif path=='/api/shopping/policy' and self.command=='GET':
            result=self.service.shopping_policy()
        elif path=='/api/shopping/recommend' and self.command=='POST':
            result=self.service.shopping_recommend(body)
        elif path=='/api/bootstrap' and self.command=='GET':
            result=self.service.bootstrap(month)
        elif path=='/api/settings' and self.command=='PUT':
            result=self.service.settings(body)
        elif path=='/api/transactions' and self.command=='POST':
            result=self.service.create_tx(body)
        elif path.startswith('/api/transactions/') and self.command in ('PUT','DELETE'):
            tx_id=unquote(path[len('/api/transactions/'):])
            if not tx_id or '/' in tx_id: raise InputError('Invalid transaction ID')
            result=self.service.edit_tx(tx_id,body) if self.command=='PUT' else self.service.delete_tx(tx_id)
        elif path=='/api/bills' and self.command=='POST':
            result=self.service.save_bill(body)
        elif path.startswith('/api/bills/') and self.command in ('PUT','DELETE'):
            bill_id=unquote(path[len('/api/bills/'):])
            if not bill_id or '/' in bill_id: raise InputError('Invalid bill ID')
            result=self.service.save_bill(body,bill_id) if self.command=='PUT' else self.service.delete_bill(bill_id)
        elif path=='/api/purchase' and self.command=='POST':
            result=self.service.purchase(body.get('month',date.today().strftime('%Y-%m')),body.get('price'))
        elif path=='/api/demo/seed' and self.command=='POST':
            result=self.service.seed_demo()
        else:
            return self.json_response(404,{'error':'Unknown API endpoint'})
        self.json_response(200,result)

    def do_GET(self): self._handle()
    def do_POST(self): self._handle()
    def do_PUT(self): self._handle()
    def do_DELETE(self): self._handle()
    def _handle(self):
        try:
            self.dispatch()
        except ShoppingUnavailable as exc:
            self.json_response(503,{'error':str(exc)})
        except (ShoppingInputError,InputError,ValueError,TypeError,KeyError) as exc:
            self.json_response(400,{'error':str(exc)})
        except subprocess.TimeoutExpired:
            self.json_response(504,{'error':'The CLI import timed out'})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            print('[local dashboard] INTERNAL ERROR',repr(exc),file=sys.stderr)
            self.json_response(500,{'error':'Internal server error; see the terminal for details'})


def make_server(db_path=None,host='127.0.0.1',port=8000):
    httpd=ThreadingHTTPServer((host,port),Handler)
    httpd.service=Service(db_path)
    httpd.daemon_threads=True
    return httpd
