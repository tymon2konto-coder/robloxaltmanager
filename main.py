#!/usr/bin/env python3
"""
Roblox Alt Manager – simple CLI tool
------------------------------------
Manage multiple Roblox accounts via .ROBLOSECURITY cookies,
validate them, and launch into games.
Usage:
python main.py
"""
from __future__ import annotations
import sys
import time
from typing import Optional
try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
except ImportError:
    # Fallback if colorama is missing
    class Fore:
        GREEN = CYAN = YELLOW = RED = MAGENTA = WHITE = RESET = ""
    class Style:
        BRIGHT = RESET_ALL = ""

from roblox_manager import (
    Account,
    load_accounts,
    save_accounts,
    validate_cookie,
    launch_account,
    enable_multi_instance,
    release_multi_instance,
    login_with_browser,
    open_browser_for_account,
    refresh_all_cookies,
    unlock,
    lock,
    is_accounts_encrypted,
    is_crypto_available,
    EncryptionError,
)
import getpass

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def clear():
    print("\n" * 2)

def header():
    print(f"{Fore.CYAN}{Style.BRIGHT}")
    print("╔══════════════════════════════════════════════════╗")
    print("║           Roblox Alt Manager (Python)            ║")
    print("║              Personal use only                   ║")
    print("╚══════════════════════════════════════════════════╝")
    print(Style.RESET_ALL)

def pause():
    input(f"\n{Fore.YELLOW}Press Enter to continue...{Style.RESET_ALL}")

def get_choice(prompt: str, valid: range | list) -> str:
    while True:
        choice = input(prompt).strip()
        if choice in [str(x) for x in valid]:
            return choice
        print(f"{Fore.RED}Invalid choice.{Style.RESET_ALL}")

# ---------------------------------------------------------------------------
# Menu actions
# ---------------------------------------------------------------------------
def list_accounts(accounts: list[Account]):
    if not accounts:
        print(f"{Fore.YELLOW}No accounts saved yet.{Style.RESET_ALL}")
        return
    print(f"\n{Fore.CYAN}{'#':<4} {'Username':<22} {'User ID':<12} {'Notes'}{Style.RESET_ALL}")
    print("-" * 60)
    for i, acc in enumerate(accounts, 1):
        notes = (acc.notes[:30] + "…") if len(acc.notes) > 30 else acc.notes
        print(f"{i:<4} {acc.username:<22} {acc.user_id:<12} {notes}")

def add_account(accounts: list[Account]):
    print(f"\n{Fore.CYAN}Add new account{Style.RESET_ALL}")
    print("Paste the full .ROBLOSECURITY cookie value.")
    print("(It usually starts with _|WARNING:-DO-NOT-SHARE-THIS...")
    print()
    cookie = input("Cookie: ").strip()
    if not cookie:
        print(f"{Fore.RED}Empty cookie, cancelled.{Style.RESET_ALL}")
        return
    
    # Clean common copy-paste issues
    if cookie.startswith(".ROBLOSECURITY="):
        cookie = cookie.split("=", 1)[1]
    cookie = cookie.strip().strip('"').strip("'")

    print(f"\n{Fore.YELLOW}Validating cookie...{Style.RESET_ALL}")
    info = validate_cookie(cookie)
    if not info:
        print(f"{Fore.RED}Cookie is invalid or expired.{Style.RESET_ALL}")
        return

    # Check for duplicates
    for acc in accounts:
        if acc.user_id == info["id"]:
            print(f"{Fore.YELLOW}Account {info['name']} is already saved (updating cookie).{Style.RESET_ALL}")
            acc.cookie = cookie
            acc.username = info["name"]
            acc.display_name = info["displayName"]
            save_accounts(accounts)
            print(f"{Fore.GREEN}Updated successfully.{Style.RESET_ALL}")
            return

    notes = input("Optional notes (press Enter to skip): ").strip()
    new_acc = Account(
        username=info["name"],
        user_id=info["id"],
        cookie=cookie,
        display_name=info["displayName"],
        notes=notes,
        added_at=time.time(),
    )
    accounts.append(new_acc)
    save_accounts(accounts)
    print(f"{Fore.GREEN}Added {info['name']} (ID: {info['id']}) successfully!{Style.RESET_ALL}")

