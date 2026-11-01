@echo off
cd /d "%~dp0"
if exist "venv\Scripts\python.exe" (
  "venv\Scripts\python.exe" "background_monitor.py"
) else (
  python "background_monitor.py"
)
pause
