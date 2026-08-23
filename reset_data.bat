@echo off
title Reset Roblox Alt Manager data
cd /d "%~dp0"
echo.
echo  This will wipe accounts, favorites, tabs, config, avatars.
echo  Safe for uploading a clean copy to GitHub.
echo.
python reset_data.py %*
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)
echo.
pause
