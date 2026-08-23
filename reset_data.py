#!/usr/bin/env python3
"""
Wipe personal / runtime data so this folder is safe for GitHub or sharing.
Keeps the EXE and app files. Deletes accounts, favorites, tabs, config, avatars.
"""
from __future__ import annotations
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

DEFAULT_CONFIG = {
    "theme": "dark",
    "auto_cookie_refresh": True,
    "multi_instance": False,
    "launch_delay": 3.0,
}
DEFAULT_TABS = {
    "active": "all",
    "tabs": [{"id": "all", "name": "All", "builtin": True, "accounts": []}],
}
FILES = {
    "accounts.json": [],
    "favorites.json": [],
    "tabs.json": DEFAULT_TABS,
    "config.json": DEFAULT_CONFIG,
}
DIRS = ["avatar_cache", "__pycache__"]
GLOBS = ["*.lnk", "*.tmp", "*.bak", "*.bak_test", "*.pyc", "accounts.json.tmp"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Reset personal data for clean GitHub upload")
    ap.add_argument("--yes", "-y", action="store_true")
    args = ap.parse_args()
    if not args.yes:
        print("This will permanently wipe accounts/cookies, favorites, tabs, config, avatars.")
        if input("Type YES to continue: ").strip() != "YES":
            print("Cancelled.")
            return 1
    print("Resetting…")
    for name, data in FILES.items():
        (ROOT / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"  reset  {name}")
    for name in DIRS:
        d = ROOT / name
        if d.is_dir():
            for c in list(d.iterdir()):
                if c.is_file():
                    c.unlink(missing_ok=True)
                else:
                    shutil.rmtree(c, ignore_errors=True)
        else:
            d.mkdir(parents=True, exist_ok=True)
        print(f"  cleared {name}/")
    for pattern in GLOBS:
        for p in ROOT.glob(pattern):
            if p.is_file():
                p.unlink(missing_ok=True)
                print(f"  deleted {p.name}")
    print("Done. Safe for GitHub.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
