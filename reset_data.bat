@echo off
title Reset data
cd /d "%~dp0"
echo.
echo  Wipe accounts, favorites, tabs, config, avatars, browser profiles.
echo  Safe for GitHub after this.
echo.
where python >nul 2>&1
if errorlevel 1 (
  echo Python not found - writing empty data files without Python...
  echo []> accounts.json
  echo []> favorites.json
  echo {"theme":"dark","auto_cookie_refresh":true,"multi_instance":false,"launch_delay":3.0,"active_place_id":"","active_job_id":"","active_link_code":"","last_visited_servers":[]}> config.json
  echo {"active":"all","tabs":[{"id":"all","name":"All","builtin":true,"accounts":[]}]}> tabs.json
  if exist avatar_cache rmdir /s /q avatar_cache
  mkdir avatar_cache
  if exist browser_profiles rmdir /s /q browser_profiles
  mkdir browser_profiles
  if exist .roblox_alt_manager.lock del /q .roblox_alt_manager.lock
  if exist accounts.json.tmp del /q accounts.json.tmp
  echo Done.
  pause
  exit /b 0
)
python reset_data.py %*
echo.
pause
