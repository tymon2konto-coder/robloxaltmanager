# Roblox Alt Manager (Python)

Personal Roblox account manager with profile icons, cookie rotation, favorites, and an encrypted cookie vault.

## Run from source

```bash
pip install -r requirements.txt
python gui_main.py
```

First launch: create a master password. Cookies are encrypted on disk (AES + PBKDF2).

## Build a GitHub Release (Windows)

Double-click:

```
build_release.bat
```

That creates:

```
RobloxAltManager_Release/
  RobloxAltManager.exe   ← ready to run (your icon)
  reset_data.bat         ← one-click wipe after testing
  reset_data.py
  .gitignore
  README.txt
  avatar_cache/          ← empty
  browser_profiles/      ← empty
  accounts.json          ← empty (no cookies)
  …
```

The builder **always strips all personal data** from the release folder
(accounts, favorites, tabs, config, avatars, browser profiles, lock files).

Zip `RobloxAltManager_Release` and attach it to a GitHub Release.

### Before pushing / sharing (after you tested the EXE)
In the release folder (or source folder):

```
reset_data.bat
```

Wipes accounts, favorites, tabs, config, avatars, browser profiles. Code/exe stay.

### If the EXE crashes on launch
Check `crash.log` next to the EXE (written automatically on fatal errors).
Target PC needs: Windows 10/11 + Microsoft Edge (for browser login features).

## Security

- Master password required to unlock
- Change password: **Settings → Security**
- Stolen `accounts.json` is useless without the password
- No recovery if you forget the password

## Files

| File | Purpose |
|------|---------|
| `gui_main.py` | GUI |
| `roblox_manager.py` | Core logic + encryption |
| `build_release.bat` | Build release folder with EXE |
| `reset_data.bat` | Wipe personal data |
| `app_icon.ico` | App icon |
