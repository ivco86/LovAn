@echo off
REM Flask AI Gallery - Auto-start with browser
title Flask AI Gallery

REM Change to script directory
cd /d "%~dp0"

REM Start Flask in background (no window)
start /B py app.py

REM Wait 3 seconds for Flask to start
echo Waiting for Flask to start...
timeout /t 3 /nobreak >nul

REM Open browser
echo Opening browser...
start http://localhost:5000

REM Keep this window minimized
echo Flask is running in background
echo Close this window to stop Flask
pause >nul

REM When window closes, kill Flask
taskkill /F /IM py.exe >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1
