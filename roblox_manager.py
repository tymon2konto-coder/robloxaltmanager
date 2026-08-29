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
import sys
import re
import subprocess
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
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
def _app_dir() -> Path:
    """Writable data dir: next to the EXE when frozen, else the script folder."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

_APP_DIR = _app_dir()
ACCOUNTS_FILE = _APP_DIR / "accounts.json"
CONFIG_FILE = _APP_DIR / "config.json"
FAVORITES_FILE = _APP_DIR / "favorites.json"
TABS_FILE = _APP_DIR / "tabs.json"
AVATAR_CACHE_DIR = _APP_DIR / "avatar_cache"
BROWSER_PROFILES_DIR = _APP_DIR / "browser_profiles"
INTERACTIVE_TIMEOUT = 6
AVATAR_CACHE_MAX_AGE = 7 * 24 * 3600  # 7 days
FRIENDS_CACHE_TTL = 120.0  # seconds
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
        "active_place_id": "",
        "active_job_id": "",
        "active_link_code": "",
        "last_visited_servers": [],
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
# Lightweight session reuse for polling / repeated calls with the same cookie.
# Keyed by a short hash of the cookie so we don't keep secrets in plain keys.
_SESSION_CACHE: dict[str, tuple[float, "requests.Session"]] = {}
_SESSION_CACHE_TTL = 90.0  # seconds
_SESSION_CACHE_MAX = 8


def _cookie_cache_key(cookie: str) -> str:
    # Short stable key — never store the full cookie as a dict key longer than needed
    return str(hash(cookie[:48] + cookie[-24:] if len(cookie) > 72 else cookie))


def make_session(cookie: str, reuse: bool = True) -> requests.Session:
    """
    Build a requests.Session with Roblox headers + cookie.
    When reuse=True (default), return a cached session for the same cookie
    so connection pooling helps repeated presence/friends/validate calls.
    """
    if reuse and cookie:
        key = _cookie_cache_key(cookie)
        hit = _SESSION_CACHE.get(key)
        if hit:
            ts, sess = hit
            if time.time() - ts < _SESSION_CACHE_TTL:
                # Refresh cookie on the session in case it rotated
                try:
                    sess.cookies.set(".ROBLOSECURITY", cookie, domain=".roblox.com")
                except Exception:
                    pass
                _SESSION_CACHE[key] = (time.time(), sess)
                return sess
        # Evict oldest if full
        if len(_SESSION_CACHE) >= _SESSION_CACHE_MAX:
            oldest = min(_SESSION_CACHE.items(), key=lambda kv: kv[1][0])
            try:
                del _SESSION_CACHE[oldest[0]]
            except KeyError:
                pass

    session = requests.Session()
    session.cookies.set(".ROBLOSECURITY", cookie, domain=".roblox.com")
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Origin": "https://www.roblox.com",
        "Referer": "https://www.roblox.com/",
        "Connection": "keep-alive",
    })
    # Slightly more aggressive pool for parallel refreshes
    try:
        from requests.adapters import HTTPAdapter
        adapter = HTTPAdapter(pool_connections=8, pool_maxsize=8, max_retries=0)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
    except Exception:
        pass

    if reuse and cookie:
        _SESSION_CACHE[_cookie_cache_key(cookie)] = (time.time(), session)
    return session

def validate_cookie(
    cookie: str,
    accounts: list[Account] | None = None,
    user_id: int | None = None,
) -> Optional[dict]:
    session = make_session(cookie)
    try:
        resp = session.get("https://users.roblox.com/v1/users/authenticated", timeout=INTERACTIVE_TIMEOUT)
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
        resp = session.post("https://auth.roblox.com/v2/logout", timeout=5)
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
            timeout=8,
        )
        cookie = apply_cookie_rotation(resp, cookie, accounts, user_id)

        if resp.status_code == 403 and "x-csrf-token" in resp.headers:
            headers["X-CSRF-TOKEN"] = resp.headers["x-csrf-token"]
            resp = session.post(
                "https://auth.roblox.com/v1/authentication-ticket",
                headers=headers,
                json={},
                timeout=8,
            )
            cookie = apply_cookie_rotation(resp, cookie, accounts, user_id)

        ticket = resp.headers.get("rbx-authentication-ticket")
        if ticket:
            return ticket
    except Exception as e:
        print(f"[!] Failed to get auth ticket: {e}")
    return None

# ---------------------------------------------------------------------------
# Friends + presence (online friends for selected account)
# ---------------------------------------------------------------------------
_FRIENDS_CACHE: dict[int, tuple[float, list[dict]]] = {}


def _resolve_user_names(session: requests.Session, user_ids: list[int]) -> dict[int, dict]:
    """
    Batch-resolve username + displayName for user ids.
    Friends API no longer returns names; users.roblox.com does.
    Returns {user_id: {"name": str, "displayName": str}}.
    """
    out: dict[int, dict] = {}
    chunk_size = 100
    for i in range(0, len(user_ids), chunk_size):
        chunk = [uid for uid in user_ids[i : i + chunk_size] if uid and uid > 0]
        if not chunk:
            continue
        try:
            resp = session.post(
                "https://users.roblox.com/v1/users",
                json={"userIds": chunk, "excludeBannedUsers": False},
                timeout=8,
            )
            if resp.status_code != 200:
                continue
            for item in resp.json().get("data") or []:
                uid = item.get("id")
                if uid is None:
                    continue
                name = (item.get("name") or "").strip()
                display = (item.get("displayName") or name or "").strip()
                if not name:
                    continue
                out[int(uid)] = {"name": name, "displayName": display or name}
        except Exception:
            continue
    return out


def get_friends(cookie: str, user_id: int, use_cache: bool = True) -> list[dict]:
    """
    Return friends of user_id: [{"id", "name", "displayName"}, ...].
    Friend list API only returns ids now; names are resolved via users API.
    Cached for FRIENDS_CACHE_TTL so presence polls don't re-fetch the graph.
    """
    if use_cache:
        hit = _FRIENDS_CACHE.get(int(user_id))
        if hit:
            ts, data = hit
            if time.time() - ts < FRIENDS_CACHE_TTL:
                return data

    session = make_session(cookie)
    friend_ids: list[int] = []
    try:
        # Non-paginated endpoint (capped ~200) — still the simplest source of ids
        resp = session.get(
            f"https://friends.roblox.com/v1/users/{user_id}/friends",
            timeout=8,
        )
        if resp.status_code == 200:
            for item in resp.json().get("data") or []:
                fid = item.get("id")
                if fid is None:
                    continue
                try:
                    fid_i = int(fid)
                except (TypeError, ValueError):
                    continue
                if fid_i > 0:
                    friend_ids.append(fid_i)

        # If we hit the cap or got nothing, try paginated /friends/find
        if len(friend_ids) >= 200 or not friend_ids:
            cursor = ""
            seen = set(friend_ids)
            while True:
                params: dict = {"limit": 50}
                if cursor:
                    params["cursor"] = cursor
                resp = session.get(
                    f"https://friends.roblox.com/v1/users/{user_id}/friends/find",
                    params=params,
                    timeout=8,
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                page = data.get("pageItems") or data.get("data") or []
                for item in page:
                    fid = item.get("id")
                    if fid is None:
                        continue
                    try:
                        fid_i = int(fid)
                    except (TypeError, ValueError):
                        continue
                    if fid_i > 0 and fid_i not in seen:
                        seen.add(fid_i)
                        friend_ids.append(fid_i)
                cursor = data.get("nextCursor") or data.get("nextPageCursor") or ""
                if not cursor or not data.get("hasMore", bool(cursor)):
                    break
    except Exception:
        pass

    if not friend_ids:
        return []

    names = _resolve_user_names(session, friend_ids)
    friends: list[dict] = []
    for fid in friend_ids:
        info = names.get(fid)
        if not info:
            # Skip unresolved ids so the UI never shows bare numbers
            continue
        friends.append({
            "id": fid,
            "name": info["name"],
            "displayName": info["displayName"],
        })
    _FRIENDS_CACHE[int(user_id)] = (time.time(), friends)
    return friends


def get_presences(cookie: str, user_ids: list[int]) -> dict[int, dict]:
    """
    Batch-fetch presence for user_ids.
    Returns {user_id: {
        "userPresenceType": int,  # 0 Offline, 1 Online, 2 InGame, 3 InStudio
        "lastLocation": str,
        "placeId": int | None,
        "rootPlaceId": int | None,
        "gameId": str | None,  # job / server instance id
        "universeId": int | None,
    }}
    """
    session = make_session(cookie)
    result: dict[int, dict] = {}
    # API accepts up to ~100 ids per request
    chunk_size = 100
    for i in range(0, len(user_ids), chunk_size):
        chunk = user_ids[i : i + chunk_size]
        if not chunk:
            continue
        try:
            resp = session.post(
                "https://presence.roblox.com/v1/presence/users",
                json={"userIds": chunk},
                timeout=8,
            )
            if resp.status_code != 200:
                continue
            for item in (resp.json().get("userPresences") or []):
                uid = item.get("userId")
                if uid is None:
                    continue
                result[int(uid)] = {
                    "userPresenceType": int(item.get("userPresenceType") or 0),
                    "lastLocation": item.get("lastLocation") or "",
                    "placeId": item.get("placeId"),
                    "rootPlaceId": item.get("rootPlaceId"),
                    "gameId": item.get("gameId") or item.get("gameInstanceId"),
                    "universeId": item.get("universeId"),
                }
        except Exception:
            continue
    return result


def get_online_friends(cookie: str, user_id: int) -> list[dict]:
    """
    Friends who are InGame only (not idle on site), with presence details for joining.
    Each entry:
      {
        "id", "name", "displayName",
        "userPresenceType", "lastLocation",
        "placeId", "rootPlaceId", "gameId", "universeId",
        "game_name",  # best-effort label for UI
      }
    Sorted: InGame first, then Online.
    """
    friends = get_friends(cookie, user_id)
    if not friends:
        return []
    ids = [f["id"] for f in friends]
    presences = get_presences(cookie, ids)
    online: list[dict] = []
    for f in friends:
        p = presences.get(f["id"])
        if not p:
            continue
        ptype = p.get("userPresenceType", 0)
        # Only friends actually in a game — not idle on site / Studio
        if ptype != 2:
            continue
        game_name = (p.get("lastLocation") or "").strip() or "In game"
        online.append({
            "id": f["id"],
            "name": f["name"],
            "displayName": f["displayName"],
            "userPresenceType": ptype,
            "lastLocation": p.get("lastLocation") or "",
            "placeId": p.get("placeId"),
            "rootPlaceId": p.get("rootPlaceId"),
            "gameId": p.get("gameId"),
            "universeId": p.get("universeId"),
            "game_name": game_name,
        })
    online.sort(key=lambda x: x["displayName"].lower())
    return online


def get_public_servers(
    place_id: int,
    cookie: str = "",
    limit: int = 100,
    cursor: str = "",
) -> tuple[list[dict], str]:
    """
    List public servers for a place (one page).
    Returns (servers, next_cursor).
    Each server: {"id" (job id), "playing", "maxPlayers", "ping", "fps"}
    Sorted most relevant first: higher player count, then lower ping.
    """
    session = make_session(cookie) if cookie else requests.Session()
    if not cookie:
        session.headers.update({"User-Agent": USER_AGENT})
    servers: list[dict] = []
    next_cursor = ""
    try:
        params: dict = {
            "sortOrder": "Desc",  # more populated first when API supports it
            "limit": min(100, max(10, limit)),
        }
        if cursor:
            params["cursor"] = cursor
        resp = session.get(
            f"https://games.roblox.com/v1/games/{place_id}/servers/Public",
            params=params,
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("data") or []:
                job_id = item.get("id")
                if not job_id:
                    continue
                servers.append({
                    "id": str(job_id),
                    "playing": int(item.get("playing") or 0),
                    "maxPlayers": int(item.get("maxPlayers") or 0),
                    "ping": item.get("ping"),
                    "fps": item.get("fps"),
                })
            next_cursor = data.get("nextPageCursor") or ""
    except Exception:
        pass
    # Client-side relevance: active servers first (most players), then best ping
    def relevance(s: dict):
        ping = s.get("ping")
        ping_k = int(ping) if isinstance(ping, (int, float)) else 5_000
        return (-s.get("playing", 0), ping_k)
    servers.sort(key=relevance)
    return servers, next_cursor


def pick_fast_server(servers: list[dict]) -> Optional[dict]:
    """Prefer lowest ping; fall back to highest fps, then fewest players."""
    if not servers:
        return None
    def key(s: dict):
        ping = s.get("ping")
        fps = s.get("fps")
        # Missing ping sorts last
        ping_k = int(ping) if isinstance(ping, (int, float)) else 10_000
        fps_k = -float(fps) if isinstance(fps, (int, float)) else 0
        return (ping_k, fps_k, s.get("playing", 0))
    return min(servers, key=key)


def pick_small_server(servers: list[dict]) -> Optional[dict]:
    """Fewest players; prefer not full."""
    if not servers:
        return None
    open_servers = [
        s for s in servers
        if s.get("maxPlayers", 0) <= 0 or s.get("playing", 0) < s.get("maxPlayers", 0)
    ]
    pool = open_servers or servers
    return min(pool, key=lambda s: (s.get("playing", 0), s.get("ping") or 10_000))


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
# Profile pictures
# ---------------------------------------------------------------------------
def get_avatar_headshot_url(user_id: int, size: str = "48x48") -> Optional[str]:
    urls = get_avatar_headshot_urls([user_id], size=size)
    return urls.get(int(user_id))


def get_avatar_headshot_urls(user_ids: list[int], size: str = "48x48") -> dict[int, str]:
    """
    Batch-fetch avatar headshot URLs (thumbnails API accepts many userIds).
    Returns {user_id: imageUrl} for Completed entries only.
    """
    out: dict[int, str] = {}
    ids = [int(u) for u in user_ids if u]
    if not ids:
        return out
    chunk_size = 100
    for i in range(0, len(ids), chunk_size):
        chunk = ids[i : i + chunk_size]
        try:
            resp = requests.get(
                "https://thumbnails.roblox.com/v1/users/avatar-headshot",
                params={
                    "userIds": ",".join(str(u) for u in chunk),
                    "size": size,
                    "format": "Png",
                    "isCircular": "false",
                },
                timeout=12,
                headers={"User-Agent": USER_AGENT},
            )
            if resp.status_code != 200:
                continue
            for item in (resp.json().get("data") or []):
                if item.get("state") != "Completed":
                    continue
                url = item.get("imageUrl")
                target = item.get("targetId")
                if url and target is not None:
                    out[int(target)] = url
        except Exception:
            continue
    return out


def download_avatar(user_id: int, size: str = "48x48", force: bool = False) -> Optional[Path]:
    """
    Download and cache avatar headshot.
    Disk cache is trusted for AVATAR_CACHE_MAX_AGE unless force=True.
    force still skips a re-download if the file is under 5 minutes old.
    """
    AVATAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = AVATAR_CACHE_DIR / f"{user_id}_{size}.png"

    if cache_path.exists() and cache_path.stat().st_size > 100:
        age = time.time() - cache_path.stat().st_mtime
        if not force and age < AVATAR_CACHE_MAX_AGE:
            return cache_path
        if force and age < 300:
            return cache_path

    url = get_avatar_headshot_url(user_id, size)
    if not url:
        if cache_path.exists() and cache_path.stat().st_size > 100:
            return cache_path
        return None
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": USER_AGENT})
        if r.status_code == 200 and r.content:
            cache_path.write_bytes(r.content)
            return cache_path
    except Exception:
        pass
    if cache_path.exists() and cache_path.stat().st_size > 100:
        return cache_path
    return None


def refresh_all_avatars(user_ids: list[int], force: bool = False) -> None:
    """
    Fill missing/stale avatars.
    Batches the thumbnails API call, then downloads only the images that are
    missing or stale — so network work is minimal and parallel.
    """
    ids = [int(uid) for uid in user_ids if uid]
    if not ids:
        return

    AVATAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    size = "48x48"
    need: list[int] = []
    for uid in ids:
        cache_path = AVATAR_CACHE_DIR / f"{uid}_{size}.png"
        if cache_path.exists() and cache_path.stat().st_size > 100:
            age = time.time() - cache_path.stat().st_mtime
            if not force and age < AVATAR_CACHE_MAX_AGE:
                continue
            if force and age < 300:
                continue
        need.append(uid)

    if not need:
        return

    urls = get_avatar_headshot_urls(need, size=size)

    def one(uid: int) -> None:
        url = urls.get(uid)
        if not url:
            return
        cache_path = AVATAR_CACHE_DIR / f"{uid}_{size}.png"
        try:
            r = requests.get(url, timeout=12, headers={"User-Agent": USER_AGENT})
            if r.status_code == 200 and r.content:
                cache_path.write_bytes(r.content)
        except Exception:
            pass

    workers = min(10, max(1, len(need)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, need))

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
_LIVE_DRIVERS: list = []


def _edge_options_fast(profile_dir: str):
    """Edge options tuned for fast cold-start (login / open session)."""
    from selenium.webdriver.edge.options import Options

    options = Options()
    options.add_argument(f"--user-data-dir={profile_dir}")
    options.add_argument("--window-size=960,700")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # Startup noise / background junk
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-breakpad")
    options.add_argument("--disable-client-side-phishing-detection")
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-hang-monitor")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-prompt-on-repost")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-translate")
    options.add_argument("--metrics-recording-only")
    options.add_argument("--no-first-run")
    options.add_argument("--password-store=basic")
    options.add_argument("--use-mock-keychain")
    options.add_argument("--disable-features=TranslateUI,MediaRouter,ImprovedCookieControls,CalculateNativeWinOcclusion")
    # Faster network / rendering path (safe for Roblox web)
    options.add_argument("--enable-features=NetworkServiceInProcess2")
    options.add_argument("--disable-ipc-flooding-protection")
    options.add_argument("--renderer-process-limit=3")
    options.add_argument("--js-flags=--lite-mode")
    options.add_argument("--disable-component-update")
    options.add_argument("--disable-domain-reliability")
    options.add_argument("--disable-features=AudioServiceOutOfProcess")
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)
    # Eager: DOM ready is enough; images/scripts can finish after we inject cookies
    options.page_load_strategy = "eager"
    prefs = {
        "profile.default_content_setting_values.notifications": 2,
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        # Prefer HTTP/2 / QUIC where available
        "webkit.webprefs.loads_images_automatically": True,
    }
    options.add_experimental_option("prefs", prefs)
    return options


def _stealth_webdriver_bit(driver) -> None:
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": (
                    "Object.defineProperty(navigator, 'webdriver', "
                    "{get: () => undefined});"
                )
            },
        )
    except Exception:
        pass
    # Block common analytics / ad hosts that slow first paint (Roblox itself stays)
    try:
        driver.execute_cdp_cmd("Network.enable", {})
        driver.execute_cdp_cmd(
            "Network.setBlockedURLs",
            {
                "urls": [
                    "*google-analytics.com*",
                    "*googletagmanager.com*",
                    "*doubleclick.net*",
                    "*facebook.net*",
                    "*scorecardresearch.com*",
                    "*hotjar.com*",
                    "*sentry.io*",
                    "*fullstory.com*",
                    "*newrelic.com*",
                    "*nr-data.net*",
                ]
            },
        )
    except Exception:
        pass


def _start_edge_fast(temp_prefix: str, persist_name: str | None = None):
    from selenium import webdriver
    from selenium.webdriver.edge.service import Service

    if persist_name:
        profile_path = BROWSER_PROFILES_DIR / persist_name
        profile_path.mkdir(parents=True, exist_ok=True)
        profile_dir = str(profile_path)
    else:
        profile_dir = tempfile.mkdtemp(prefix=temp_prefix)

    options = _edge_options_fast(profile_dir)
    try:
        service = Service(log_output=os.devnull)
    except TypeError:
        service = Service()
    try:
        driver = webdriver.Edge(options=options, service=service)
    except TypeError:
        driver = webdriver.Edge(options=options)
    _stealth_webdriver_bit(driver)
    try:
        # Eager strategy + lower timeout = feel faster on good connections
        driver.set_page_load_timeout(12)
        driver.set_script_timeout(8)
    except Exception:
        pass
    _LIVE_DRIVERS.append(driver)
    return driver


def _quit_driver(driver) -> None:
    try:
        driver.quit()
    except Exception:
        pass
    try:
        _LIVE_DRIVERS.remove(driver)
    except ValueError:
        pass


def close_managed_browsers() -> None:
    """Quit Edge sessions this app started (called on exit)."""
    drivers = list(_LIVE_DRIVERS)
    _LIVE_DRIVERS.clear()
    for driver in drivers:
        try:
            driver.quit()
        except Exception:
            pass


def _inject_roblox_consent_cookies(driver) -> None:
    """
    Pre-set Roblox-only cookie-consent so the banner doesn't ask every session.
    Roblox stores consent in `RBXcb` (see their site scripts: consentCookieName).
    """
    # Accept-all style payload; categories Roblox's banner uses in the consent string
    rbxcb_value = (
        "Essential=true&Functional=true&Analytics=true&Advertising=true"
    )
    expires = int(time.time()) + 180 * 24 * 3600  # matches ~180-day site default
    consent_cookies = [
        {
            "name": "RBXcb",
            "value": rbxcb_value,
            "domain": ".roblox.com",
            "path": "/",
            "secure": True,
            "httpOnly": False,
            "expires": expires,
        },
        # Harmless extras some regional Roblox stacks still check
        {
            "name": "OptanonAlertBoxClosed",
            "value": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "domain": ".roblox.com",
            "path": "/",
            "secure": True,
            "httpOnly": False,
            "expires": expires,
        },
    ]
    try:
        driver.execute_cdp_cmd("Network.enable", {})
    except Exception:
        pass
    for c in consent_cookies:
        try:
            driver.execute_cdp_cmd("Network.setCookie", c)
        except Exception:
            pass
    # Hide leftover banner nodes on roblox.com only (doesn't touch other sites)
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": r"""
                (function () {
                  try {
                    var h = location.hostname || '';
                    if (h.indexOf('roblox.com') === -1) return;
                    var hide = function () {
                      var nodes = document.querySelectorAll(
                        '#cookie-banner-wrapper, [id*="cookie-banner"], [class*="cookie-banner"], [class*="CookieBanner"], #onetrust-banner-sdk, #onetrust-consent-sdk'
                      );
                      for (var i = 0; i < nodes.length; i++) {
                        nodes[i].style.setProperty('display', 'none', 'important');
                      }
                    };
                    if (document.readyState === 'loading') {
                      document.addEventListener('DOMContentLoaded', hide);
                    } else {
                      hide();
                    }
                    setTimeout(hide, 500);
                    setTimeout(hide, 1500);
                  } catch (e) {}
                })();
                """
            },
        )
    except Exception:
        pass


def login_with_browser(timeout_seconds: int = 300) -> Optional[dict]:
    try:
        from selenium import webdriver  # noqa: F401 — presence check
    except ImportError:
        print("[!] Missing dependency. Run: pip install selenium")
        return None

    try:
        driver = _start_edge_fast("roblox_login_", persist_name="login")
    except Exception as e:
        print(f"[!] Could not start browser: {e}")
        return None

    _inject_roblox_consent_cookies(driver)

    try:
        driver.get("https://www.roblox.com/login")
    except Exception:
        pass

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
            _quit_driver(driver)
            return None
        time.sleep(0.35)

    _quit_driver(driver)

    if not cookie_value:
        return None

    info = validate_cookie(cookie_value)
    if not info:
        return None

    return {
        "cookie": info.get("cookie", cookie_value),
        "id": info["id"],
        "name": info["name"],
        "displayName": info["displayName"],
    }


def open_browser_for_account(account: Account) -> bool:
    """Open Edge already logged in — one navigation, cookie set via CDP (no double load)."""
    try:
        from selenium import webdriver  # noqa: F401
    except ImportError:
        return False

    try:
        driver = _start_edge_fast(
            "roblox_session_",
            persist_name=f"session_{account.user_id}",
        )
    except Exception:
        return False

    try:
        # Consent first (Roblox only), then session cookie — one navigation to home
        _inject_roblox_consent_cookies(driver)
        try:
            driver.execute_cdp_cmd("Network.enable", {})
            driver.execute_cdp_cmd(
                "Network.setCookie",
                {
                    "name": ".ROBLOSECURITY",
                    "value": account.cookie,
                    "domain": ".roblox.com",
                    "path": "/",
                    "secure": True,
                    "httpOnly": True,
                },
            )
        except Exception:
            try:
                driver.get("https://www.roblox.com/favicon.ico")
                driver.add_cookie({
                    "name": ".ROBLOSECURITY",
                    "value": account.cookie,
                    "domain": ".roblox.com",
                    "path": "/",
                    "secure": True,
                    "httpOnly": True,
                })
            except Exception:
                pass

        try:
            driver.get("https://www.roblox.com/home")
        except Exception:
            pass
        return True
    except Exception:
        _quit_driver(driver)
        return False

# ---------------------------------------------------------------------------
# Auto cookie refresh
# ---------------------------------------------------------------------------
def refresh_all_cookies(accounts: list[Account]) -> tuple[int, int, list[str]]:
    """Validate cookies in parallel. One save at the end (no per-account disk writes)."""
    if not accounts:
        return 0, 0, []

    def one(acc: Account) -> tuple[int, Optional[dict]]:
        info = validate_cookie(acc.cookie, accounts=None, user_id=None)
        return acc.user_id, info

    results: dict[int, Optional[dict]] = {}
    workers = min(12, max(1, len(accounts)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(one, acc) for acc in accounts]
        for fut in as_completed(futs):
            try:
                uid, info = fut.result()
                results[uid] = info
            except Exception:
                continue

    valid = 0
    invalid: list[str] = []
    for acc in accounts:
        info = results.get(acc.user_id)
        if info:
            acc.username = info["name"]
            acc.display_name = info["displayName"]
            if info.get("cookie"):
                acc.cookie = info["cookie"]
            acc.last_validated = time.time()
            valid += 1
        else:
            invalid.append(acc.username)
    save_accounts(accounts)
    return valid, len(accounts), invalid
