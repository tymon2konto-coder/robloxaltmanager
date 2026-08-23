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
  reset_data.bat         ← one-click wipe before GitHub
  reset_data.py
  .gitignore
  README.txt
  avatar_cache/
  accounts.json          ← empty
  …
```

Zip `RobloxAltManager_Release` and attach it to a GitHub Release.

### Before pushing / sharing
In the release folder (or source folder):

```
reset_data.bat
```

Wipes accounts, favorites, tabs, config, avatars. Code/exe stay.

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
