"""
Core logic for the Roblox Alt Manager.
Handles cookie validation, account storage, authentication tickets, launching,
cookie rotation (Set-Cookie), profile thumbnails, game favorites, and browser login.
"""
from __future__ import annotations
import base64
import json
import os
import platform
import re
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
from urllib.parse import quote
import requests

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False
    Fernet = None  # type: ignore
    InvalidToken = Exception  # type: ignore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ACCOUNTS_FILE = Path(__file__).parent / "accounts.json"
CONFIG_FILE = Path(__file__).parent / "config.json"
FAVORITES_FILE = Path(__file__).parent / "favorites.json"
TABS_FILE = Path(__file__).parent / "tabs.json"
AVATAR_CACHE_DIR = Path(__file__).parent / "avatar_cache"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)
ROBLOX_UA = "Roblox/WinInet"

# ---------------------------------------------------------------------------
# Encryption (AES-128 via Fernet + PBKDF2). Without the master password the
# accounts file is computationally infeasible to decrypt.
# ---------------------------------------------------------------------------
_PBKDF2_ITERATIONS = 480_000
_ENCRYPTION_VERSION = 1
_fernet: Optional["Fernet"] = None
_unlocked = False


class EncryptionError(Exception):
    """Raised when encryption/decryption fails or crypto is unavailable."""


def is_crypto_available() -> bool:
    return _HAS_CRYPTO


def is_unlocked() -> bool:
    return _unlocked


def is_accounts_encrypted() -> bool:
    """Return True if accounts.json is in the encrypted envelope format."""
    if not ACCOUNTS_FILE.exists():
        return False
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (
            isinstance(data, dict)
            and data.get("version") == _ENCRYPTION_VERSION
            and "salt" in data
            and "ciphertext" in data
        )
    except Exception:
        return False


def _derive_key(password: str, salt: bytes) -> bytes:
    if not _HAS_CRYPTO:
        raise EncryptionError("cryptography package is not installed")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))


def unlock(password: str) -> bool:
    """
    Unlock the accounts store with the master password.
    Returns True on success. On first-run / plaintext migration this also
    encrypts the existing file under the new password.
    """
    global _fernet, _unlocked
    if not _HAS_CRYPTO:
        raise EncryptionError(
            "Install the 'cryptography' package:  pip install cryptography"
        )
    if not password:
        return False

    if is_accounts_encrypted():
        try:
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                envelope = json.load(f)
            salt = base64.b64decode(envelope["salt"])
            key = _derive_key(password, salt)
            f = Fernet(key)
            # Verify the password by decrypting
            f.decrypt(envelope["ciphertext"].encode("ascii"))
            _fernet = f
            _unlocked = True
            return True
        except (InvalidToken, KeyError, ValueError, TypeError):
            return False
    else:
        # Plaintext or missing file → set up encryption with this password
        salt = os.urandom(16)
        key = _derive_key(password, salt)
        _fernet = Fernet(key)
        _unlocked = True
        # Migrate any existing plaintext accounts into the encrypted file
        accounts = _load_accounts_plaintext()
        _save_accounts_encrypted(accounts, salt)
        return True


def lock() -> None:
    """Clear the in-memory key (call on app exit if desired)."""
    global _fernet, _unlocked
    _fernet = None
    _unlocked = False


def change_password(old_password: str, new_password: str) -> bool:
    """Re-encrypt the accounts file under a new master password."""
    if not unlock(old_password):
        return False
    if not new_password:
        return False
    accounts = load_accounts()
    salt = os.urandom(16)
    key = _derive_key(new_password, salt)
    global _fernet
    _fernet = Fernet(key)
    _save_accounts_encrypted(accounts, salt)
    return True


def _load_accounts_plaintext() -> list["Account"]:
    if not ACCOUNTS_FILE.exists():
        return []
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, list):
            return [Account.from_dict(item) for item in raw]
        return []
    except Exception:
        return []


