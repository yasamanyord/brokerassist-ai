@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 or newer is required. Install it, add it to PATH, then retry.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe (
  python -m venv .venv
  if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
set BROKERASSIST_MODE=offline
echo Open http://127.0.0.1:8000 in your browser.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
goto :eof
:failed
echo Setup failed. Run the commands in README.md to troubleshoot.
pause
exit /b 1