def add_account_browser(accounts: list[Account]):
    """Open a real Chrome window, let the user log in, capture the cookie, keep browser open."""
    print(f"\n{Fore.CYAN}Add account via browser{Style.RESET_ALL}")
    print("A browser window will open.")
    print("Log in to Roblox normally — the browser stays fully usable and will NOT close.")
    print()
    result = login_with_browser(timeout_seconds=300)
    if not result:
        print(f"{Fore.RED}Could not capture a valid login.{Style.RESET_ALL}")
        return

    cookie = result["cookie"]
    user_id = result["id"]
    username = result["name"]
    display_name = result["displayName"]

    # Check for duplicates
    for acc in accounts:
        if acc.user_id == user_id:
            print(f"{Fore.YELLOW}Account {username} is already saved (updating cookie).{Style.RESET_ALL}")
            acc.cookie = cookie
            acc.username = username
            acc.display_name = display_name
            save_accounts(accounts)
            print(f"{Fore.GREEN}Updated successfully.{Style.RESET_ALL}")
            return

    notes = input("Optional notes (press Enter to skip): ").strip()
    new_acc = Account(
        username=username,
        user_id=user_id,
        cookie=cookie,
        display_name=display_name,
        notes=notes,
        added_at=time.time(),
    )
    accounts.append(new_acc)
    save_accounts(accounts)
    print(f"{Fore.GREEN}Added {username} (ID: {user_id}) successfully!{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Browser window is still open — you can keep using it.{Style.RESET_ALL}")

def remove_account(accounts: list[Account]):
    if not accounts:
        print(f"{Fore.YELLOW}No accounts to remove.{Style.RESET_ALL}")
        return
    list_accounts(accounts)
    print()
    try:
        idx = int(input("Enter number to remove (0 to cancel): ").strip())
        if idx == 0:
            return
        if 1 <= idx <= len(accounts):
            removed = accounts.pop(idx - 1)
            save_accounts(accounts)
            print(f"{Fore.GREEN}Removed {removed.username}.{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}Invalid number.{Style.RESET_ALL}")
    except ValueError:
        print(f"{Fore.RED}Invalid input.{Style.RESET_ALL}")

def revalidate_all(accounts: list[Account]):
    if not accounts:
        print(f"{Fore.YELLOW}No accounts.{Style.RESET_ALL}")
        return
    print(f"\n{Fore.CYAN}Re-validating & refreshing cookies (handles rotation)...{Style.RESET_ALL}")
    valid, total, invalid = refresh_all_cookies(accounts)
    # reload
    accounts[:] = load_accounts()
    for acc in accounts:
        if acc.username not in invalid:
            print(f"  {Fore.GREEN}✓{Style.RESET_ALL} {acc.username}")
        else:
            print(f"  {Fore.RED}✗{Style.RESET_ALL} {acc.username}  (cookie invalid/expired)")
    print(f"\n{valid}/{total} accounts still valid.")

def launch_menu(accounts: list[Account]):
    if not accounts:
        print(f"{Fore.YELLOW}No accounts saved. Add one first.{Style.RESET_ALL}")
        return
    list_accounts(accounts)
    print()
    try:
        idx = int(input("Account number to launch (0 to cancel): ").strip())
        if idx == 0:
            return
        if not (1 <= idx <= len(accounts)):
            print(f"{Fore.RED}Invalid number.{Style.RESET_ALL}")
            return
    except ValueError:
        print(f"{Fore.RED}Invalid input.{Style.RESET_ALL}")
        return

    account = accounts[idx - 1]
    place_str = input("Place ID (required): ").strip()
    if not place_str.isdigit():
        print(f"{Fore.RED}Place ID must be a number.{Style.RESET_ALL}")
        return
    place_id = int(place_str)
    job_id = input("Job ID / Server ID (optional, press Enter to skip): ").strip()
    link_code = input("Private server link code (optional, press Enter to skip): ").strip()
    success = launch_account(account, place_id, job_id=job_id, link_code=link_code, accounts=accounts)
    if success:
        print(f"{Fore.GREEN}Launch command sent. Roblox should open shortly.{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}Launch failed.{Style.RESET_ALL}")

