"""Run the personal budgeting dashboard locally: python run_dashboard.py --demo"""
import argparse
import threading
import webbrowser
from pathlib import Path
from backend.server import make_server


def main():
    p=argparse.ArgumentParser(description='Local budgeting dashboard (Python stdlib only)')
    p.add_argument('--db',default='data/budget.sqlite3',help='SQLite path')
    p.add_argument('--port',type=int,default=8000)
    p.add_argument('--demo',action='store_true',help='Populate an empty database with synthetic demo transactions')
    p.add_argument('--no-browser',action='store_true',help='Do not open browser automatically')
    args=p.parse_args()
    db=Path(args.db).expanduser()
    if not db.is_absolute(): db=Path(__file__).resolve().parent/db
    server=make_server(db,port=args.port)
    if args.demo:
        try:
            server.service.seed_demo()
            print('Loaded synthetic demonstration data into the empty database.')
        except ValueError as exc:
            print('Demo seed skipped:',exc)
    url=f'http://127.0.0.1:{server.server_address[1]}'
    print('Your local dashboard is running at',url)
    print('Using database:',db)
    print('Press Ctrl+C to stop. Budgeting works offline; Live shopping requires internet plus Tavily and OpenRouter API keys.')
    if not args.no_browser:
        threading.Timer(0.8,lambda:webbrowser.open(url)).start()
    try: server.serve_forever()
    except KeyboardInterrupt: print('\nStopped dashboard.')
    finally: server.server_close()

if __name__=='__main__': main()
