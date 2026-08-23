@echo off
setlocal EnableExtensions
title Build GitHub Release folder
cd /d "%~dp0"

set "RELEASE=RobloxAltManager_Release"
set "APPNAME=RobloxAltManager"

echo.
echo  ============================================================
echo   Roblox Alt Manager - Build GitHub Release
echo  ============================================================
echo.
echo  This will create a folder:
echo    %cd%\%RELEASE%\
echo  containing a ready-to-run EXE + reset tools.
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found in PATH.
  echo Install Python 3.10+ from python.org and check "Add to PATH".
  pause
  exit /b 1
)

echo [1/4] Installing dependencies...
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt pyinstaller pillow
if errorlevel 1 (
  echo [ERROR] pip install failed.
  pause
  exit /b 1
)

echo [2/4] Building EXE with PyInstaller...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --windowed ^
  --name "%APPNAME%" ^
  --icon "app_icon.ico" ^
  --hidden-import cryptography ^
  --hidden-import cryptography.fernet ^
  --hidden-import cryptography.hazmat.primitives.kdf.pbkdf2 ^
  --collect-all cryptography ^
  gui_main.py

if errorlevel 1 (
  echo [ERROR] PyInstaller build failed.
  pause
  exit /b 1
)

if not exist "dist\%APPNAME%\%APPNAME%.exe" (
  echo [ERROR] EXE not found after build.
  pause
  exit /b 1
)

echo [3/4] Assembling release folder...
if exist "%RELEASE%" rmdir /s /q "%RELEASE%"
mkdir "%RELEASE%"

xcopy /E /I /Y "dist\%APPNAME%\*" "%RELEASE%\" >nul

copy /Y "reset_data.bat" "%RELEASE%\" >nul
copy /Y "reset_data.py" "%RELEASE%\" >nul
copy /Y ".gitignore" "%RELEASE%\" >nul
if exist "app_icon.ico" copy /Y "app_icon.ico" "%RELEASE%\" >nul

mkdir "%RELEASE%\avatar_cache" 2>nul

REM Clean starter data files (no cookies in a public release)
echo []> "%RELEASE%\accounts.json"
echo []> "%RELEASE%\favorites.json"
(
echo {
echo   "theme": "dark",
echo   "auto_cookie_refresh": true,
echo   "multi_instance": false,
echo   "launch_delay": 3.0
echo }
) > "%RELEASE%\config.json"
(
echo {
echo   "active": "all",
echo   "tabs": [
echo     {"id": "all", "name": "All", "builtin": true, "accounts": []}
echo   ]
echo }
) > "%RELEASE%\tabs.json"

(
echo Roblox Alt Manager
echo ==================
echo.
echo Run:  %APPNAME%.exe
echo.
echo First launch asks for a master password - cookies are encrypted on disk.
echo.
echo Before uploading to GitHub / sharing:
echo   1. Double-click reset_data.bat
echo   2. Type YES
echo   3. Zip this folder or push to Git
echo.
echo .gitignore already ignores accounts.json and other personal files.
) > "%RELEASE%\README.txt"

echo [4/4] Cleaning build leftovers...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "%APPNAME%.spec" del /q "%APPNAME%.spec"

echo.
echo  ============================================================
echo   DONE
echo  ============================================================
echo.
echo  Release folder:
echo    %cd%\%RELEASE%\
echo.
echo  Inside it:
echo    %APPNAME%.exe     - run this
echo    reset_data.bat    - wipe personal data before GitHub
echo    README.txt
echo.
echo  Zip that folder and attach it to your GitHub Release.
echo.
pause
endlocal
