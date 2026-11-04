@echo off
cd /d "%~dp0"
py -3 run_dashboard.py --demo
if errorlevel 1 python run_dashboard.py --demo
pause
