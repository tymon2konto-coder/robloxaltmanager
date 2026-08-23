<img width="512" height="512" alt="app_icon" src="https://github.com/user-attachments/assets/1889b210-c020-4b57-af87-a8ad956e7db3"
/># Roblox Alt Manager (Python)

Personal Roblox account manager with profile icons, cookie rotation, favorites, and an encrypted cookie vault.

## Run from source

```bash
pip install -r requirements.txt
python gui_main.py
```

First launch: create a master password. Cookies are encrypted on disk (AES + PBKDF2).

<img width="309" height="248" alt="image" src="https://github.com/user-attachments/assets/b42fa878-ab1a-48f9-9e2b-69044ab598aa" />


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
<img width="980" height="587" alt="image" src="https://github.com/user-attachments/assets/eb72713f-fcfc-40cb-8c2a-d0b421447bab" />
<img width="420" height="484" alt="image" src="https://github.com/user-attachments/assets/2e6257bd-0814-4998-a05a-a9f999657968" />
