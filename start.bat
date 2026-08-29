@echo off
cd /d "%~dp0"

REM Prefer pythonw = no console window. Falls back to python if missing.
where pythonw >nul 2>&1
if %errorlevel%==0 (
  start "" pythonw gui_main.py
  exit /b 0
)

python gui_main.py
if errorlevel 1 (
  echo.
  echo Something went wrong. Make sure Python is installed and requirements are installed.
  echo Run requirements.bat first if you haven't.
  pause
)
