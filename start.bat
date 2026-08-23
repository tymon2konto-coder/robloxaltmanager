@echo off
title Roblox Alt Manager - GUI
cd /d "%~dp0"
python gui_main.py
if errorlevel 1 (
echo.
echo Something went wrong. Make sure Python is installed and requirements are installed.
echo Run requirements.bat first if you haven't.
pause
)