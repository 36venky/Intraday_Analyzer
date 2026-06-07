@echo off
cd /d "%~dp0"
call intraday\Scripts\activate.bat
python Controller\Main.py
pause
