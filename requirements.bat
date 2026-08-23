@echo off
title Install Requirements - Roblox Alt Manager
echo Installing Python packages...
echo.
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo Done!
pause