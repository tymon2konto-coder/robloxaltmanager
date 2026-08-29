# Roblox Alt Manager (Python)

Personal Roblox account manager with profile icons, cookie rotation, favorites, and an encrypted cookie vault.

## Run from source

```bash
pip install -r requirements.txt
python gui_main.py
```

First launch: create a master password. Cookies are encrypted on disk (AES + PBKDF2).


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
| `reset_data.bat` | Wipe personal data |
| `app_icon.ico` | App icon |