def open_browser_menu(accounts: list[Account]):
    if not accounts:
        print(f"{Fore.YELLOW}No accounts saved. Add one first.{Style.RESET_ALL}")
        return
    list_accounts(accounts)
    print()
    try:
        idx = int(input("Account number to open in browser (0 to cancel): ").strip())
        if idx == 0:
            return
        if not (1 <= idx <= len(accounts)):
            print(f"{Fore.RED}Invalid number.{Style.RESET_ALL}")
            return
    except ValueError:
        print(f"{Fore.RED}Invalid input.{Style.RESET_ALL}")
        return

    account = accounts[idx - 1]
    open_browser_for_account(account)

def multi_instance_menu():
    print(f"\n{Fore.CYAN}Multi-Instance Mode{Style.RESET_ALL}")
    print("This holds Roblox's singleton mutex so you can open multiple clients.")
    print("Keep this program running while you use multiple accounts.")
    print()
    if enable_multi_instance():
        try:
            print(f"\n{Fore.YELLOW}Press Ctrl+C when you are finished...{Style.RESET_ALL}")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print()
            release_multi_instance()
            print(f"{Fore.GREEN}Multi-instance released.{Style.RESET_ALL}")

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
def main():
    header()
    accounts = load_accounts()
    while True:
        print(f"\n{Fore.CYAN}Main Menu{Style.RESET_ALL}")
        print("  1. List accounts")
        print("  2. Add account (paste cookie)")
        print("  3. Add account (browser login)")
        print("  4. Remove account")
        print("  5. Re-validate all cookies")
        print("  6. Launch account into a game")
        print("  7. Enable Multi-Instance (Windows)")
        print("  8. Open browser for account")
        print("  0. Exit")
        print()
        choice = get_choice("Choice: ", list(range(0, 9)))
        if choice == "0":
            print(f"\n{Fore.CYAN}Bye!{Style.RESET_ALL}")
            break
        elif choice == "1":
            list_accounts(accounts)
            pause()
        elif choice == "2":
            add_account(accounts)
            pause()
        elif choice == "3":
            add_account_browser(accounts)
            pause()
        elif choice == "4":
            remove_account(accounts)
            pause()
        elif choice == "5":
            revalidate_all(accounts)
            pause()
        elif choice == "6":
            launch_menu(accounts)
            pause()
        elif choice == "7":
            multi_instance_menu()
        elif choice == "8":
            open_browser_menu(accounts)
            pause()

def _cli_unlock() -> bool:
    if not is_crypto_available():
        print(f"{Fore.RED}Install cryptography:  pip install cryptography{Style.RESET_ALL}")
        return False
    encrypted = is_accounts_encrypted()
    if encrypted:
        print(f"{Fore.CYAN}Account vault is encrypted. Enter master password:{Style.RESET_ALL}")
        pw = getpass.getpass("Password: ")
        try:
            if unlock(pw):
                print(f"{Fore.GREEN}Unlocked.{Style.RESET_ALL}")
                return True
            print(f"{Fore.RED}Wrong password.{Style.RESET_ALL}")
            return False
        except EncryptionError as e:
            print(f"{Fore.RED}{e}{Style.RESET_ALL}")
            return False
    else:
        print(f"{Fore.CYAN}Create a master password (cookies will be encrypted on disk):{Style.RESET_ALL}")
        pw = getpass.getpass("New password: ")
        confirm = getpass.getpass("Confirm: ")
        if not pw or pw != confirm:
            print(f"{Fore.RED}Passwords do not match or empty.{Style.RESET_ALL}")
            return False
        if len(pw) < 6:
            print(f"{Fore.RED}Use at least 6 characters.{Style.RESET_ALL}")
            return False
        try:
            if unlock(pw):
                print(f"{Fore.GREEN}Vault created and encrypted.{Style.RESET_ALL}")
                return True
            return False
        except EncryptionError as e:
            print(f"{Fore.RED}{e}{Style.RESET_ALL}")
            return False


if __name__ == "__main__":
    try:
        if not _cli_unlock():
            sys.exit(1)
        main()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Interrupted.{Style.RESET_ALL}")
        release_multi_instance()
        sys.exit(0)
    finally:
        lock()