def _save_accounts_encrypted(accounts: list["Account"], salt: bytes | None = None) -> None:
    if not _unlocked or _fernet is None:
        raise EncryptionError("Accounts store is locked – unlock first")
    if salt is None:
        # Re-use existing salt when possible so the password still works
        if is_accounts_encrypted():
            with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                envelope = json.load(f)
            salt = base64.b64decode(envelope["salt"])
        else:
            salt = os.urandom(16)
            # Key was derived with a different salt; re-derive is not needed
            # because we already hold a working Fernet instance. We still
            # write a fresh salt only on first encryption (handled in unlock).
    plaintext = json.dumps([a.to_dict() for a in accounts], indent=2).encode("utf-8")
    ciphertext = _fernet.encrypt(plaintext)
    envelope = {
        "version": _ENCRYPTION_VERSION,
        "kdf": "pbkdf2-sha256",
        "iterations": _PBKDF2_ITERATIONS,
        "salt": base64.b64encode(salt).decode("ascii"),
        "ciphertext": ciphertext.decode("ascii"),
    }
    # Atomic write
    tmp = ACCOUNTS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(envelope, f, indent=2)
    tmp.replace(ACCOUNTS_FILE)

# ---------------------------------------------------------------------------
# Config Helpers
# ---------------------------------------------------------------------------
def load_config() -> dict:
    default_config = {
        "theme": "dark",
        "auto_cookie_refresh": True,
        "multi_instance": False,
        "launch_delay": 3.0,  # seconds between multi-account launches
    }
    if not CONFIG_FILE.exists():
        return default_config
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for k, v in default_config.items():
                data.setdefault(k, v)
            return data
    except Exception:
        return default_config

