# Roblox Alt Manager (Python)

Personal Roblox account manager with profile icons, cookie rotation, and game favorites.

## Features

- Add accounts via browser login or cookie paste
- **24×24 profile pictures** (left of each username, never overlapping text)
- Avatars **re-checked every launch**
- **Favorite games** – enter a Place ID, name is fetched from Roblox API
- Launch into Place ID / Job ID / private server link code
- Auto cookie rotation (Set-Cookie) so accounts don’t randomly invalidate
- Optional background cookie refresh every 30 min
- Multi-instance (Windows)
- **Encrypted account vault** – cookies are encrypted at rest with a master password (AES via Fernet + PBKDF2). A stolen `accounts.json` is useless without the password.

## Run

```bash
pip install -r requirements.txt
python gui_main.py
```

On first launch you will be asked to create a master password. Existing plaintext cookies are automatically migrated into the encrypted vault.

## Security notes

- Cookies never sit on disk in cleartext once a password is set.
- Key is derived with PBKDF2-HMAC-SHA256 (480 000 iterations) + random salt.
- The in-memory key is cleared when the app exits.
- **Remember the password** – there is no recovery. If you forget it the vault cannot be decrypted.
- This protects against file stealers / cookie-grabber trojans that copy `accounts.json`. It does not protect against malware that can read process memory while the app is unlocked.

## Clean reset (for GitHub / sharing)

Wipe all personal data (accounts, favorites, tabs, config, avatars) while keeping the app code:

```bash
python reset_data.py
# or double-click reset_data.bat on Windows
# skip prompt:  python reset_data.py --yes
```

A `.gitignore` is included so `accounts.json` and other local data are not committed by mistake.

## Favorites

1. Click **+ Add** in the Favorite Games panel
2. Paste a Place ID or full `roblox.com/games/...` URL
3. Name is looked up automatically
4. **Use** or double-click to fill the Place ID field
5. Select an account → **Launch Selected**

## Icons

- Size: ~24×24 (downloaded at 48×48, scaled down)
- Column is fixed-width so icons never cover usernames
- Re-downloaded on every app start

## Files

- `accounts.json` – encrypted cookie vault (keep private + remember master password)
- `favorites.json` – saved games
- `avatar_cache/` – profile pictures
- `config.json` – theme + auto-refresh setting
- `reset_data.py` / `reset_data.bat` – wipe personal data for a clean upload
