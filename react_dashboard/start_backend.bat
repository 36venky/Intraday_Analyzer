@echo off
cd /d "%~dp0"
cd ..
call intraday\Scripts\activate.bat 2>nul || echo (using system python)
python react_dashboard\backend\main.py
pause
