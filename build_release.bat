@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Build GitHub Release folder
cd /d "%~dp0"

set "RELEASE=RobloxAltManager_Release"
set "APPNAME=RobloxAltManager"
set "SPECFILE=%APPNAME%.spec"

echo.
echo  ============================================================
echo   Roblox Alt Manager - Build GitHub Release
echo  ============================================================
echo.
echo  This will create:
echo    %cd%\%RELEASE%\
echo  with a ready-to-run EXE and zero personal data.
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found in PATH.
  echo Install Python 3.10+ from python.org and check "Add to PATH".
  pause
  exit /b 1
)

echo [1/5] Installing dependencies...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt pyinstaller pillow
if errorlevel 1 (
  echo [ERROR] pip install failed.
  pause
  exit /b 1
)

echo [2/5] Cleaning previous build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "%SPECFILE%" del /q "%SPECFILE%"
if exist "%RELEASE%" rmdir /s /q "%RELEASE%"

echo [3/5] Building EXE with PyInstaller (onedir, windowed)...
REM
REM Notes that fix common runtime issues:
REM  - collect cryptography / pystray / selenium / certifi fully
REM  - include win32 modules used by multi-instance
REM  - bundle icons so tray + title bar work when frozen
REM  - roblox_manager is a local module next to gui_main (auto-found)
REM
python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --windowed ^
  --name "%APPNAME%" ^
  --icon "app_icon.ico" ^
  --add-data "app_icon.ico;." ^
  --add-data "app_icon.png;." ^
  --add-data "app_icon_32.png;." ^
  --add-data "app_icon_48.png;." ^
  --add-data "app_icon_64.png;." ^
  --hidden-import=roblox_manager ^
  --hidden-import=cryptography ^
  --hidden-import=cryptography.fernet ^
  --hidden-import=cryptography.hazmat.primitives.kdf.pbkdf2 ^
  --hidden-import=cryptography.hazmat.backends ^
  --hidden-import=pystray ^
  --hidden-import=PIL ^
  --hidden-import=PIL.Image ^
  --hidden-import=PIL.ImageTk ^
  --hidden-import=PIL.ImageDraw ^
  --hidden-import=requests ^
  --hidden-import=urllib3 ^
  --hidden-import=certifi ^
  --hidden-import=charset_normalizer ^
  --hidden-import=idna ^
  --hidden-import=selenium ^
  --hidden-import=selenium.webdriver ^
  --hidden-import=selenium.webdriver.edge ^
  --hidden-import=selenium.webdriver.edge.options ^
  --hidden-import=selenium.webdriver.edge.service ^
  --hidden-import=selenium.webdriver.common ^
  --hidden-import=win32api ^
  --hidden-import=win32event ^
  --hidden-import=winerror ^
  --hidden-import=pythoncom ^
  --hidden-import=pywintypes ^
  --hidden-import=tkinter ^
  --hidden-import=tkinter.ttk ^
  --hidden-import=tkinter.messagebox ^
  --hidden-import=tkinter.simpledialog ^
  --collect-all=cryptography ^
  --collect-all=pystray ^
  --collect-all=certifi ^
  --collect-submodules=selenium ^
  --collect-submodules=win32com ^
  gui_main.py

if errorlevel 1 (
  echo [ERROR] PyInstaller build failed. Scroll up for the Python traceback.
  pause
  exit /b 1
)

if not exist "dist\%APPNAME%\%APPNAME%.exe" (
  echo [ERROR] EXE not found after build: dist\%APPNAME%\%APPNAME%.exe
  pause
  exit /b 1
)

echo [4/5] Assembling release folder (NO personal data)...
mkdir "%RELEASE%"
xcopy /E /I /Y "dist\%APPNAME%\*" "%RELEASE%\" >nul

REM Helper scripts for the end user
copy /Y "reset_data.bat" "%RELEASE%\" >nul
copy /Y "reset_data.py" "%RELEASE%\" >nul
copy /Y ".gitignore" "%RELEASE%\" >nul

REM Icons also next to the EXE (in addition to bundled _MEIPASS copies)
if exist "app_icon.ico" copy /Y "app_icon.ico" "%RELEASE%\" >nul
if exist "app_icon.png" copy /Y "app_icon.png" "%RELEASE%\" >nul
if exist "app_icon_32.png" copy /Y "app_icon_32.png" "%RELEASE%\" >nul
if exist "app_icon_48.png" copy /Y "app_icon_48.png" "%RELEASE%\" >nul
if exist "app_icon_64.png" copy /Y "app_icon_64.png" "%RELEASE%\" >nul

REM ---- Wipe ALL personal / runtime data in the release folder ----
if exist "%RELEASE%\avatar_cache" rmdir /s /q "%RELEASE%\avatar_cache"
if exist "%RELEASE%\browser_profiles" rmdir /s /q "%RELEASE%\browser_profiles"
if exist "%RELEASE%\__pycache__" rmdir /s /q "%RELEASE%\__pycache__"
mkdir "%RELEASE%\avatar_cache" 2>nul
mkdir "%RELEASE%\browser_profiles" 2>nul

if exist "%RELEASE%\.roblox_alt_manager.lock" del /q "%RELEASE%\.roblox_alt_manager.lock"
if exist "%RELEASE%\accounts.json.tmp" del /q "%RELEASE%\accounts.json.tmp"

REM Empty starter data (never ship real cookies)
(
echo []
) > "%RELEASE%\accounts.json"
(
echo []
) > "%RELEASE%\favorites.json"
(
echo {
echo   "theme": "dark",
echo   "auto_cookie_refresh": true,
echo   "multi_instance": false,
echo   "launch_delay": 3.0,
echo   "active_place_id": "",
echo   "active_job_id": "",
echo   "active_link_code": "",
echo   "last_visited_servers": []
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
echo First launch asks for a master password — cookies are encrypted on disk.
echo.
echo Before uploading to GitHub / sharing:
echo   1. Double-click reset_data.bat
echo   2. Type YES
echo   3. Zip this folder
echo.
echo The build already ships with empty accounts / no avatars / no browser profiles.
echo reset_data.bat is for wiping after you tested the EXE yourself.
echo.
echo Requirements on the PC that runs the EXE:
echo   - Windows 10/11
echo   - Microsoft Edge ^(for "Open in browser" / browser login^)
echo   - No Python install needed
) > "%RELEASE%\README.txt"

echo [5/5] Cleaning build leftovers...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "%SPECFILE%" del /q "%SPECFILE%"

echo.
echo  ============================================================
echo   DONE
echo  ============================================================
echo.
echo  Release folder:
echo    %cd%\%RELEASE%\
echo.
echo  Inside it:
echo    %APPNAME%.exe      - run this
echo    reset_data.bat     - wipe personal data after testing
echo    README.txt
echo.
echo  All accounts / avatars / browser profiles were cleared in the release.
echo  Zip that folder and attach it to your GitHub Release.
echo.
pause
endlocal
