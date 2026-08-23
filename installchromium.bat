@echo off
title Install Requirements & Chromium
cd /d "%~dp0"

echo ========================================
echo  1. Installing Python Packages...
echo ========================================
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
echo ========================================
echo  2. Checking for Chromium...
echo ========================================

set "CHROMIUM_PATH=%LOCALAPPDATA%\Chromium\Application\chrome.exe"
if exist "%CHROMIUM_PATH%" (
    echo [OK] Chromium is already installed.
    goto :end
)

echo [!] Chromium not found. Downloading now...
echo This may take a few minutes. Please wait.

REM Create directory
mkdir "%LOCALAPPDATA%\Chromium\Application" 2>nul

REM Download latest Chromium snapshot for Windows x64
echo Downloading from official snapshots...
powershell -Command "& { $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.googleapis.com/download/storage/v1/b/chromium-browser-snapshots/o/Win_x64%2F1318347%2Fchrome-win.zip?alt=media' -OutFile '%TEMP%\chromium.zip' }"

if not exist "%TEMP%\chromium.zip" (
    echo [!] Download failed. 
    echo Please try running this script again or check your internet connection.
    pause
    exit /b 1
)

echo Extracting...
powershell -Command "& { Expand-Archive -Path '%TEMP%\chromium.zip' -DestinationPath '%LOCALAPPDATA%\Chromium\Temp' -Force }"

REM Move files to the correct location
xcopy "%LOCALAPPDATA%\Chromium\Temp\chrome-win\*" "%LOCALAPPDATA%\Chromium\Application\" /E /Y /Q >nul

REM Cleanup
rmdir /S /Q "%LOCALAPPDATA%\Chromium\Temp"
del "%TEMP%\chromium.zip"

echo [OK] Chromium installed successfully!

:end
echo.
echo ========================================
echo  Installation Complete!
echo ========================================
pause