def save_config(config: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def load_tabs() -> dict:
    """
    tabs.json format:
      {
        "active": "all",
        "tabs": [
          {"id": "all", "name": "All", "builtin": true, "accounts": []},
          {"id": "...", "name": "Farm", "builtin": false, "accounts": ["user1", ...]}
        ]
      }
    Account membership is by username. The All tab always shows every account.
    """
    default = {
        "active": "all",
        "tabs": [
            {"id": "all", "name": "All", "builtin": True, "accounts": []},
        ],
    }
    if not TABS_FILE.exists():
        return default
    try:
        with open(TABS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return default
        tabs = data.get("tabs") or []
        # Ensure All exists and is first
        all_tab = next((t for t in tabs if t.get("id") == "all" or t.get("builtin")), None)
        if not all_tab:
            all_tab = {"id": "all", "name": "All", "builtin": True, "accounts": []}
        else:
            all_tab = {
                "id": "all",
                "name": all_tab.get("name") or "All",
                "builtin": True,
                "accounts": [],
            }
        others = []
        for t in tabs:
            if t.get("id") == "all" or t.get("builtin"):
                continue
            others.append({
                "id": str(t.get("id") or uuid.uuid4()),
                "name": str(t.get("name") or "Tab"),
                "builtin": False,
                "accounts": list(t.get("accounts") or []),
            })
        active = data.get("active") or "all"
        if active != "all" and not any(t["id"] == active for t in others):
            active = "all"
        return {"active": active, "tabs": [all_tab] + others}
    except Exception:
        return default


def save_tabs(data: dict) -> None:
    with open(TABS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class Account:
    username: str
    user_id: int
    cookie: str
    display_name: str = ""
    notes: str = ""
    added_at: float = 0.0
    last_validated: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Account":
        return cls(
            username=data["username"],
            user_id=data["user_id"],
            cookie=data["cookie"],
            display_name=data.get("display_name", ""),
            notes=data.get("notes", ""),
            added_at=data.get("added_at", 0.0),
            last_validated=data.get("last_validated", 0.0),
        )

@dataclass
class FavoriteGame:
    place_id: int
    name: str
    universe_id: int = 0
    added_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FavoriteGame":
        return cls(
            place_id=data["place_id"],
            name=data.get("name", f"Place {data['place_id']}"),
            universe_id=data.get("universe_id", 0),
            added_at=data.get("added_at", 0.0),
        )

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
def load_accounts() -> list[Account]:
    """
    Load accounts. Requires unlock() first when the file is encrypted.
    If the file is still plaintext (legacy) it is returned as-is; call unlock()
    to migrate it to encrypted storage.
    """
    if not ACCOUNTS_FILE.exists():
        return []
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # Encrypted envelope
        if isinstance(raw, dict) and raw.get("version") == _ENCRYPTION_VERSION:
            if not _unlocked or _fernet is None:
                raise EncryptionError("Accounts are encrypted – unlock with the master password first")
            plaintext = _fernet.decrypt(raw["ciphertext"].encode("ascii"))
            data = json.loads(plaintext.decode("utf-8"))
            return [Account.from_dict(item) for item in data]
        # Legacy plaintext list
        if isinstance(raw, list):
            return [Account.from_dict(item) for item in raw]
        return []
    except EncryptionError:
        raise
    except Exception:
        return []


def save_accounts(accounts: list[Account]) -> None:
    """
    Persist accounts. When unlocked, always writes the encrypted envelope so
    cookies never sit on disk in cleartext.
    """
    if _unlocked and _fernet is not None:
        _save_accounts_encrypted(accounts)
        return
    # Fallback: plaintext (only if user never set a password)
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump([a.to_dict() for a in accounts], f, indent=2)

def update_account_cookie(accounts: list[Account], user_id: int, new_cookie: str) -> bool:
    for acc in accounts:
        if acc.user_id == user_id and acc.cookie != new_cookie:
            acc.cookie = new_cookie
            save_accounts(accounts)
            return True
    return False

def load_favorites() -> list[FavoriteGame]:
    if not FAVORITES_FILE.exists():
        return []
    try:
        with open(FAVORITES_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [FavoriteGame.from_dict(item) for item in raw]
    except Exception:
        return []

def save_favorites(favorites: list[FavoriteGame]) -> None:
    with open(FAVORITES_FILE, "w", encoding="utf-8") as f:
        json.dump([g.to_dict() for g in favorites], f, indent=2)

# ---------------------------------------------------------------------------
# Cookie rotation helper
# ---------------------------------------------------------------------------
def _extract_roblosecurity(set_cookie_header: str | None) -> Optional[str]:
    if not set_cookie_header:
        return None
    matches = re.findall(
        r"\.ROBLOSECURITY=([^;,\s]+)",
        set_cookie_header,
        flags=re.IGNORECASE,
    )
    if not matches:
        return None
    best = max(matches, key=len)
    if len(best) > 50:
        return best
    return None

def apply_cookie_rotation(
    response: requests.Response,
    current_cookie: str,
    accounts: list[Account] | None = None,
    user_id: int | None = None,
) -> str:
    set_cookie = response.headers.get("Set-Cookie") or response.headers.get("set-cookie")
    if not set_cookie:
        try:
            raw = response.raw.headers.getlist("Set-Cookie")  # type: ignore
            if raw:
                set_cookie = ", ".join(raw)
        except Exception:
            pass

    new_cookie = _extract_roblosecurity(set_cookie)
    if new_cookie and new_cookie != current_cookie:
        if accounts is not None and user_id is not None:
            update_account_cookie(accounts, user_id, new_cookie)
        return new_cookie
    return current_cookie

# ---------------------------------------------------------------------------
# Roblox API helpers
# ---------------------------------------------------------------------------
def make_session(cookie: str) -> requests.Session:
    session = requests.Session()
    session.cookies.set(".ROBLOSECURITY", cookie, domain=".roblox.com")
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.roblox.com",
        "Referer": "https://www.roblox.com/",
    })
    return session

def validate_cookie(
    cookie: str,
    accounts: list[Account] | None = None,
    user_id: int | None = None,
) -> Optional[dict]:
    session = make_session(cookie)
    try:
        resp = session.get("https://users.roblox.com/v1/users/authenticated", timeout=15)
        cookie = apply_cookie_rotation(resp, cookie, accounts, user_id)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "id": data["id"],
                "name": data["name"],
                "displayName": data.get("displayName", data["name"]),
                "cookie": cookie,
            }
    except Exception:
        pass
    return None

def get_csrf_token(session: requests.Session) -> Optional[str]:
    try:
        resp = session.post("https://auth.roblox.com/v2/logout", timeout=10)
        token = resp.headers.get("x-csrf-token")
        if token:
            return token
    except Exception:
        pass
    return None

def get_auth_ticket(
    cookie: str,
    accounts: list[Account] | None = None,
    user_id: int | None = None,
) -> Optional[str]:
    session = make_session(cookie)
    csrf = get_csrf_token(session) or ""
    headers = {
        "X-CSRF-TOKEN": csrf,
        "Referer": "https://www.roblox.com/",
        "Origin": "https://www.roblox.com",
        "Content-Type": "application/json",
        "RBX-For-Gameauth": "true",
        "User-Agent": ROBLOX_UA,
    }
    try:
        resp = session.post(
            "https://auth.roblox.com/v1/authentication-ticket",
            headers=headers,
            json={},
            timeout=15,
        )
        cookie = apply_cookie_rotation(resp, cookie, accounts, user_id)

        if resp.status_code == 403 and "x-csrf-token" in resp.headers:
            headers["X-CSRF-TOKEN"] = resp.headers["x-csrf-token"]
            resp = session.post(
                "https://auth.roblox.com/v1/authentication-ticket",
                headers=headers,
                json={},
                timeout=15,
            )
            cookie = apply_cookie_rotation(resp, cookie, accounts, user_id)

        ticket = resp.headers.get("rbx-authentication-ticket")
        if ticket:
            return ticket
    except Exception as e:
        print(f"[!] Failed to get auth ticket: {e}")
    return None

# ---------------------------------------------------------------------------
# Game / Place info (for favorites)
# ---------------------------------------------------------------------------
def get_place_info(place_id: int) -> Optional[dict]:
    """
    Fetch place name + universeId from Roblox APIs.
    Returns {"place_id", "name", "universe_id"} or None.
    """
    try:
        # Primary: games multiget-place-details
        resp = requests.get(
            "https://games.roblox.com/v1/games/multiget-place-details",
            params={"placeIds": str(place_id)},
            timeout=12,
            headers={"User-Agent": USER_AGENT},
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and data:
                item = data[0]
                name = item.get("name") or item.get("placeName") or f"Place {place_id}"
                universe_id = item.get("universeId") or item.get("universe_id") or 0
                return {
                    "place_id": place_id,
                    "name": name,
                    "universe_id": int(universe_id) if universe_id else 0,
                }
    except Exception:
        pass

    # Fallback: universe from place
    try:
        resp = requests.get(
            f"https://apis.roblox.com/universes/v1/places/{place_id}/universe",
            timeout=10,
            headers={"User-Agent": USER_AGENT},
        )
        if resp.status_code == 200:
            uni = resp.json().get("universeId")
            if uni:
                # Get universe name
                r2 = requests.get(
                    f"https://games.roblox.com/v1/games",
                    params={"universeIds": str(uni)},
                    timeout=10,
                    headers={"User-Agent": USER_AGENT},
                )
                name = f"Place {place_id}"
                if r2.status_code == 200:
                    d = r2.json().get("data") or []
                    if d:
                        name = d[0].get("name") or name
                return {
                    "place_id": place_id,
                    "name": name,
                    "universe_id": int(uni),
                }
    except Exception:
        pass

    return None

# ---------------------------------------------------------------------------
# Profile pictures – always re-check on launch
# ---------------------------------------------------------------------------
def get_avatar_headshot_url(user_id: int, size: str = "48x48") -> Optional[str]:
    try:
        resp = requests.get(
            "https://thumbnails.roblox.com/v1/users/avatar-headshot",
            params={
                "userIds": str(user_id),
                "size": size,
                "format": "Png",
                "isCircular": "false",
            },
            timeout=10,
            headers={"User-Agent": USER_AGENT},
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("data"):
                item = data["data"][0]
                if item.get("state") == "Completed" and item.get("imageUrl"):
                    return item["imageUrl"]
    except Exception:
        pass
    return None

def download_avatar(user_id: int, size: str = "48x48", force: bool = False) -> Optional[Path]:
    """
    Download and cache avatar headshot.
    force=True → always re-download (used on every app launch).
    """
    AVATAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = AVATAR_CACHE_DIR / f"{user_id}_{size}.png"

    if not force and cache_path.exists() and cache_path.stat().st_size > 100:
        # Still allow short-term reuse within same session; force handles launch
        if time.time() - cache_path.stat().st_mtime < 300:  # 5 min
            return cache_path

    url = get_avatar_headshot_url(user_id, size)
    if not url:
        # Keep old file if download fails
        if cache_path.exists() and cache_path.stat().st_size > 100:
            return cache_path
        return None
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
        if r.status_code == 200 and r.content:
            cache_path.write_bytes(r.content)
            return cache_path
    except Exception:
        pass
    if cache_path.exists() and cache_path.stat().st_size > 100:
        return cache_path
    return None

def refresh_all_avatars(user_ids: list[int]) -> None:
    """Force re-download avatars for the given user IDs (called on launch)."""
    for uid in user_ids:
        try:
            download_avatar(uid, size="48x48", force=True)
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Launching
# ---------------------------------------------------------------------------
def build_launch_url(
    auth_ticket: str,
    place_id: int,
    job_id: str = "",
    link_code: str = "",
) -> str:
    browser_tracker_id = str(uuid.uuid4().int)[:15]
    launch_time = str(int(time.time() * 1000))

    if link_code:
        launcher = (
            "https://assetgame.roblox.com/game/PlaceLauncher.ashx"
            f"?request=RequestPrivateGame"
            f"&placeId={place_id}"
            f"&linkCode={link_code}"
            f"&browserTrackerId={browser_tracker_id}"
        )
    elif job_id:
        launcher = (
            "https://assetgame.roblox.com/game/PlaceLauncher.ashx"
            f"?request=RequestGameJob"
            f"&placeId={place_id}"
            f"&gameId={job_id}"
            f"&browserTrackerId={browser_tracker_id}"
            f"&isPlayTogetherGame=false"
        )
    else:
        launcher = (
            "https://assetgame.roblox.com/game/PlaceLauncher.ashx"
            f"?request=RequestGame"
            f"&placeId={place_id}"
            f"&browserTrackerId={browser_tracker_id}"
            f"&isPlayTogetherGame=false"
        )

    encoded_launcher = quote(launcher, safe="")
    url = (
        f"roblox-player:1+launchmode:play"
        f"+gameinfo:{auth_ticket}"
        f"+launchtime:{launch_time}"
        f"+placelauncherurl:{encoded_launcher}"
        f"+browsertrackerid:{browser_tracker_id}"
        f"+robloxLocale:en_us+gameLocale:en_us"
    )
    return url

def launch_account(
    account: Account,
    place_id: int,
    job_id: str = "",
    link_code: str = "",
    accounts: list[Account] | None = None,
) -> bool:
    ticket = get_auth_ticket(account.cookie, accounts=accounts, user_id=account.user_id)
    if not ticket:
        return False

    if accounts is not None:
        for a in accounts:
            if a.user_id == account.user_id:
                account.cookie = a.cookie
                break

    launch_url = build_launch_url(ticket, place_id, job_id=job_id, link_code=link_code)
    try:
        if platform.system() == "Windows":
            os.startfile(launch_url)  # type: ignore
        else:
            subprocess.Popen(["xdg-open", launch_url], start_new_session=True)
        return True
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Multi-instance (Windows only)
# Roblox uses named mutexes to enforce single-client mode. We create & hold
# them first so every subsequent Roblox client skips the singleton check.
# IMPORTANT: enable with NO Roblox processes running (including tray ghosts).
# ---------------------------------------------------------------------------
_mutex_handles: list = []

# All known singleton names (case variants) – all are MUTEX objects, not Events
_SINGLETON_NAMES = (
    "ROBLOX_singletonMutex",
    "ROBLOX_singletonEvent",
    "ROBLOX_SingletonEvent",
    "ROBLOX_SingletonMutex",
)

_ROBLOX_PROCESS_NAMES = (
    "robloxplayerbeta.exe",
    "robloxplayer.exe",
    "windows10universal.exe",
)


def find_roblox_pids() -> list:
    """Return PIDs of running Roblox client processes (Windows)."""
    if platform.system() != "Windows":
        return []
    pids = []
    try:
        import ctypes
        from ctypes import wintypes

        # Lightweight: tasklist via subprocess is fine and reliable
        out = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"],
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            errors="ignore",
        )
        for line in out.splitlines():
            # "Image Name","PID","Session Name","Session#","Mem Usage"
            parts = line.strip().strip('"').split('","')
            if len(parts) < 2:
                continue
            name = parts[0].lower()
            if name in _ROBLOX_PROCESS_NAMES:
                try:
                    pids.append(int(parts[1]))
                except ValueError:
                    pass
    except Exception:
        pass
    return pids


def enable_multi_instance() -> bool:
    """Create & hold Roblox singleton mutexes. Returns True on success."""
    global _mutex_handles
    if platform.system() != "Windows":
        print("[!] Multi-instance is Windows-only.")
        return False

    # Already holding – keep existing handles
    if _mutex_handles:
        print("[*] Multi-instance already active.")
        return True

    handles = []

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [
            wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR
        ]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        for name in _SINGLETON_NAMES:
            ctypes.set_last_error(0)
            # bInitialOwner=True → we own it for the life of this process
            h = kernel32.CreateMutexW(None, True, name)
            err = ctypes.get_last_error()
            if not h:
                print(f"[!] CreateMutexW({name}) failed, error={err}")
                continue
            handles.append(h)
            if err == 183:  # ERROR_ALREADY_EXISTS
                # Object existed – we have a handle but may not own it.
                # Still keep the handle open; works if we were first overall.
                print(f"[*] {name} already existed (handle kept open).")
            else:
                print(f"[+] Holding {name}")

        if handles:
            _mutex_handles = handles
            print(f"[+] Multi-instance ON ({len(handles)} mutexes held).")
            return True
    except Exception as e:
        print(f"[!] ctypes multi-instance failed: {e}")
        for h in handles:
            try:
                import ctypes
                ctypes.WinDLL("kernel32").CloseHandle(h)
            except Exception:
                pass
        handles = []

    # Fallback: pywin32
    try:
        import win32event  # type: ignore
        import win32api    # type: ignore
        import winerror    # type: ignore

        for name in _SINGLETON_NAMES:
            h = win32event.CreateMutex(None, True, name)
            if h:
                handles.append(h)
                if win32api.GetLastError() == getattr(winerror, "ERROR_ALREADY_EXISTS", 183):
                    print(f"[*] {name} already existed (pywin32).")
                else:
                    print(f"[+] Holding {name} (pywin32)")
        if handles:
            _mutex_handles = handles
            print(f"[+] Multi-instance ON ({len(handles)} mutexes, pywin32).")
            return True
    except ImportError:
        print("[!] Neither ctypes mutex nor pywin32 available.")
    except Exception as e:
        print(f"[!] pywin32 multi-instance failed: {e}")

    return False


def release_multi_instance() -> None:
    global _mutex_handles
    if not _mutex_handles:
        return
    try:
        import ctypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        for h in _mutex_handles:
            try:
                kernel32.CloseHandle(h)
            except Exception:
                pass
    except Exception:
        try:
            import win32api  # type: ignore
            for h in _mutex_handles:
                try:
                    win32api.CloseHandle(h)
                except Exception:
                    pass
        except Exception:
            pass
    _mutex_handles = []
    print("[*] Multi-instance mutexes released.")

# ---------------------------------------------------------------------------
# Browser login
# ---------------------------------------------------------------------------
def login_with_browser(timeout_seconds: int = 300) -> Optional[dict]:
    try:
        from selenium import webdriver
        from selenium.webdriver.edge.options import Options
    except ImportError:
        print("[!] Missing dependency. Run: pip install selenium")
        return None

    options = Options()
    temp_profile_dir = tempfile.mkdtemp(prefix="roblox_login_")
    options.add_argument(f"--user-data-dir={temp_profile_dir}")
    options.add_argument("--window-size=800,600")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    try:
        driver = webdriver.Edge(options=options)
    except Exception as e:
        print(f"[!] Could not start browser: {e}")
        return None

    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    })
                """
            },
        )
    except Exception:
        pass

    driver.get("https://www.roblox.com/login")

    start = time.time()
    cookie_value = None
    while time.time() - start < timeout_seconds:
        try:
            cookies = driver.get_cookies()
            for c in cookies:
                if c.get("name") == ".ROBLOSECURITY" and c.get("value"):
                    cookie_value = c["value"]
                    break
            if cookie_value:
                break
        except Exception:
            return None
        time.sleep(1.5)

    if not cookie_value:
        try:
            driver.quit()
        except Exception:
            pass
        return None

    info = validate_cookie(cookie_value)
    if not info:
        try:
            driver.quit()
        except Exception:
            pass
        return None

    try:
        driver.quit()
    except Exception:
        pass

    return {
        "cookie": info.get("cookie", cookie_value),
        "id": info["id"],
        "name": info["name"],
        "displayName": info["displayName"],
    }

def open_browser_for_account(account: Account) -> bool:
    try:
        from selenium import webdriver
        from selenium.webdriver.edge.options import Options
    except ImportError:
        return False

    options = Options()
    temp_profile_dir = tempfile.mkdtemp(prefix="roblox_session_")
    options.add_argument(f"--user-data-dir={temp_profile_dir}")
    options.add_argument("--window-size=800,600")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    try:
        driver = webdriver.Edge(options=options)
    except Exception:
        return False

    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    })
                """
            },
        )
    except Exception:
        pass

    driver.get("https://www.roblox.com")
    driver.add_cookie({
        "name": ".ROBLOSECURITY",
        "value": account.cookie,
        "domain": ".roblox.com",
        "path": "/",
        "secure": True,
        "httpOnly": True,
    })
    driver.refresh()
    return True

# ---------------------------------------------------------------------------
# Auto cookie refresh
# ---------------------------------------------------------------------------
def refresh_all_cookies(accounts: list[Account]) -> tuple[int, int, list[str]]:
    valid = 0
    invalid: list[str] = []
    for acc in accounts:
        info = validate_cookie(acc.cookie, accounts=accounts, user_id=acc.user_id)
        if info:
            acc.username = info["name"]
            acc.display_name = info["displayName"]
            if "cookie" in info:
                acc.cookie = info["cookie"]
            acc.last_validated = time.time()
            valid += 1
        else:
            invalid.append(acc.username)
    save_accounts(accounts)
    return valid, len(accounts), invalid
