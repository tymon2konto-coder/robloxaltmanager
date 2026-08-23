#!/usr/bin/env python3
"""
Reset all personal / runtime data so the folder is safe to push to GitHub.

Keeps application code. Deletes or empties:
  - accounts.json          (cookies / vault)
  - favorites.json
  - tabs.json
  - config.json            (back to defaults)
  - avatar_cache/*
  - __pycache__ / *.pyc
  - temporary files
  - personal shortcuts (e.g. Brave.lnk)

Usage:
  python reset_data.py
  python reset_data.py --yes   # skip confirmation
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
    "tabs": [
        {"id": "all", "name": "All", "builtin": True, "accounts": []},
    ],
}

FILES_TO_RESET = {
    "accounts.json": [],
    "favorites.json": [],
    "tabs.json": DEFAULT_TABS,
    "config.json": DEFAULT_CONFIG,
}

DIRS_TO_CLEAR = [
    "avatar_cache",
    "__pycache__",
]

# Personal / machine-specific junk
EXTRA_DELETE_GLOBS = [
    "*.lnk",
    "*.tmp",
    "*.bak",
    "*.bak_test",
    "*.pyc",
    "accounts.json.tmp",
]


def confirm() -> bool:
    print("This will permanently wipe:")
    print("  • all accounts / cookies (encrypted vault)")
    print("  • favorites, tabs, config")
    print("  • avatar cache and __pycache__")
    print("  • personal shortcuts (.lnk)")
    print()
    reply = input("Type YES to continue: ").strip()
    return reply == "YES"


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"  reset  {path.name}")


def clear_dir(path: Path) -> int:
    if not path.is_dir():
        path.mkdir(parents=True, exist_ok=True)
        print(f"  empty  {path.name}/")
        return 0
    n = 0
    for child in list(path.iterdir()):
        if child.is_file():
            child.unlink(missing_ok=True)
            n += 1
        elif child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
            n += 1
    print(f"  cleared {path.name}/  ({n} items)")
    return n


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset personal data for clean GitHub upload")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    args = parser.parse_args()

    if not args.yes and not confirm():
        print("Cancelled.")
        return 1

    print("\nResetting…")

    for name, data in FILES_TO_RESET.items():
        write_json(ROOT / name, data)

    for name in DIRS_TO_CLEAR:
        clear_dir(ROOT / name)

    for pattern in EXTRA_DELETE_GLOBS:
        for p in ROOT.glob(pattern):
            if p.is_file():
                p.unlink(missing_ok=True)
                print(f"  deleted {p.name}")

    # Nested pycache under any subfolder
    for pyc in ROOT.rglob("__pycache__"):
        if pyc.is_dir() and pyc != ROOT / "__pycache__":
            shutil.rmtree(pyc, ignore_errors=True)
            print(f"  removed {pyc.relative_to(ROOT)}")

    print("\nDone. Folder is clean for GitHub.")
    print("Remember: never commit a real accounts.json with cookies.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
