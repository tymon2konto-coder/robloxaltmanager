#!/usr/bin/env python3
"""
Roblox Alt Manager - GUI with 24x24 avatars, favorites, cookie rotation
"""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import os
import sys
import time
import threading
import re
from pathlib import Path
from typing import Optional
from roblox_manager import (
    Account,
    FavoriteGame,
    load_accounts,
    save_accounts,
    load_favorites,
    save_favorites,
    validate_cookie,
    launch_account,
    enable_multi_instance,
    release_multi_instance,
    find_roblox_pids,
    login_with_browser,
    open_browser_for_account,
    load_config,
    save_config,
    load_tabs,
    save_tabs,
    download_avatar,
    refresh_all_avatars,
    refresh_all_cookies,
    get_place_info,
    get_online_friends,
    get_presences,
    get_public_servers,
    pick_fast_server,
    pick_small_server,
    close_managed_browsers,
    unlock,
    lock,
    is_accounts_encrypted,
    is_crypto_available,
    EncryptionError,
    change_password,
)
import uuid


class ThemedScrollbar(tk.Frame):
    """
    Fully drawn vertical scrollbar. Windows ignores colors on native
    tk/ttk Scrollbar arrow buttons; this avoids the white OS chrome.
    API-compatible: .set(first, last) and command=widget.yview
    """

    def __init__(self, parent, command=None, colors=None, width: int = 14, **kw):
        self._colors = colors or {
            "btn_bg": "#505050",
            "frame_bg": "#383838",
            "select_bg": "#0078d7",
            "fg": "#ffffff",
        }
        super().__init__(parent, width=width, **kw)
        self.command = command
        self._first = 0.0
        self._last = 1.0
        self._drag_y = None
        self._is_themed_scrollbar = True
        self.pack_propagate(False)
        self.grid_propagate(False)
        self.configure(width=width)

        c = self._colors
        btn_kw = dict(
            width=1,
            bd=0,
            relief=tk.FLAT,
            highlightthickness=0,
            font=("Segoe UI", 7),
            cursor="hand2",
        )
        # Never use theme select_bg here — that made arrows look purple on every theme
        self.btn_up = tk.Button(
            self, text="▲", command=self._scroll_up,
            bg=c["btn_bg"], fg=c["fg"],
            activebackground=c["btn_bg"],
            activeforeground=c["fg"],
            **btn_kw,
        )
        self.btn_up.pack(side=tk.TOP, fill=tk.X)
        self.canvas = tk.Canvas(
            self, width=width, highlightthickness=0, bd=0,
            bg=c["frame_bg"], cursor="hand2",
        )
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.btn_down = tk.Button(
            self, text="▼", command=self._scroll_down,
            bg=c["btn_bg"], fg=c["fg"],
            activebackground=c["btn_bg"],
            activeforeground=c["fg"],
            **btn_kw,
        )
        self.btn_down.pack(side=tk.BOTTOM, fill=tk.X)

        self.canvas.bind("<Button-1>", self._on_trough_click)
        self.canvas.bind("<B1-Motion>", self._on_thumb_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_thumb_release)
        self.canvas.bind("<Configure>", lambda e: self._draw_thumb())
        self._thumb_id = None
        self._draw_thumb()

    def apply_theme_colors(self, colors: dict):
        self._colors = {
            "btn_bg": colors.get("btn_bg", "#505050"),
            "frame_bg": colors.get("frame_bg", "#383838"),
            "fg": colors.get("btn_fg") or colors.get("fg", "#ffffff"),
        }
        c = self._colors
        self.configure(bg=c["frame_bg"])
        for btn in (self.btn_up, self.btn_down):
            btn.configure(
                bg=c["btn_bg"], fg=c["fg"],
                activebackground=c["btn_bg"],
                activeforeground=c["fg"],
            )
        self.canvas.configure(bg=c["frame_bg"])
        self._draw_thumb()

    def set(self, first, last):
        try:
            self._first = float(first)
            self._last = float(last)
        except (TypeError, ValueError):
            self._first, self._last = 0.0, 1.0
        self._draw_thumb()

    def _draw_thumb(self):
        self.canvas.delete("all")
        h = max(self.canvas.winfo_height(), 1)
        w = max(self.canvas.winfo_width(), 1)
        span = max(self._last - self._first, 0.05)
        # Thumb height proportional to visible fraction
        thumb_h = max(int(h * span), 18)
        max_top = max(h - thumb_h, 0)
        top = int(self._first * max_top) if max_top else 0
        c = self._colors
        # trough already canvas bg
        pad = 2
        self._thumb_id = self.canvas.create_rectangle(
            pad, top, w - pad, top + thumb_h,
            fill=c["btn_bg"], outline=c["btn_bg"], width=0,
        )
        self._thumb_top = top
        self._thumb_h = thumb_h
        self._trough_h = h

    def _scroll_up(self):
        if self.command:
            self.command("scroll", -1, "units")

    def _scroll_down(self):
        if self.command:
            self.command("scroll", 1, "units")

    def _on_trough_click(self, event):
        if self._thumb_h >= self._trough_h:
            return
        # Click above/below thumb → page; on thumb → start drag
        if self._thumb_top <= event.y <= self._thumb_top + self._thumb_h:
            self._drag_y = event.y - self._thumb_top
            return
        if self.command:
            if event.y < self._thumb_top:
                self.command("scroll", -1, "pages")
            else:
                self.command("scroll", 1, "pages")

    def _on_thumb_drag(self, event):
        if self._drag_y is None:
            return
        h = self._trough_h
        thumb_h = self._thumb_h
        max_top = max(h - thumb_h, 1)
        top = max(0, min(event.y - self._drag_y, max_top))
        fraction = top / max_top
        if self.command:
            self.command("moveto", fraction)

    def _on_thumb_release(self, event):
        self._drag_y = None


def _app_dir_path() -> Path:
    """Writable app directory (next to the EXE when frozen)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _resource_dir() -> Path:
    """
    Directory that holds bundled read-only assets (icons).
    PyInstaller onedir/onefile extracts/adds data under sys._MEIPASS;
    fall back to the writable app dir when not frozen.
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _set_windows_app_id():
    """Make Windows taskbar use our icon instead of python.exe / pythonw.exe."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "RobloxAltManager.App.1"
        )
    except Exception:
        pass


# Named mutex handle kept for process lifetime (Windows single-instance)
_SINGLE_INSTANCE_MUTEX = None
_WINDOW_TITLE = "Roblox Alt Manager"


def _activate_existing_window() -> bool:
    """Find the running main window (even if tray-hidden) and bring it forward."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, _WINDOW_TITLE)
        if not hwnd:
            return False
        # Restore if minimized / show if withdrawn to tray
        SW_RESTORE = 9
        SW_SHOW = 5
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.ShowWindow(hwnd, SW_SHOW)
        user32.SetForegroundWindow(hwnd)
        # Nudge topmost briefly so it actually comes forward on modern Windows
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        return True
    except Exception:
        return False


def _ensure_single_instance() -> bool:
    """
    Return True if this process should continue (we are the only instance).
    Return False if another instance was found and activated (caller should exit).
    """
    global _SINGLE_INSTANCE_MUTEX
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # Local mutex — one per user session
            name = "Local\\RobloxAltManager_SingleInstance"
            handle = kernel32.CreateMutexW(None, False, name)
            already = kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS
            _SINGLE_INSTANCE_MUTEX = handle
            if already:
                _activate_existing_window()
                return False
            return True
        except Exception:
            return True
    # Non-Windows: lock file
    try:
        lock_path = _app_dir_path() / ".roblox_alt_manager.lock"
        if lock_path.exists():
            try:
                old_pid = int(lock_path.read_text().strip())
                # If process still alive, refuse (best-effort)
                try:
                    os.kill(old_pid, 0)
                    return False
                except OSError:
                    pass
            except Exception:
                pass
        lock_path.write_text(str(os.getpid()))
        return True
    except Exception:
        return True


def _apply_window_icon(window: tk.Misc) -> None:
    """
    Set title-bar / alt-tab icon on a Tk window.
    Uses a real multi-size .ico (iconbitmap) plus a sharp PNG via PIL (iconphoto).
    Keeps PhotoImage refs on the window so GC does not drop them.
    Looks in the bundled resource dir first (PyInstaller), then next to the EXE.
    """
    search_dirs = []
    try:
        search_dirs.append(_resource_dir())
    except Exception:
        pass
    try:
        search_dirs.append(_app_dir_path())
    except Exception:
        pass

    ico = None
    for base in search_dirs:
        candidate = (base / "app_icon.ico").resolve()
        if candidate.is_file():
            ico = candidate
            break
    if ico is not None:
        try:
            window.iconbitmap(default=str(ico))
        except Exception:
            try:
                window.iconbitmap(str(ico))
            except Exception:
                pass

    # Prefer PIL resize (LANCZOS) over Tk subsample — subsample looks soft/blurry
    photos = []
    try:
        from PIL import Image, ImageTk

        src_path = None
        for base in search_dirs:
            p = base / "app_icon.png"
            if p.is_file():
                src_path = p
                break
        if src_path is not None:
            src = Image.open(src_path).convert("RGBA")
            for size in (32, 16):
                im = src.resize((size, size), Image.Resampling.LANCZOS)
                photos.append(ImageTk.PhotoImage(im, master=window))
    except Exception:
        photos = []

    if not photos:
        for name in ("app_icon_32.png", "app_icon_48.png", "app_icon_64.png"):
            path = None
            for base in search_dirs:
                p = (base / name).resolve()
                if p.is_file():
                    path = p
                    break
            if path is None:
                continue
            try:
                photos.append(tk.PhotoImage(file=str(path), master=window))
                break
            except Exception:
                continue

    if photos:
        window._app_icon_photos = photos  # type: ignore[attr-defined]
        try:
            window.iconphoto(True, *photos)
        except Exception:
            try:
                window.iconphoto(True, photos[0])
            except Exception:
                pass


class RobloxAltManagerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("Roblox Alt Manager")
        self.geometry("980x560")
        self.resizable(False, False)
        
        self.config = load_config()
        self.current_theme = self.config.get("theme", "dark")
        self.auto_refresh = self.config.get("auto_cookie_refresh", True)
        self.multi_instance_active = False
        
        self.accounts = load_accounts()
        self.favorites = load_favorites()
        self.tabs_data = load_tabs()
        self.active_tab_id = self.tabs_data.get("active", "all")
        self._photo_images = {}
        self._refresh_job = None
        self._tab_buttons = {}  # id -> widget
        self._online_friends_cache = []  # list of dicts from get_online_friends
        self._online_fetch_token = 0  # invalidate stale async fetches
        self._selected_account_for_online = None  # Account currently driving online list
        self._tray_icon = None
        self._tray_thread = None
        self._app_icon_photo = None  # keep ref so GC doesn't drop window icon
        self._presence_by_uid: dict = {}  # user_id -> presence type int
        self._search_query = ""
        self._online_poll_job = None
        self._presence_poll_job = None
        self._search_job = None
        self._launch_running = False
        self._launch_cancel = threading.Event()
        
        # entry_* / select_bg used so themes apply consistently everywhere
        self.colors = {
            "dark": {
                "bg": "#2b2b2b", "fg": "#ffffff", "frame_bg": "#383838",
                "btn_bg": "#505050", "btn_fg": "#ffffff",
                "tree_bg": "#333333", "tree_fg": "#ffffff",
                "entry_bg": "#3a3a3a", "entry_fg": "#ffffff",
                "select_bg": "#0078d7", "select_fg": "#ffffff",
            },
            "light": {
                "bg": "#f0f0f0", "fg": "#000000", "frame_bg": "#e0e0e0",
                "btn_bg": "#d0d0d0", "btn_fg": "#000000",
                "tree_bg": "#ffffff", "tree_fg": "#000000",
                "entry_bg": "#ffffff", "entry_fg": "#000000",
                "select_bg": "#0078d7", "select_fg": "#ffffff",
            },
            # Deep dark purple — not pastel / light lilac
            "purple": {
                "bg": "#1a1028", "fg": "#f3eaff", "frame_bg": "#2a1a40",
                "btn_bg": "#4a3270", "btn_fg": "#f3eaff",
                "tree_bg": "#221433", "tree_fg": "#f3eaff",
                "entry_bg": "#2e1c45", "entry_fg": "#f3eaff",
                "select_bg": "#7c5cbf", "select_fg": "#ffffff",
            },
        }
        if self.current_theme not in self.colors:
            self.current_theme = "dark"
        
        self.style = ttk.Style()
        self.apply_theme()
        self._set_window_icon()
        self.create_widgets()
        
        # Restore multi-instance from saved setting (works even if Roblox is already open)
        if self.config.get("multi_instance", False):
            if enable_multi_instance():
                self.multi_instance_active = True
                self.status_var.set("Multi-instance ACTIVE")
            else:
                # Keep the preference saved; user can retry from Settings
                self.status_var.set("Multi-instance saved but failed to enable")
        
        # Close (X) hides to system tray; Exit from tray quits for real
        self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        
        # Show accounts immediately (cached avatars only); refresh avatars in background
        self.update_account_list()
        self.status_var.set("Ready")
        self.after(50, self._startup_avatar_refresh)
        self.after(100, self._start_tray)
        self.after(1500, self._refresh_account_presences)
        self.after(10_000, self._online_friends_poll_tick)
        self.after(8_000, self._presence_poll_tick)
        # Re-check presence when the window is focused again (e.g. after alt-tab)
        self.bind("<FocusIn>", self._on_app_focus_in)
        
        if self.auto_refresh:
            self.schedule_cookie_refresh()
        
        # Ctrl+F → focus search
        self.bind_all("<Control-f>", self._focus_search)
        self.bind_all("<Control-F>", self._focus_search)

        # Ask about saved Job ID after UI is up (only if one was saved)
        self.after(350, self._prompt_saved_job_id)

    def _prompt_saved_job_id(self):
        """Windows-style Yes/No: restore last Job ID if the user wants it."""
        saved = str(self.config.get("active_job_id") or "").strip()
        if not saved:
            return
        preview = saved if len(saved) <= 48 else saved[:45] + "..."
        if messagebox.askyesno(
            "Load saved Job ID?",
            f"Load saved job id?\n\n{preview}",
            parent=self,
        ):
            self.job_id_entry.delete(0, tk.END)
            self.job_id_entry.insert(0, saved)
            self.status_var.set("Loaded saved Job ID")
        # No → leave field empty; value stays in config until they save a new one

    def _app_dir(self) -> Path:
        if getattr(sys, "frozen", False):
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parent

    def _set_window_icon(self):
        """Title-bar + taskbar icon (not the Python feather)."""
        _apply_window_icon(self)
        
    def _make_scrollbar(self, parent, orient="vertical", command=None):
        """Custom-drawn scrollbar (native Windows ones stay white no matter what)."""
        c = self.colors.get(self.current_theme) or self.colors["dark"]
        return ThemedScrollbar(parent, command=command, colors=c, width=14)

    def apply_theme(self):
        theme_colors = self.colors.get(self.current_theme) or self.colors["dark"]
        self.configure(bg=theme_colors["bg"])
        self.style.theme_use("default")
        self.style.configure(
            "Treeview",
            background=theme_colors["tree_bg"],
            foreground=theme_colors["tree_fg"],
            fieldbackground=theme_colors["tree_bg"],
            rowheight=28,
        )
        self.style.configure(
            "Treeview.Heading",
            background=theme_colors["btn_bg"],
            foreground=theme_colors["btn_fg"],
        )
        self.style.map(
            "Treeview",
            background=[("selected", theme_colors.get("select_bg", "#0078d7"))],
            foreground=[("selected", theme_colors.get("select_fg", "#ffffff"))],
        )
        self.style.configure(
            "TCombobox",
            fieldbackground=theme_colors.get("entry_bg", theme_colors["tree_bg"]),
            background=theme_colors["btn_bg"],
            foreground=theme_colors.get("entry_fg", theme_colors["fg"]),
        )
        self.style.configure(
            "TLabel",
            background=theme_colors["frame_bg"],
            foreground=theme_colors["fg"],
        )
        self.style.configure(
            "TFrame",
            background=theme_colors["frame_bg"],
        )
        self.style.configure(
            "TButton",
            background=theme_colors["btn_bg"],
            foreground=theme_colors["btn_fg"],
        )

    def toggle_theme(self):
        order = ["dark", "purple", "light"]
        try:
            idx = order.index(self.current_theme)
        except ValueError:
            idx = 0
        self.current_theme = order[(idx + 1) % len(order)]
        self.config["theme"] = self.current_theme
        save_config(self.config)
        self.apply_theme()
        self.update_widget_colors(self, self.colors[self.current_theme])
        if hasattr(self, "tab_bar"):
            self._rebuild_tab_bar()

    def update_widget_colors(self, widget, colors):
        widget_type = widget.winfo_class()
        try:
            if widget_type in ("Frame", "TFrame"):
                widget.configure(bg=colors["bg"] if widget is self else colors["frame_bg"])
            elif widget_type in ("Labelframe", "LabelFrame", "TLabelframe"):
                widget.configure(bg=colors["frame_bg"], fg=colors["fg"])
            elif widget_type == "Label":
                # Keep status/labels readable; don't force button colors on all labels
                widget.configure(bg=colors["frame_bg"], fg=colors["fg"])
            elif widget_type == "Button":
                # Preserve intentional green/blue action buttons
                try:
                    cur = str(widget.cget("bg")).lower()
                except Exception:
                    cur = ""
                special = cur in ("#4caf50", "#2563eb", "#7c3aed")
                if not special:
                    widget.configure(bg=colors["btn_bg"], fg=colors["btn_fg"])
            elif widget_type in ("Entry", "TEntry"):
                widget.configure(
                    bg=colors.get("entry_bg", colors["tree_bg"]),
                    fg=colors.get("entry_fg", colors["fg"]),
                    insertbackground=colors.get("entry_fg", colors["fg"]),
                )
            elif widget_type == "Listbox":
                widget.configure(
                    bg=colors["tree_bg"],
                    fg=colors["tree_fg"],
                    selectbackground=colors.get("select_bg", "#0078d7"),
                    selectforeground=colors.get("select_fg", "#ffffff"),
                )
            elif widget_type == "Checkbutton":
                widget.configure(
                    bg=colors["frame_bg"],
                    fg=colors["fg"],
                    selectcolor=colors["btn_bg"],
                    activebackground=colors["frame_bg"],
                    activeforeground=colors["fg"],
                )
            elif getattr(widget, "_is_themed_scrollbar", False):
                widget.apply_theme_colors(colors)
                return  # children handled inside
            elif widget_type == "Toplevel":
                widget.configure(bg=colors["bg"])
        except Exception:
            pass
        for child in widget.winfo_children():
            self.update_widget_colors(child, colors)

    def create_widgets(self):
        theme_colors = self.colors[self.current_theme]
        
        # Top buttons
        top_frame = tk.Frame(self, bg=theme_colors["frame_bg"], pady=5)
        top_frame.pack(fill="x", padx=5)
        
        tk.Button(
            top_frame, text="Add Account (Browser)", command=self.add_account_browser,
            width=20, bg=theme_colors["btn_bg"], fg=theme_colors["btn_fg"],
        ).pack(side="left", padx=2)
        tk.Button(
            top_frame, text="Add Account (Cookie)", command=self.add_account_cookie,
            width=18, bg=theme_colors["btn_bg"], fg=theme_colors["btn_fg"],
        ).pack(side="left", padx=2)
        tk.Button(
            top_frame, text="Remove Selected", command=self.remove_selected,
            width=15, bg=theme_colors["btn_bg"], fg=theme_colors["btn_fg"],
        ).pack(side="left", padx=2)
        tk.Button(
            top_frame, text="Validate / Refresh Cookies", command=self.validate_all,
            width=22, bg=theme_colors["btn_bg"], fg=theme_colors["btn_fg"],
        ).pack(side="left", padx=2)
        
        tk.Button(
            top_frame, text="⚙ Settings", command=self.open_settings,
            width=10, bg=theme_colors["btn_bg"], fg=theme_colors["btn_fg"],
        ).pack(side="right", padx=2)
        
        # Main content: accounts left, favorites right
        content = tk.Frame(self, bg=theme_colors["bg"])
        content.pack(fill="both", expand=True, padx=5, pady=2)
        
        # --- Account list ---
        list_frame = tk.Frame(content, bg=theme_colors["frame_bg"])
        list_frame.pack(side="left", fill="both", expand=True)
        
        # Tab bar row: tabs on the left, compact search on the far right
        tab_row = tk.Frame(list_frame, bg=theme_colors["frame_bg"])
        tab_row.pack(fill="x", padx=2, pady=(2, 0))
        self.tab_bar = tk.Frame(tab_row, bg=theme_colors["frame_bg"])
        self.tab_bar.pack(side="left", fill="x", expand=True)
        self._rebuild_tab_bar()
        
        self.search_var = tk.StringVar()
        self.search_entry = tk.Entry(
            tab_row,
            textvariable=self.search_var,
            width=14,
            bg=theme_colors["tree_bg"],
            fg=theme_colors["tree_fg"],
            insertbackground=theme_colors["fg"],
            relief=tk.FLAT,
            font=("Segoe UI", 9),
        )
        self.search_entry.pack(side="right", padx=(4, 2), pady=2, ipady=2)
        self.search_entry.insert(0, "")
        self._search_placeholder = "Search"
        self.search_entry.insert(0, self._search_placeholder)
        self.search_entry.configure(fg="#888888")
        self.search_entry.bind("<FocusIn>", self._search_focus_in)
        self.search_entry.bind("<FocusOut>", self._search_focus_out)
        self.search_entry.bind("<KeyRelease>", self._on_search_key)
        self.search_entry.bind("<Escape>", self._search_clear)
        
        # Order: icon | Display Name | Username | User ID | Notes
        columns = ("Display Name", "Username", "User ID", "Notes")
        self.tree = ttk.Treeview(
            list_frame, columns=columns, show="tree headings", selectmode="extended",
        )
        
        self.tree.heading("#0", text="")
        self.tree.heading("Display Name", text="Display Name")
        self.tree.heading("Username", text="Username")
        self.tree.heading("User ID", text="User ID")
        self.tree.heading("Notes", text="Notes")
        
        # Icon col: optional presence dot drawn into the avatar image (left of headshot)
        self.tree.column("#0", width=48, minwidth=44, stretch=False, anchor="w")
        self.tree.column("Display Name", width=140, minwidth=80)
        self.tree.column("Username", width=140, minwidth=100)
        self.tree.column("User ID", width=100, minwidth=80)
        self.tree.column("Notes", width=160, minwidth=80)
        
        self.tree_scrollbar = self._make_scrollbar(
            list_frame, orient="vertical", command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=self.tree_scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree_scrollbar.pack(side="right", fill="y")
        
        # Bind once (not on every list refresh)
        self._drag = {"item": None, "y": 0, "active": False}
        self.tree.bind("<ButtonPress-1>", self.on_tree_press)
        self.tree.bind("<B1-Motion>", self.on_tree_motion)
        self.tree.bind("<ButtonRelease-1>", self.on_tree_release)
        self.tree.bind("<Double-Button-1>", self.on_tree_double_click)
        self.tree.bind("<Button-3>", self.on_tree_right_click)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        
        # --- Right panel: favorites (top) + online friends (bottom), ~50/50 ---
        right_panel = tk.Frame(content, bg=theme_colors["bg"])
        right_panel.pack(side="right", fill="both", padx=(6, 0))
        right_panel.rowconfigure(0, weight=1)
        right_panel.rowconfigure(1, weight=1)
        right_panel.columnconfigure(0, weight=1)
        
        fav_frame = tk.LabelFrame(
            right_panel, text="  ★ Favorite Games  ",
            bg=theme_colors["frame_bg"], fg=theme_colors["fg"],
            padx=4, pady=4,
        )
        fav_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 3))
        
        self.fav_list = tk.Listbox(
            fav_frame, width=32, height=8,
            bg=theme_colors["tree_bg"], fg=theme_colors["tree_fg"],
            selectbackground="#0078d7", selectforeground="#ffffff",
            activestyle="none", font=("Segoe UI", 9),
        )
        self.fav_list.pack(fill="both", expand=True, pady=(0, 4))
        self.fav_list.bind("<Double-Button-1>", self.on_fav_double_click)
        
        fav_btn_row = tk.Frame(fav_frame, bg=theme_colors["frame_bg"])
        fav_btn_row.pack(fill="x")
        
        tk.Button(
            fav_btn_row, text="+ Add", command=self.add_favorite,
            width=8, bg=theme_colors["btn_bg"], fg=theme_colors["btn_fg"],
        ).pack(side="left", padx=1)
        tk.Button(
            fav_btn_row, text="Use", command=self.use_favorite,
            width=8, bg="#4CAF50", fg="white",
        ).pack(side="left", padx=1)
        tk.Button(
            fav_btn_row, text="Remove", command=self.remove_favorite,
            width=8, bg=theme_colors["btn_bg"], fg=theme_colors["btn_fg"],
        ).pack(side="left", padx=1)
        
        online_frame = tk.LabelFrame(
            right_panel, text="  Online Friends  ",
            bg=theme_colors["frame_bg"], fg=theme_colors["fg"],
            padx=4, pady=4,
        )
        online_frame.grid(row=1, column=0, sticky="nsew", pady=(3, 0))
        
        self.online_list = tk.Listbox(
            online_frame, width=32, height=8,
            bg=theme_colors["tree_bg"], fg=theme_colors["tree_fg"],
            selectbackground="#0078d7", selectforeground="#ffffff",
            activestyle="none", font=("Segoe UI", 9),
        )
        self.online_list.pack(fill="both", expand=True, pady=(0, 4))
        self.online_list.bind("<Double-Button-1>", self.on_online_double_click)
        
        online_btn_row = tk.Frame(online_frame, bg=theme_colors["frame_bg"])
        online_btn_row.pack(fill="x")
        
        tk.Button(
            online_btn_row, text="Join", command=self.join_online_friend,
            width=10, bg="#4CAF50", fg="white",
        ).pack(side="left", padx=1)
        tk.Button(
            online_btn_row, text="Refresh", command=self.refresh_online_friends,
            width=10, bg=theme_colors["btn_bg"], fg=theme_colors["btn_fg"],
        ).pack(side="left", padx=1)
        
        # Bottom launch bar
        bottom_frame = tk.Frame(self, bg=theme_colors["frame_bg"], pady=5)
        bottom_frame.pack(fill="x", padx=5)
        
        tk.Label(
            bottom_frame, text="Place ID:",
            bg=theme_colors["frame_bg"], fg=theme_colors["fg"],
        ).pack(side="left", padx=2)
        _entry_kw = dict(
            bg=theme_colors.get("entry_bg", theme_colors["tree_bg"]),
            fg=theme_colors.get("entry_fg", theme_colors["fg"]),
            insertbackground=theme_colors.get("entry_fg", theme_colors["fg"]),
        )
        self.place_id_entry = tk.Entry(bottom_frame, width=16, **_entry_kw)
        self.place_id_entry.pack(side="left", padx=2)
        self.place_id_entry.insert(0, str(self.config.get("active_place_id") or ""))
        self.place_id_entry.bind("<FocusOut>", self._save_launch_fields)
        self.place_id_entry.bind("<Return>", self._save_launch_fields)
        
        tk.Label(
            bottom_frame, text="Job ID:",
            bg=theme_colors["frame_bg"], fg=theme_colors["fg"],
        ).pack(side="left", padx=2)
        self.job_id_entry = tk.Entry(bottom_frame, width=16, **_entry_kw)
        self.job_id_entry.pack(side="left", padx=2)
        # Job ID is NOT auto-filled — startup prompt asks if a saved one exists
        self.job_id_entry.bind("<FocusOut>", self._save_launch_fields)
        self.job_id_entry.bind("<Return>", self._save_launch_fields)
        
        tk.Label(
            bottom_frame, text="Link Code:",
            bg=theme_colors["frame_bg"], fg=theme_colors["fg"],
        ).pack(side="left", padx=2)
        self.link_code_entry = tk.Entry(bottom_frame, width=16, **_entry_kw)
        self.link_code_entry.pack(side="left", padx=2)
        self.link_code_entry.insert(0, str(self.config.get("active_link_code") or ""))
        self.link_code_entry.bind("<FocusOut>", self._save_launch_fields)
        self.link_code_entry.bind("<Return>", self._save_launch_fields)
        
        tk.Button(
            bottom_frame, text="Servers", command=self.open_server_browser,
            width=9, bg=theme_colors["btn_bg"], fg=theme_colors["btn_fg"],
        ).pack(side="left", padx=(8, 2))
        
        tk.Button(
            bottom_frame, text="Launch Selected", command=self.launch_selected,
            bg="#4CAF50", fg="white", width=15,
        ).pack(side="right", padx=5)
        tk.Button(
            bottom_frame, text="Open Browser", command=self.open_browser_selected,
            width=15, bg=theme_colors["btn_bg"], fg=theme_colors["btn_fg"],
        ).pack(side="right", padx=5)

        self.status_var = tk.StringVar(value="Ready")
        status_bar = tk.Label(
            self, textvariable=self.status_var, bd=1, relief=tk.SUNKEN,
            anchor=tk.W, bg=theme_colors["frame_bg"], fg=theme_colors["fg"],
        )
        status_bar.pack(side="bottom", fill="x")
        
        self.update_favorites_list()
        self._set_online_list_message("Select an account to see online friends")

    # ------------------------------------------------------------------
    # Startup: force avatar refresh every launch
    # ------------------------------------------------------------------
    def _startup_avatar_refresh(self):
        """Fill missing avatars only — never force-redownload the whole set."""
        def worker():
            ids = [a.user_id for a in self.accounts if a.user_id]
            if ids:
                refresh_all_avatars(ids, force=False)

            def done():
                self._refresh_avatar_images_only()
                if self.multi_instance_active:
                    self.status_var.set("Multi-instance ACTIVE")
                else:
                    self.status_var.set("Ready")

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _refresh_avatar_images_only(self):
        """Update tree row images without clearing text columns (instant list)."""
        for iid in self.tree.get_children():
            vals = self.tree.item(iid, "values")
            if not vals or len(vals) < 3:
                continue
            try:
                uid = int(vals[2])  # User ID column
            except (TypeError, ValueError):
                continue
            ptype = int(self._presence_by_uid.get(uid, 0) or 0)
            img = self._load_avatar_image(uid, presence_type=ptype)
            self.tree.item(iid, text="", image=img if img else "")

    # ------------------------------------------------------------------
    # Favorites
    # ------------------------------------------------------------------
    def update_favorites_list(self):
        self.fav_list.delete(0, tk.END)
        for g in self.favorites:
            self.fav_list.insert(tk.END, f"{g.name}  ({g.place_id})")

    def add_favorite(self):
        raw = simpledialog.askstring(
            "Add Favorite Game",
            "Enter Place ID (or full roblox.com/games/... URL):",
            parent=self,
        )
        if not raw:
            return
        m = re.search(r"(\d{5,})", raw.strip())
        if not m:
            messagebox.showerror("Error", "Could not find a Place ID.")
            return
        place_id = int(m.group(1))
        
        # Already favorited?
        if any(g.place_id == place_id for g in self.favorites):
            messagebox.showinfo("Info", "That game is already in favorites.")
            return
        
        self.status_var.set(f"Looking up place {place_id}...")
        self.update()
        
        def worker():
            info = get_place_info(place_id)
            def done():
                if not info:
                    messagebox.showerror(
                        "Error",
                        f"Could not fetch info for place {place_id}.\n"
                        "Check the ID and your internet connection.",
                    )
                    self.status_var.set("Ready")
                    return
                fav = FavoriteGame(
                    place_id=info["place_id"],
                    name=info["name"],
                    universe_id=info.get("universe_id", 0),
                    added_at=time.time(),
                )
                self.favorites.append(fav)
                save_favorites(self.favorites)
                self.update_favorites_list()
                self.status_var.set(f"Added favorite: {fav.name}")
                messagebox.showinfo("Favorite Added", f"{fav.name}\nPlace ID: {fav.place_id}")
            self.after(0, done)
        threading.Thread(target=worker, daemon=True).start()

    def remove_favorite(self):
        sel = self.fav_list.curselection()
        if not sel:
            messagebox.showwarning("Warning", "Select a favorite first.")
            return
        idx = sel[0]
        name = self.favorites[idx].name
        if messagebox.askyesno("Remove Favorite", f"Remove '{name}'?"):
            self.favorites.pop(idx)
            save_favorites(self.favorites)
            self.update_favorites_list()
            self.status_var.set(f"Removed favorite: {name}")

    def use_favorite(self):
        sel = self.fav_list.curselection()
        if not sel:
            messagebox.showwarning("Warning", "Select a favorite first.")
            return
        g = self.favorites[sel[0]]
        self.place_id_entry.delete(0, tk.END)
        self.place_id_entry.insert(0, str(g.place_id))
        self._save_launch_fields()
        self.status_var.set(f"Loaded: {g.name} ({g.place_id})")

    def _save_launch_fields(self, event=None):
        """Persist Place ID / Job ID / Link Code so they restore on next startup."""
        self.config["active_place_id"] = self.place_id_entry.get().strip()
        self.config["active_job_id"] = self.job_id_entry.get().strip()
        self.config["active_link_code"] = self.link_code_entry.get().strip()
        save_config(self.config)

    # ------------------------------------------------------------------
    # Online friends (right panel, bottom half)
    # ------------------------------------------------------------------
    def _set_online_list_message(self, message: str):
        self.online_list.delete(0, tk.END)
        self._online_friends_cache = []
        self.online_list.insert(tk.END, message)

    def _format_online_row(self, friend: dict) -> str:
        # DisplayName (username) - Game
        dn = friend.get("displayName") or friend.get("name") or "?"
        un = friend.get("name") or "?"
        game = friend.get("game_name") or "Online"
        return f"{dn} ({un}) - {game}"

    def _username_from_values(self, vals) -> str:
        """Tree values order: Display Name, Username, User ID, Notes."""
        if not vals or len(vals) < 2:
            return ""
        return str(vals[1])

    def on_tree_select(self, event=None):
        selected = self.tree.selection()
        if not selected:
            self._selected_account_for_online = None
            self._set_online_list_message("Select an account to see online friends")
            return
        vals = self.tree.item(selected[0], "values")
        if not vals:
            return
        username = self._username_from_values(vals)
        account = next((a for a in self.accounts if a.username == username), None)
        if not account:
            self._set_online_list_message("Account not found")
            return
        # Always refresh when selection changes (including same row re-selected after clear)
        self._selected_account_for_online = account
        self._fetch_online_friends(account)

    def refresh_online_friends(self):
        if self._selected_account_for_online:
            self._fetch_online_friends(self._selected_account_for_online, silent=False)
        else:
            self._set_online_list_message("Select an account to see online friends")

    def _app_is_focused(self) -> bool:
        """True when the main window is visible and not minimized."""
        try:
            if not self.winfo_exists():
                return False
            if self.state() != "normal":
                return False
            return True
        except Exception:
            return False

    def _online_friends_poll_tick(self):
        """Silent refresh of online friends every 10s while the app is focused."""
        try:
            if (
                self._app_is_focused()
                and self._selected_account_for_online is not None
            ):
                self._fetch_online_friends(
                    self._selected_account_for_online, silent=True
                )
        finally:
            self._online_poll_job = self.after(10_000, self._online_friends_poll_tick)

    def _presence_poll_tick(self):
        try:
            if self._app_is_focused() and self.accounts:
                self._refresh_account_presences()
        finally:
            # Every 8s while focused so browser/online shows up quickly
            self._presence_poll_job = self.after(8_000, self._presence_poll_tick)

    def _on_app_focus_in(self, event=None):
        # Only react to main window focus, not every child widget
        if event is not None and event.widget is not self:
            return
        if self.accounts:
            self._refresh_account_presences()

    def _fetch_online_friends(self, account: Account, silent: bool = False):
        self._online_fetch_token += 1
        token = self._online_fetch_token
        if not silent:
            self._set_online_list_message(f"Loading friends for {account.username}...")
            self.status_var.set(f"Fetching online friends for {account.username}...")

        def worker():
            try:
                friends = get_online_friends(account.cookie, account.user_id)
            except Exception:
                friends = None

            def done():
                if token != self._online_fetch_token:
                    return  # stale response
                if friends is None:
                    if not silent:
                        self._set_online_list_message(
                            "Failed to load friends (check cookie)"
                        )
                        self.status_var.set("Online friends fetch failed")
                    return

                # Subtle in-place update: keep selection if the same friend is still online
                prev_sel = None
                if silent and self._online_friends_cache:
                    cur = self.online_list.curselection()
                    if cur and cur[0] < len(self._online_friends_cache):
                        prev_sel = self._online_friends_cache[cur[0]].get("id")

                new_rows = [self._format_online_row(f) for f in friends]
                old_rows = []
                if silent:
                    try:
                        old_rows = list(self.online_list.get(0, tk.END))
                    except Exception:
                        old_rows = []

                self._online_friends_cache = friends

                # Skip full rebuild if nothing changed (no flicker)
                if silent and new_rows == old_rows:
                    return

                self.online_list.delete(0, tk.END)
                if not friends:
                    self.online_list.insert(tk.END, "No friends online")
                else:
                    for row in new_rows:
                        self.online_list.insert(tk.END, row)
                    if prev_sel is not None:
                        for i, f in enumerate(friends):
                            if f.get("id") == prev_sel:
                                self.online_list.selection_set(i)
                                self.online_list.see(i)
                                break
                if not silent:
                    if not friends:
                        self.status_var.set(
                            f"No friends online for {account.username}"
                        )
                    else:
                        self.status_var.set(
                            f"{len(friends)} online friend(s) for {account.username}"
                        )

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _get_selected_online_friend(self) -> Optional[dict]:
        sel = self.online_list.curselection()
        if not sel or not self._online_friends_cache:
            return None
        idx = sel[0]
        if idx < 0 or idx >= len(self._online_friends_cache):
            return None
        return self._online_friends_cache[idx]

    def on_online_double_click(self, event=None):
        self.join_online_friend()

    def join_online_friend(self):
        friend = self._get_selected_online_friend()
        if not friend:
            messagebox.showwarning("Warning", "Select an online friend first.")
            return
        account = self._selected_account_for_online
        if not account:
            # Fall back to current tree selection
            selected = self.tree.selection()
            if selected:
                vals = self.tree.item(selected[0], "values")
                if vals:
                    uname = self._username_from_values(vals)
                    account = next(
                        (a for a in self.accounts if a.username == uname), None
                    )
        if not account:
            messagebox.showwarning("Warning", "Select an account first.")
            return

        place_id = friend.get("placeId") or friend.get("rootPlaceId")
        game_id = friend.get("gameId") or ""
        if not place_id:
            messagebox.showinfo(
                "Cannot join",
                f"{friend.get('displayName')} ({friend.get('name')}) is online "
                "but not in a joinable game server.",
            )
            return

        # Fill fields + persist so user sees what we're joining
        self.place_id_entry.delete(0, tk.END)
        self.place_id_entry.insert(0, str(place_id))
        self.job_id_entry.delete(0, tk.END)
        if game_id:
            self.job_id_entry.insert(0, str(game_id))
        self.link_code_entry.delete(0, tk.END)
        self._save_launch_fields()

        self.status_var.set(
            f"Joining {friend.get('displayName')} ({friend.get('name')})..."
        )
        self.configure(cursor="watch")
        self.update_idletasks()

        def worker():
            success = launch_account(
                account,
                int(place_id),
                job_id=str(game_id) if game_id else "",
                link_code="",
                accounts=self.accounts,
            )

            def done():
                self.configure(cursor="")
                if success:
                    self.status_var.set(
                        f"Launched {account.username} → {friend.get('displayName')}"
                    )
                else:
                    messagebox.showerror(
                        "Join failed",
                        "Could not get auth ticket or launch Roblox.\n"
                        "Try Validate / Refresh Cookies first.",
                    )
                    self.status_var.set("Join failed")

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def on_fav_double_click(self, event):
        self.use_favorite()

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def open_settings(self):
        settings_win = tk.Toplevel(self)
        settings_win.title("Settings")
        settings_win.geometry("360x420")
        settings_win.transient(self)
        settings_win.grab_set()
        settings_win.resizable(False, False)
        
        theme_colors = self.colors[self.current_theme]
        settings_win.configure(bg=theme_colors["frame_bg"])
        
        # --- Theme ---
        tk.Label(
            settings_win, text="Appearance",
            bg=theme_colors["frame_bg"], fg=theme_colors["fg"],
            font=("Segoe UI", 10, "bold"),
        ).pack(pady=(14, 4), anchor="w", padx=16)
        
        theme_row = tk.Frame(settings_win, bg=theme_colors["frame_bg"])
        theme_row.pack(fill="x", padx=16, pady=(0, 8))
        
        tk.Label(
            theme_row, text="Theme:",
            bg=theme_colors["frame_bg"], fg=theme_colors["fg"],
        ).pack(side="left")
        
        _theme_labels = {
            "dark": "Dark",
            "purple": "Purple",
            "light": "Light",
        }
        theme_var = tk.StringVar(
            value=_theme_labels.get(self.current_theme, "Dark")
        )
        theme_box = ttk.Combobox(
            theme_row,
            textvariable=theme_var,
            values=("Dark", "Purple", "Light"),
            state="readonly",
            width=14,
        )
        theme_box.pack(side="left", padx=(8, 0))
        
        def on_theme_change(_event=None):
            choice = theme_var.get()
            new_theme = {"Dark": "dark", "Purple": "purple", "Light": "light"}.get(
                choice, "dark"
            )
            if new_theme != self.current_theme:
                self.current_theme = new_theme
                self.config["theme"] = new_theme
                save_config(self.config)
                self.apply_theme()
                self.update_widget_colors(self, self.colors[self.current_theme])
                if hasattr(self, "tab_bar"):
                    self._rebuild_tab_bar()
                # Refresh settings window colors recursively
                settings_win.configure(bg=self.colors[self.current_theme]["frame_bg"])
                self.update_widget_colors(settings_win, self.colors[self.current_theme])
                self.status_var.set(f"Theme: {choice}")
        
        theme_box.bind("<<ComboboxSelected>>", on_theme_change)
        
        # --- Multi-instance ---
        tk.Label(
            settings_win, text="Roblox",
            bg=theme_colors["frame_bg"], fg=theme_colors["fg"],
            font=("Segoe UI", 10, "bold"),
        ).pack(pady=(10, 4), anchor="w", padx=16)
        
        multi_var = tk.BooleanVar(
            value=self.multi_instance_active or self.config.get("multi_instance", False)
        )
        
        def on_multi_toggle():
            want = multi_var.get()
            if want:
                if enable_multi_instance():
                    self.multi_instance_active = True
                    self.config["multi_instance"] = True
                    save_config(self.config)
                    self.status_var.set("Multi-instance ACTIVE")
                else:
                    multi_var.set(False)
                    self.multi_instance_active = False
                    # Keep preference so next launch still tries
                    self.config["multi_instance"] = True
                    save_config(self.config)
                    messagebox.showerror(
                        "Error",
                        "Failed to enable multi-instance.\n"
                        "Windows only – no extra packages required.",
                        parent=settings_win,
                    )
            else:
                release_multi_instance()
                self.multi_instance_active = False
                self.config["multi_instance"] = False
                save_config(self.config)
                self.status_var.set("Ready")
        
        tk.Checkbutton(
            settings_win,
            text="Enable multi-instance (keep this app open.)",
            variable=multi_var,
            command=on_multi_toggle,
            bg=theme_colors["frame_bg"],
            fg=theme_colors["fg"],
            selectcolor=theme_colors["btn_bg"],
            activebackground=theme_colors["frame_bg"],
            activeforeground=theme_colors["fg"],
            justify="left",
            anchor="w",
        ).pack(pady=4, padx=16, anchor="w")
        
        delay_row = tk.Frame(settings_win, bg=theme_colors["frame_bg"])
        delay_row.pack(fill="x", padx=16, pady=(6, 0))
        
        tk.Label(
            delay_row, text="Delay between launches (sec):",
            bg=theme_colors["frame_bg"], fg=theme_colors["fg"],
        ).pack(side="left")
        
        delay_var = tk.StringVar(
            value=str(self.config.get("launch_delay", 3.0))
        )
        delay_entry = tk.Entry(
            delay_row, textvariable=delay_var, width=6,
            bg="#ffffff", fg="#000000",
        )
        delay_entry.pack(side="left", padx=(8, 0))
        
        def save_delay(_event=None):
            try:
                val = float(delay_var.get().strip())
                if val < 0:
                    val = 0.0
                if val > 120:
                    val = 120.0
                self.config["launch_delay"] = val
                save_config(self.config)
                delay_var.set(str(val))
                self.status_var.set(f"Launch delay: {val}s")
            except ValueError:
                delay_var.set(str(self.config.get("launch_delay", 3.0)))
        
        delay_entry.bind("<FocusOut>", save_delay)
        delay_entry.bind("<Return>", save_delay)
        
        # --- Cookie auto-refresh ---
        tk.Label(
            settings_win, text="Cookies",
            bg=theme_colors["frame_bg"], fg=theme_colors["fg"],
            font=("Segoe UI", 10, "bold"),
        ).pack(pady=(10, 4), anchor="w", padx=16)
        
        auto_var = tk.BooleanVar(value=self.auto_refresh)
        
        def toggle_auto():
            self.auto_refresh = auto_var.get()
            self.config["auto_cookie_refresh"] = self.auto_refresh
            save_config(self.config)
            if self.auto_refresh:
                self.schedule_cookie_refresh()
            else:
                if self._refresh_job is not None:
                    try:
                        self.after_cancel(self._refresh_job)
                    except Exception:
                        pass
                    self._refresh_job = None
            self.status_var.set(
                "Auto cookie refresh ON" if self.auto_refresh else "Auto cookie refresh OFF"
            )
        
        tk.Checkbutton(
            settings_win,
            text="Auto-refresh cookies every 30 min\n(handles Roblox Set-Cookie rotation)",
            variable=auto_var,
            command=toggle_auto,
            bg=theme_colors["frame_bg"],
            fg=theme_colors["fg"],
            selectcolor=theme_colors["btn_bg"],
            activebackground=theme_colors["frame_bg"],
            activeforeground=theme_colors["fg"],
            justify="left",
            anchor="w",
        ).pack(pady=4, padx=16, anchor="w")

        # --- Security ---
        tk.Label(
            settings_win, text="Security",
            bg=theme_colors["frame_bg"], fg=theme_colors["fg"],
            font=("Segoe UI", 10, "bold"),
        ).pack(pady=(12, 4), anchor="w", padx=16)

        tk.Button(
            settings_win,
            text="Change master password…",
            command=lambda: self._change_master_password(settings_win),
            width=24,
            bg=theme_colors["btn_bg"],
            fg=theme_colors["btn_fg"],
        ).pack(pady=(2, 4), padx=16, anchor="w")

        tk.Label(
            settings_win,
            text="Vault is encrypted. Remember the password —\nthere is no recovery if you forget it.",
            bg=theme_colors["frame_bg"],
            fg=theme_colors["fg"],
            font=("Segoe UI", 8),
            justify="left",
        ).pack(pady=(0, 8), padx=16, anchor="w")

    def _change_master_password(self, parent=None):
        """Dialog to change the vault master password."""
        theme_colors = self.colors[self.current_theme]
        dlg = tk.Toplevel(parent or self)
        dlg.title("Change Master Password")
        dlg.geometry("360x220")
        dlg.transient(parent or self)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.configure(bg=theme_colors["frame_bg"])

        frm = tk.Frame(dlg, bg=theme_colors["frame_bg"], padx=16, pady=14)
        frm.pack(fill="both", expand=True)

        def labeled_entry(row, label, show="•"):
            tk.Label(
                frm, text=label,
                bg=theme_colors["frame_bg"], fg=theme_colors["fg"],
            ).grid(row=row, column=0, sticky="w", pady=4)
            var = tk.StringVar()
            ent = tk.Entry(frm, textvariable=var, show=show, width=28,
                           bg="#ffffff", fg="#000000")
            ent.grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 0))
            return var, ent

        old_var, old_ent = labeled_entry(0, "Current password:")
        new_var, new_ent = labeled_entry(1, "New password:")
        conf_var, conf_ent = labeled_entry(2, "Confirm new:")
        old_ent.focus_set()

        status_var = tk.StringVar()
        tk.Label(
            frm, textvariable=status_var,
            bg=theme_colors["frame_bg"], fg="#c44",
            font=("Segoe UI", 9),
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

        def do_change(event=None):
            old_pw = old_var.get()
            new_pw = new_var.get()
            conf = conf_var.get()
            if not old_pw or not new_pw:
                status_var.set("All fields are required.")
                return
            if new_pw != conf:
                status_var.set("New passwords do not match.")
                return
            if len(new_pw) < 6:
                status_var.set("Use at least 6 characters.")
                return
            if new_pw == old_pw:
                status_var.set("New password must be different.")
                return
            try:
                if change_password(old_pw, new_pw):
                    messagebox.showinfo(
                        "Password changed",
                        "Master password updated.\nThe vault has been re-encrypted.",
                        parent=dlg,
                    )
                    dlg.destroy()
                    self.status_var.set("Master password changed")
                else:
                    status_var.set("Current password is wrong.")
                    old_var.set("")
                    old_ent.focus_set()
            except EncryptionError as e:
                status_var.set(str(e))

        btn_row = tk.Frame(frm, bg=theme_colors["frame_bg"])
        btn_row.grid(row=4, column=0, columnspan=2, sticky="e", pady=(14, 0))
        tk.Button(
            btn_row, text="Cancel", command=dlg.destroy,
            width=10, bg=theme_colors["btn_bg"], fg=theme_colors["btn_fg"],
        ).pack(side="right", padx=(8, 0))
        tk.Button(
            btn_row, text="Change", command=do_change,
            width=10, bg=theme_colors["btn_bg"], fg=theme_colors["btn_fg"],
        ).pack(side="right")

        dlg.bind("<Return>", do_change)

    def schedule_cookie_refresh(self):
        if self._refresh_job is not None:
            try:
                self.after_cancel(self._refresh_job)
            except Exception:
                pass
        self._refresh_job = self.after(30 * 60 * 1000, self._do_background_refresh)

    def _do_background_refresh(self):
        if not self.auto_refresh or not self.accounts:
            self.schedule_cookie_refresh()
            return
        
        def worker():
            try:
                valid, total, invalid = refresh_all_cookies(self.accounts)
                def update_ui():
                    self.update_account_list()
                    if invalid:
                        self.status_var.set(
                            f"Cookie refresh: {valid}/{total} OK, invalid: {', '.join(invalid[:3])}"
                        )
                    else:
                        self.status_var.set(f"Cookie refresh: {valid}/{total} OK")
                self.after(0, update_ui)
            except Exception:
                pass
            finally:
                self.after(0, self.schedule_cookie_refresh)
        
        threading.Thread(target=worker, daemon=True).start()

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------
    def _get_tab(self, tab_id: str):
        for t in self.tabs_data.get("tabs", []):
            if t.get("id") == tab_id:
                return t
        return None

    def _rebuild_tab_bar(self):
        theme = self.colors[self.current_theme]
        self.tab_bar.configure(bg=theme["frame_bg"])
        for child in self.tab_bar.winfo_children():
            child.destroy()
        self._tab_buttons = {}

        for tab in self.tabs_data.get("tabs", []):
            tid = tab["id"]
            is_active = tid == self.active_tab_id
            # Classic raised / sunken button tabs (same palette as the toolbar)
            btn = tk.Button(
                self.tab_bar,
                text=tab.get("name", "Tab"),
                bg=theme["btn_bg"],
                fg=theme["btn_fg"],
                activebackground=theme["btn_bg"],
                activeforeground=theme["btn_fg"],
                relief="sunken" if is_active else "raised",
                bd=2,
                padx=8,
                pady=1,
                font=("Segoe UI", 9, "bold" if is_active else "normal"),
                cursor="hand2",
                takefocus=0,
                command=lambda i=tid: self._switch_tab(i),
            )
            btn.pack(side="left", padx=(0, 2), pady=2)
            btn.bind("<Double-Button-1>", lambda e, i=tid: self._rename_tab(i))
            btn.bind("<Button-3>", lambda e, i=tid: self._tab_context_menu(e, i))
            self._tab_buttons[tid] = btn

        add_btn = tk.Button(
            self.tab_bar,
            text="+",
            bg=theme["btn_bg"],
            fg=theme["btn_fg"],
            activebackground=theme["btn_bg"],
            activeforeground=theme["btn_fg"],
            relief="raised",
            bd=2,
            padx=6,
            pady=1,
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
            takefocus=0,
            command=self._add_tab,
        )
        add_btn.pack(side="left", padx=(4, 0), pady=2)

    def _switch_tab(self, tab_id: str):
        if tab_id == self.active_tab_id:
            return
        if not self._get_tab(tab_id):
            return
        self.active_tab_id = tab_id
        self.tabs_data["active"] = tab_id
        save_tabs(self.tabs_data)
        self._rebuild_tab_bar()
        self.update_account_list()
        tab = self._get_tab(tab_id)
        name = tab.get("name", tab_id) if tab else tab_id
        self.status_var.set(f"Tab: {name}")

    def _add_tab(self):
        name = simpledialog.askstring("New Tab", "Tab name:", parent=self)
        if name is None:
            return
        name = name.strip() or "New Tab"
        new_id = str(uuid.uuid4())[:8]
        self.tabs_data["tabs"].append({
            "id": new_id,
            "name": name,
            "builtin": False,
            "accounts": [],
        })
        self.active_tab_id = new_id
        self.tabs_data["active"] = new_id
        save_tabs(self.tabs_data)
        self._rebuild_tab_bar()
        self.update_account_list()
        self.status_var.set(f"Created tab: {name}")

    def _rename_tab(self, tab_id: str):
        tab = self._get_tab(tab_id)
        if not tab:
            return
        # All tab can be renamed for display, but stays builtin / not deletable
        new_name = simpledialog.askstring(
            "Rename Tab", "Tab name:", initialvalue=tab.get("name", ""), parent=self,
        )
        if new_name is None:
            return
        new_name = new_name.strip()
        if not new_name:
            return
        tab["name"] = new_name
        save_tabs(self.tabs_data)
        self._rebuild_tab_bar()
        self.status_var.set(f"Renamed tab: {new_name}")

    def _delete_tab(self, tab_id: str):
        tab = self._get_tab(tab_id)
        if not tab:
            return
        if tab.get("builtin") or tab.get("id") == "all":
            messagebox.showinfo("Tabs", "The All tab cannot be deleted.")
            return
        if not messagebox.askyesno("Delete Tab", f"Delete tab '{tab.get('name')}'?\nAccounts are not removed."):
            return
        self.tabs_data["tabs"] = [t for t in self.tabs_data["tabs"] if t.get("id") != tab_id]
        if self.active_tab_id == tab_id:
            self.active_tab_id = "all"
            self.tabs_data["active"] = "all"
        save_tabs(self.tabs_data)
        self._rebuild_tab_bar()
        self.update_account_list()
        self.status_var.set("Tab deleted")

    def _tab_context_menu(self, event, tab_id: str):
        tab = self._get_tab(tab_id)
        if not tab:
            return
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Edit name", command=lambda: self._rename_tab(tab_id))
        if not tab.get("builtin") and tab.get("id") != "all":
            menu.add_separator()
            menu.add_command(label="Delete", command=lambda: self._delete_tab(tab_id))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def on_tree_right_click(self, event):
        """Account context menu: add to tab / remove from tab."""
        row = self.tree.identify_row(event.y)
        if row:
            # Select row under cursor if not already in selection
            if row not in self.tree.selection():
                self.tree.selection_set(row)

        selected = self.tree.selection()
        usernames = []
        for iid in selected:
            vals = self.tree.item(iid, "values")
            if vals:
                uname = self._username_from_values(vals)
                if uname:
                    usernames.append(uname)

        menu = tk.Menu(self, tearoff=0)

        if usernames:
            primary = usernames[0]
            menu.add_command(
                label="Edit note",
                command=lambda u=primary: self.edit_notes(u),
            )
            menu.add_command(
                label="Copy cookie",
                command=lambda u=primary: self.copy_cookie(u),
            )
            menu.add_command(
                label="Delete",
                command=self.remove_selected,
            )
            menu.add_separator()

        custom_tabs = [
            t for t in self.tabs_data.get("tabs", [])
            if not t.get("builtin") and t.get("id") != "all"
        ]

        if self.active_tab_id == "all" or (self._get_tab(self.active_tab_id) or {}).get("builtin"):
            if custom_tabs and usernames:
                add_menu = tk.Menu(menu, tearoff=0)
                for t in custom_tabs:
                    add_menu.add_command(
                        label=t.get("name", "Tab"),
                        command=lambda tid=t["id"]: self._add_accounts_to_tab(tid, usernames),
                    )
                menu.add_cascade(label="Add to tab", menu=add_menu)
            elif not custom_tabs:
                menu.add_command(label="Create a tab first (+)", state="disabled")
            else:
                menu.add_command(label="Select account(s) first", state="disabled")
        else:
            if usernames:
                menu.add_command(
                    label="Remove from this tab",
                    command=lambda: self._remove_accounts_from_tab(self.active_tab_id, usernames),
                )
            else:
                menu.add_command(label="Select account(s) first", state="disabled")

        if menu.index("end") is None:
            return
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _add_accounts_to_tab(self, tab_id: str, usernames: list):
        tab = self._get_tab(tab_id)
        if not tab or tab.get("builtin"):
            return
        existing = list(tab.get("accounts") or [])
        added = 0
        for name in usernames:
            if name not in existing:
                existing.append(name)
                added += 1
        tab["accounts"] = existing
        save_tabs(self.tabs_data)
        self.status_var.set(f"Added {added} to '{tab.get('name')}'")

    def _remove_accounts_from_tab(self, tab_id: str, usernames: list):
        tab = self._get_tab(tab_id)
        if not tab or tab.get("builtin"):
            return
        remove_set = set(usernames)
        tab["accounts"] = [u for u in (tab.get("accounts") or []) if u not in remove_set]
        save_tabs(self.tabs_data)
        self.update_account_list()
        self.status_var.set(f"Removed {len(usernames)} from '{tab.get('name')}'")

    # ------------------------------------------------------------------
    # Avatars – 24x24 via subsample, narrow column
    # ------------------------------------------------------------------
    def _load_avatar_image(self, user_id: int, presence_type: int = 0):
        """
        Load avatar from disk cache only (no network).
        Small presence dot sits in a fixed left gutter so the headshot never shifts.
        Offline = empty gutter (no circle). Online=blue, in-game=green.
        """
        ptype = presence_type if presence_type in (1, 2, 3) else 0
        cache_key = (user_id, ptype)
        if cache_key in self._photo_images:
            return self._photo_images[cache_key]
        from roblox_manager import AVATAR_CACHE_DIR
        path = AVATAR_CACHE_DIR / f"{user_id}_48x48.png"
        if not path.exists() or path.stat().st_size <= 100:
            return None
        try:
            from PIL import Image, ImageDraw, ImageTk
            base = Image.open(path).convert("RGBA").resize((24, 24), Image.Resampling.LANCZOS)
            # Always same width: 6px gutter + 24px avatar → avatars never jump
            gutter = 6
            canvas = Image.new("RGBA", (gutter + 24, 24), (0, 0, 0, 0))
            canvas.paste(base, (gutter, 0), base)
            if ptype in (1, 2, 3):
                draw = ImageDraw.Draw(canvas)
                color = (34, 197, 94, 255) if ptype == 2 else (59, 130, 246, 255)
                # ~5px diameter, left of avatar, vertically centered
                cx, cy, r = 2, 12, 2
                draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
            photo = ImageTk.PhotoImage(canvas)
            self._photo_images[cache_key] = photo
            return photo
        except Exception:
            try:
                img = tk.PhotoImage(file=str(path))
                img = img.subsample(2, 2)
                self._photo_images[cache_key] = img
                return img
            except Exception:
                return None

    def _notes_preview(self, notes: str) -> str:
        """ⓘ + one-line preview; Treeview clips whatever doesn't fit the column."""
        if not notes:
            return ""
        text = " ".join(notes.split())
        return f"ⓘ {text}"

    def _accounts_for_active_tab(self):
        """Accounts visible on the current tab (order preserved)."""
        tab = self._get_tab(self.active_tab_id)
        if not tab or tab.get("builtin") or tab.get("id") == "all":
            return list(self.accounts)
        by_name = {a.username: a for a in self.accounts}
        result = []
        for name in tab.get("accounts") or []:
            if name in by_name:
                result.append(by_name[name])
        return result

    def _accounts_matching_search(self, accounts: list) -> list:
        q = (self._search_query or "").strip().lower()
        if not q:
            return accounts
        out = []
        for acc in accounts:
            hay = " ".join([
                str(acc.display_name or ""),
                str(acc.username or ""),
                str(acc.user_id or ""),
                str(acc.notes or ""),
            ]).lower()
            if q in hay:
                out.append(acc)
        return out

    def update_account_list(self, defer_images: bool = True):
        """
        Fast list update: text rows first, avatar images applied afterward.
        When the visible set/order is unchanged, only updates values in place
        (no flicker). Otherwise rebuilds cleanly without blocking on images.
        """
        # Preserve selection by username
        prev_selected = set()
        for iid in self.tree.selection():
            vals = self.tree.item(iid, "values")
            uname = self._username_from_values(vals)
            if uname:
                prev_selected.add(uname)

        accounts = self._accounts_matching_search(self._accounts_for_active_tab())
        desired_uids = [a.user_id for a in accounts]

        # Current order of user_ids in the tree
        current_uids: list[int] = []
        iid_by_uid: dict[int, str] = {}
        for iid in self.tree.get_children():
            vals = self.tree.item(iid, "values")
            if not vals or len(vals) < 3:
                continue
            try:
                uid = int(vals[2])
            except (TypeError, ValueError):
                continue
            current_uids.append(uid)
            iid_by_uid[uid] = iid

        same_order = current_uids == desired_uids

        if same_order and desired_uids:
            # In-place value update only — keeps images, no flicker
            for acc in accounts:
                iid = iid_by_uid.get(acc.user_id)
                if not iid:
                    continue
                note_text = self._notes_preview(acc.notes)
                values = (
                    acc.display_name or acc.username,
                    acc.username,
                    acc.user_id,
                    note_text,
                )
                try:
                    self.tree.item(iid, values=values)
                except Exception:
                    pass
                if acc.username in prev_selected:
                    try:
                        self.tree.selection_add(iid)
                    except Exception:
                        pass
        else:
            # Full structural change (search / tab / add / remove) — rebuild text fast
            for item in self.tree.get_children():
                self.tree.delete(item)
            for acc in accounts:
                note_text = self._notes_preview(acc.notes)
                iid = self.tree.insert(
                    "",
                    "end",
                    text="",
                    image="",  # images applied in second pass
                    values=(
                        acc.display_name or acc.username,
                        acc.username,
                        acc.user_id,
                        note_text,
                    ),
                )
                if acc.username in prev_selected:
                    try:
                        self.tree.selection_add(iid)
                    except Exception:
                        pass

        # Images last so the text list is interactive immediately
        if defer_images:
            self.after(1, self._refresh_avatar_images_only)
        else:
            self._refresh_avatar_images_only()

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def _focus_search(self, event=None):
        try:
            self.search_entry.focus_set()
            if self.search_entry.get() == self._search_placeholder:
                self.search_entry.delete(0, tk.END)
                self.search_entry.configure(fg=self.colors[self.current_theme]["tree_fg"])
            self.search_entry.selection_range(0, tk.END)
        except Exception:
            pass
        return "break"

    def _search_focus_in(self, event=None):
        if self.search_entry.get() == self._search_placeholder:
            self.search_entry.delete(0, tk.END)
            self.search_entry.configure(fg=self.colors[self.current_theme]["tree_fg"])

    def _search_focus_out(self, event=None):
        if not self.search_entry.get().strip():
            self.search_entry.delete(0, tk.END)
            self.search_entry.insert(0, self._search_placeholder)
            self.search_entry.configure(fg="#888888")
            self._search_query = ""
            self.update_account_list()

    def _on_search_key(self, event=None):
        raw = self.search_entry.get()
        if raw == self._search_placeholder:
            self._search_query = ""
        else:
            self._search_query = raw
        if self._search_job is not None:
            try:
                self.after_cancel(self._search_job)
            except Exception:
                pass
        self._search_job = self.after(80, self.update_account_list)

    def _search_clear(self, event=None):
        self.search_entry.delete(0, tk.END)
        self._search_query = ""
        self.update_account_list()
        self.tree.focus_set()
        return "break"

    # ------------------------------------------------------------------
    # Account presence (blue / green dots)
    # ------------------------------------------------------------------
    def _refresh_account_presences(self):
        if not self.accounts:
            return
        # Prefer cookie from selected account, else first account with a cookie
        cookie = ""
        if self._selected_account_for_online and self._selected_account_for_online.cookie:
            cookie = self._selected_account_for_online.cookie
        else:
            for a in self.accounts:
                if a.cookie:
                    cookie = a.cookie
                    break
        if not cookie:
            return
        ids = [a.user_id for a in self._accounts_for_active_tab() if a.user_id]

        def worker():
            try:
                presences = get_presences(cookie, ids)
            except Exception:
                presences = {}

            def done():
                changed = False
                for uid, p in presences.items():
                    ptype = int(p.get("userPresenceType") or 0)
                    if self._presence_by_uid.get(uid) != ptype:
                        changed = True
                    self._presence_by_uid[uid] = ptype
                if changed:
                    self._apply_presence_to_tree()

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_presence_to_tree(self):
        """Swap avatar images for presence dots without greying out text."""
        for iid in self.tree.get_children():
            vals = self.tree.item(iid, "values")
            if not vals or len(vals) < 3:
                continue
            try:
                uid = int(vals[2])
            except (TypeError, ValueError):
                continue
            ptype = int(self._presence_by_uid.get(uid, 0) or 0)
            img = self._load_avatar_image(uid, presence_type=ptype)
            self.tree.item(iid, text="", image=img if img else "")

    # ------------------------------------------------------------------
    # Server browser
    # ------------------------------------------------------------------
    def _current_place_id(self) -> Optional[int]:
        raw = self.place_id_entry.get().strip()
        m = re.search(r"(\d{5,})", raw)
        if not m:
            return None
        return int(m.group(1))

    def _cookie_for_api(self) -> str:
        if self._selected_account_for_online and self._selected_account_for_online.cookie:
            return self._selected_account_for_online.cookie
        selected = self.tree.selection()
        if selected:
            vals = self.tree.item(selected[0], "values")
            uname = self._username_from_values(vals)
            acc = next((a for a in self.accounts if a.username == uname), None)
            if acc and acc.cookie:
                return acc.cookie
        for a in self.accounts:
            if a.cookie:
                return a.cookie
        return ""

    def _remember_visited_server(self, place_id: int, server: dict):
        """Persist last-visited servers (per place) in config."""
        entry = {
            "place_id": int(place_id),
            "job_id": str(server.get("id") or ""),
            "playing": int(server.get("playing") or 0),
            "maxPlayers": int(server.get("maxPlayers") or 0),
            "ping": server.get("ping"),
            "visited_at": time.time(),
        }
        if not entry["job_id"]:
            return
        visited = list(self.config.get("last_visited_servers") or [])
        # Drop duplicates of same job
        visited = [v for v in visited if v.get("job_id") != entry["job_id"]]
        visited.insert(0, entry)
        self.config["last_visited_servers"] = visited[:30]
        save_config(self.config)

    def open_server_browser(self):
        place_id = self._current_place_id()
        if not place_id:
            messagebox.showwarning("Warning", "Enter a Place ID first.")
            return

        theme = self.colors[self.current_theme]
        win = tk.Toplevel(self)
        win.title(f"Servers – Place {place_id}")
        win.geometry("480x440")
        win.resizable(True, True)
        win.minsize(400, 320)
        win.configure(bg=theme["bg"])
        _apply_window_icon(win)

        # --- Last visited for this place ---
        visited_all = self.config.get("last_visited_servers") or []
        visited_here = [v for v in visited_all if int(v.get("place_id") or 0) == place_id]

        if visited_here:
            tk.Label(
                win, text="Last visited",
                bg=theme["bg"], fg=theme["fg"], font=("Segoe UI", 9, "bold"),
            ).pack(anchor="w", padx=10, pady=(8, 2))
            visited_lb = tk.Listbox(
                win, height=min(4, len(visited_here)),
                bg=theme["tree_bg"], fg=theme["tree_fg"],
                selectbackground="#0078d7", selectforeground="#ffffff",
                font=("Consolas", 9), activestyle="none",
            )
            visited_lb.pack(fill="x", padx=10, pady=(0, 4))
            for v in visited_here[:10]:
                ping = v.get("ping")
                ping_s = f"{ping}ms" if ping is not None else "-"
                visited_lb.insert(
                    tk.END,
                    f"{v.get('playing', 0):>3}/{v.get('maxPlayers', 0):<3}  "
                    f"ping {ping_s:<6}  {str(v.get('job_id', ''))[:10]}...",
                )

            def use_visited(event=None):
                sel = visited_lb.curselection()
                if not sel:
                    return
                v = visited_here[sel[0]]
                apply_job({
                    "id": v.get("job_id"),
                    "playing": v.get("playing", 0),
                    "maxPlayers": v.get("maxPlayers", 0),
                    "ping": v.get("ping"),
                })

            visited_lb.bind("<Double-Button-1>", use_visited)

        tk.Label(
            win, text="Public servers  (scroll for more)",
            bg=theme["bg"], fg=theme["fg"], font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=10, pady=(6, 2))

        list_frame = tk.Frame(win, bg=theme["bg"])
        list_frame.pack(fill="both", expand=True, padx=10, pady=4)
        lb = tk.Listbox(
            list_frame,
            bg=theme["tree_bg"], fg=theme["tree_fg"],
            selectbackground="#0078d7", selectforeground="#ffffff",
            font=("Consolas", 9), activestyle="none",
        )
        sb = self._make_scrollbar(list_frame, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        status = tk.StringVar(value="Loading...")
        tk.Label(win, textvariable=status, bg=theme["bg"], fg=theme["fg"]).pack(
            anchor="w", padx=10
        )

        server_cache: list = []
        state = {"cursor": "", "loading": False, "done": False}

        def format_row(s: dict) -> str:
            ping = s.get("ping")
            ping_s = f"{ping}ms" if ping is not None else "-"
            return (
                f"{s['playing']:>3}/{s['maxPlayers']:<3}  "
                f"ping {ping_s:<6}  {s['id'][:10]}..."
            )

        def apply_job(server: dict):
            if not server.get("id"):
                return
            self.job_id_entry.delete(0, tk.END)
            self.job_id_entry.insert(0, server["id"])
            self._save_launch_fields()
            self._remember_visited_server(place_id, server)
            self.status_var.set(
                f"Server selected: {server.get('playing', '?')}/"
                f"{server.get('maxPlayers', '?')}"
            )
            win.destroy()

        def on_use():
            sel = lb.curselection()
            if not sel or sel[0] >= len(server_cache):
                return
            apply_job(server_cache[sel[0]])

        lb.bind("<Double-Button-1>", lambda e: on_use())

        def pick_kind(kind: str):
            if not server_cache:
                return
            pick = (
                pick_fast_server(server_cache)
                if kind == "fast"
                else pick_small_server(server_cache)
            )
            if pick:
                apply_job(pick)

        def append_servers(servers: list, next_cursor: str, reset: bool):
            if reset:
                server_cache.clear()
                lb.delete(0, tk.END)
            for s in servers:
                # Avoid duplicate job ids when paginating
                if any(x["id"] == s["id"] for x in server_cache):
                    continue
                server_cache.append(s)
                lb.insert(tk.END, format_row(s))
            state["cursor"] = next_cursor or ""
            state["done"] = not bool(next_cursor)
            state["loading"] = False
            if not server_cache:
                status.set("No public servers found")
            elif state["done"]:
                status.set(f"{len(server_cache)} server(s)")
            else:
                status.set(f"{len(server_cache)} server(s) — scroll for more")

        def load_page(reset: bool = False):
            if state["loading"]:
                return
            if not reset and state["done"]:
                return
            state["loading"] = True
            if reset:
                state["cursor"] = ""
                state["done"] = False
                status.set("Loading...")
            else:
                status.set(f"{len(server_cache)} server(s) — loading more...")
            cookie = self._cookie_for_api()
            cursor = "" if reset else state["cursor"]

            def worker():
                servers, next_cursor = get_public_servers(
                    place_id, cookie=cookie, limit=100, cursor=cursor
                )

                def done():
                    append_servers(servers, next_cursor, reset=reset)

                self.after(0, done)

            threading.Thread(target=worker, daemon=True).start()

        def on_scroll(*_args):
            # Infinite scroll: near bottom → fetch next cursor page
            try:
                top, bottom = lb.yview()
            except Exception:
                return
            if bottom >= 0.92 and not state["loading"] and not state["done"]:
                load_page(reset=False)

        lb.configure(yscrollcommand=lambda *a: (sb.set(*a), on_scroll()))
        sb.configure(command=lambda *a: (lb.yview(*a), on_scroll()))

        btn_row = tk.Frame(win, bg=theme["bg"])
        btn_row.pack(fill="x", padx=10, pady=8)
        tk.Button(
            btn_row, text="Use Job ID", command=on_use,
            bg="#4CAF50", fg="white", width=12,
        ).pack(side="left", padx=2)
        tk.Button(
            btn_row, text="Fast",
            command=lambda: pick_kind("fast"),
            bg="#2563eb", fg="white", width=8,
        ).pack(side="left", padx=2)
        tk.Button(
            btn_row, text="Small",
            command=lambda: pick_kind("small"),
            bg="#7c3aed", fg="white", width=8,
        ).pack(side="left", padx=2)
        tk.Button(
            btn_row, text="Refresh",
            command=lambda: load_page(reset=True),
            bg=theme["btn_bg"], fg=theme["btn_fg"], width=8,
        ).pack(side="left", padx=2)
        tk.Button(
            btn_row, text="Close", command=win.destroy,
            bg=theme["btn_bg"], fg=theme["btn_fg"], width=8,
        ).pack(side="right", padx=2)

        load_page(reset=True)

    def _notes_icon_hit(self, event, row_id):
        """True only if the click landed roughly on the ⓘ glyph (left side of Notes cell)."""
        bbox = self.tree.bbox(row_id, "#4")
        if not bbox:
            return False
        cell_x, _y, _w, _h = bbox
        return event.x <= cell_x + 22

    def on_tree_press(self, event):
        """Start potential drag (ignored when Ctrl/Shift multi-selecting)."""
        if event.state & 0x0004 or event.state & 0x0001:  # Control or Shift
            self._drag = {"item": None, "y": 0, "active": False}
            return
        row = self.tree.identify_row(event.y)
        self._drag = {"item": row, "y": event.y, "x": event.x, "active": False}

    def on_tree_motion(self, event):
        """If the mouse moves enough, enter drag mode."""
        if not self._drag.get("item"):
            return
        if self._drag["active"]:
            return
        if abs(event.y - self._drag["y"]) >= 6:
            self._drag["active"] = True
            self.configure(cursor="hand2")

    def on_tree_release(self, event):
        """Drop to reorder, or treat as a normal Notes ⓘ click."""
        try:
            if self._drag.get("active") and self._drag.get("item"):
                self._drop_reorder(event)
            else:
                self._notes_single_click(event)
        finally:
            self._drag = {"item": None, "y": 0, "active": False}
            self.configure(cursor="")

    def _drop_reorder(self, event):
        """Move the dragged row to the drop position and save account order."""
        source = self._drag["item"]
        if not source or source not in self.tree.get_children():
            return

        target = self.tree.identify_row(event.y)
        children = list(self.tree.get_children())

        if target and target in children and target != source:
            bbox = self.tree.bbox(target)
            index = children.index(target)
            if bbox and event.y > bbox[1] + bbox[3] // 2:
                index += 1
            # Adjust if source is before the insertion point
            src_index = children.index(source)
            if src_index < index:
                index -= 1
            self.tree.move(source, "", index)
        elif not target and children:
            # Dropped below the last visible row → move to end
            self.tree.move(source, "", "end")
        else:
            return

        self._persist_account_order()
        self.status_var.set("Account order saved")

    def _persist_account_order(self):
        """Save row order for the active tab (All → accounts.json, custom → tabs.json)."""
        usernames = []
        for iid in self.tree.get_children():
            vals = self.tree.item(iid, "values")
            if vals:
                uname = self._username_from_values(vals)
                if uname:
                    usernames.append(uname)

        tab = self._get_tab(self.active_tab_id)
        if not tab or tab.get("builtin") or tab.get("id") == "all":
            by_name = {a.username: a for a in self.accounts}
            new_list = [by_name[u] for u in usernames if u in by_name]
            for a in self.accounts:
                if a.username not in usernames:
                    new_list.append(a)
            self.accounts = new_list
            save_accounts(self.accounts)
        else:
            tab["accounts"] = usernames
            save_tabs(self.tabs_data)

    def _notes_single_click(self, event):
        """Single-click on the ⓘ only → read-only preview."""
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        column = self.tree.identify_column(event.x)
        if column != "#4":
            return
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        item_values = self.tree.item(row_id, "values")
        if not item_values:
            return
        note_cell = item_values[3] if len(item_values) > 3 else ""
        if not note_cell.startswith("ⓘ"):
            return
        if not self._notes_icon_hit(event, row_id):
            return
        username = self._username_from_values(item_values)
        account = next((a for a in self.accounts if a.username == username), None)
        if account and account.notes:
            messagebox.showinfo(f"Notes for {username}", account.notes)

    def on_tree_double_click(self, event):
        """Double-click Notes background → edit. Double-click ⓘ → preview only."""
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        column = self.tree.identify_column(event.x)
        if column != "#4":
            return
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        item_values = self.tree.item(row_id, "values")
        if not item_values:
            return
        note_cell = item_values[3] if len(item_values) > 3 else ""
        username = self._username_from_values(item_values)
        if note_cell.startswith("ⓘ") and self._notes_icon_hit(event, row_id):
            account = next((a for a in self.accounts if a.username == username), None)
            if account and account.notes:
                messagebox.showinfo(f"Notes for {username}", account.notes)
            return
        self.edit_notes(username)

    def edit_notes(self, username):
        account = next((a for a in self.accounts if a.username == username), None)
        if not account:
            return
        new_note = simpledialog.askstring(
            "Edit Note", f"Enter note for {username}:", initialvalue=account.notes,
        )
        if new_note is not None:
            account.notes = new_note
            save_accounts(self.accounts)
            self.update_account_list()

    def copy_cookie(self, username: str):
        account = next((a for a in self.accounts if a.username == username), None)
        if not account or not account.cookie:
            messagebox.showwarning("Warning", "No cookie found for that account.")
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(account.cookie)
            self.update_idletasks()
            self.status_var.set(f"Cookie copied for {username}")
        except Exception:
            messagebox.showerror("Error", "Could not copy cookie to clipboard.")

    def add_account_cookie(self):
        raw = simpledialog.askstring(
            "Add Account (Cookie)",
            "Paste the full .ROBLOSECURITY cookie value:",
            parent=self,
        )
        if not raw:
            return
        cookie = raw.strip()
        # Allow "name=value" paste
        if "=" in cookie and ".ROBLOSECURITY" in cookie.upper():
            parts = cookie.split("=", 1)
            if len(parts) == 2:
                cookie = parts[1].strip()
        if cookie.endswith(";"):
            cookie = cookie[:-1].strip()
        if not cookie or len(cookie) < 20:
            messagebox.showerror("Error", "That doesn't look like a valid cookie.")
            return

        self.status_var.set("Validating cookie...")
        self.update_idletasks()

        def worker():
            info = validate_cookie(cookie)

            def done():
                if not info:
                    messagebox.showerror(
                        "Error",
                        "Cookie is invalid or expired.\n"
                        "Make sure you copied the full .ROBLOSECURITY value.",
                    )
                    self.status_var.set("Ready")
                    return
                result = {
                    "cookie": info.get("cookie") or cookie,
                    "id": info["id"],
                    "name": info["name"],
                    "displayName": info.get("displayName", info["name"]),
                }
                self.process_browser_result(result)

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def add_account_browser(self):
        self.status_var.set("Starting browser...")
        self.update_idletasks()

        def worker():
            result = login_with_browser(timeout_seconds=300)

            def done():
                if result:
                    self.process_browser_result(result)
                else:
                    messagebox.showerror(
                        "Error", "Failed to capture login. Please try again."
                    )
                    self.status_var.set("Ready")

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def process_browser_result(self, result: dict):
        cookie = result["cookie"]
        user_id = result["id"]
        username = result["name"]
        display_name = result["displayName"]

        def avatar_bg():
            try:
                download_avatar(user_id, force=True)
            except Exception:
                pass

            def refresh():
                self._photo_images.pop(user_id, None)
                for key in list(self._photo_images.keys()):
                    if isinstance(key, tuple) and key and key[0] == user_id:
                        self._photo_images.pop(key, None)
                self.update_account_list()

            self.after(0, refresh)

        for acc in self.accounts:
            if acc.user_id == user_id:
                response = messagebox.askyesno(
                    "Account Exists", f"Account '{username}' already exists.\n\nUpdate cookie?",
                )
                if response:
                    acc.cookie = cookie
                    acc.username = username
                    acc.display_name = display_name
                    acc.last_validated = time.time()
                    save_accounts(self.accounts)
                    self.update_account_list()
                    threading.Thread(target=avatar_bg, daemon=True).start()
                    messagebox.showinfo("Success", "Account updated successfully!")
                self.status_var.set("Ready")
                return

        new_acc = Account(
            username=username,
            user_id=user_id,
            cookie=cookie,
            display_name=display_name,
            added_at=time.time(),
            last_validated=time.time(),
        )
        self.accounts.append(new_acc)
        save_accounts(self.accounts)
        self.update_account_list()
        threading.Thread(target=avatar_bg, daemon=True).start()
        messagebox.showinfo("Success", f"Added {username} (ID: {user_id}) successfully!")
        self.status_var.set("Ready")

    def remove_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select an account first.")
            return

        usernames = []
        for item_id in selected:
            vals = self.tree.item(item_id, "values")
            if vals:
                uname = self._username_from_values(vals)
                if uname:
                    usernames.append(uname)
        if not usernames:
            return

        if len(usernames) == 1:
            prompt = f"Remove account '{usernames[0]}'?"
        else:
            prompt = f"Remove {len(usernames)} selected accounts?"

        if messagebox.askyesno("Confirm Removal", prompt):
            remove_set = set(usernames)
            self.accounts = [a for a in self.accounts if a.username not in remove_set]
            save_accounts(self.accounts)
            # Drop deleted accounts from every custom tab
            changed = False
            for t in self.tabs_data.get("tabs", []):
                if t.get("builtin") or t.get("id") == "all":
                    continue
                before = list(t.get("accounts") or [])
                after = [u for u in before if u not in remove_set]
                if after != before:
                    t["accounts"] = after
                    changed = True
            if changed:
                save_tabs(self.tabs_data)
            self.update_account_list()
            if len(usernames) == 1:
                self.status_var.set(f"Removed {usernames[0]}")
            else:
                self.status_var.set(f"Removed {len(usernames)} accounts")
            
    def validate_all(self):
        if not self.accounts:
            messagebox.showinfo("Info", "No accounts to validate.")
            return
            
        self.status_var.set("Validating & refreshing cookies...")
        self.update()
        
        def worker():
            valid, total, invalid = refresh_all_cookies(self.accounts)
            def done():
                self.update_account_list()
                message = f"{valid}/{total} accounts are valid."
                if invalid:
                    message += f"\n\nInvalid: {', '.join(invalid)}"
                messagebox.showinfo("Validation / Refresh Complete", message)
                self.status_var.set("Ready")
            self.after(0, done)
        
        threading.Thread(target=worker, daemon=True).start()
        
    def launch_selected(self):
        if self._launch_running:
            self._launch_cancel.set()
            self.status_var.set("Cancelling launch...")
            return

        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select an account first.")
            return

        place_id_str = self.place_id_entry.get().strip()
        m = re.search(r"(\d{5,})", place_id_str)
        if not m:
            messagebox.showerror(
                "Error",
                "Place ID must be a number.\n\n"
                "Tip: copy from https://www.roblox.com/games/XXXXXXXXX/...\n"
                "Or double-click a favorite.",
            )
            return

        place_id = int(m.group(1))
        job_id = self.job_id_entry.get().strip()
        link_code = self.link_code_entry.get().strip()
        self._save_launch_fields()

        accounts_to_launch = []
        for item_id in selected:
            vals = self.tree.item(item_id, "values")
            if not vals:
                continue
            uname = self._username_from_values(vals)
            acc = next((a for a in self.accounts if a.username == uname), None)
            if acc:
                accounts_to_launch.append(acc)
        if not accounts_to_launch:
            return

        delay = float(self.config.get("launch_delay", 3.0) or 0)
        total = len(accounts_to_launch)
        self._launch_cancel.clear()
        self._launch_running = True
        self.configure(cursor="watch")
        self.status_var.set(
            f"Launching 1/{total}... (click Launch again to cancel)"
        )
        self.update_idletasks()

        def worker():
            ok_count = 0
            failed = []
            cancelled = False
            for i, account in enumerate(accounts_to_launch):
                if self._launch_cancel.is_set():
                    cancelled = True
                    break
                idx = i + 1
                name = account.username
                self.after(
                    0,
                    lambda n=name, k=idx: self.status_var.set(
                        f"Launching {n} ({k}/{total})... (click Launch to cancel)"
                    ),
                )
                success = launch_account(
                    account,
                    place_id,
                    job_id=job_id,
                    link_code=link_code,
                    accounts=self.accounts,
                )
                if success:
                    ok_count += 1
                else:
                    failed.append(account.username)

                if i < total - 1 and delay > 0 and not self._launch_cancel.is_set():
                    remaining = delay
                    while remaining > 0:
                        if self._launch_cancel.is_set():
                            cancelled = True
                            break
                        rem = remaining
                        done_n = idx
                        self.after(
                            0,
                            lambda r=rem, d=done_n: self.status_var.set(
                                f"Next launch in {r:.1f}s ({d}/{total} done)..."
                            ),
                        )
                        step = min(0.2, remaining)
                        time.sleep(step)
                        remaining -= step

            def done():
                self._launch_running = False
                self.configure(cursor="")
                if cancelled:
                    self.status_var.set(f"Launch cancelled ({ok_count}/{total})")
                elif failed:
                    messagebox.showerror(
                        "Launch failed",
                        f"Launched {ok_count}/{total}.\n\n"
                        f"Failed: {', '.join(failed)}\n\n"
                        "Cookie may be invalid or auth ticket failed.\n"
                        "Try 'Validate / Refresh Cookies' first.",
                    )
                    self.status_var.set(
                        f"Launch: {ok_count} ok, {len(failed)} failed"
                    )
                else:
                    if total == 1:
                        self.status_var.set(
                            f"Launched {accounts_to_launch[0].username}"
                        )
                    else:
                        self.status_var.set(f"Launched {ok_count} accounts")

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def open_browser_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select an account first.")
            return

        # Open browser for the first selected account (browser is single-window)
        item_values = self.tree.item(selected[0], "values")
        username = self._username_from_values(item_values)
        
        account = next((a for a in self.accounts if a.username == username), None)
        if not account:
            return

        self.configure(cursor="watch")
        self.status_var.set(f"Opening browser for {username}...")
        self.update_idletasks()

        def worker():
            ok = open_browser_for_account(account)

            def done():
                self.configure(cursor="")
                if ok:
                    self.status_var.set("Browser opened.")
                else:
                    messagebox.showerror("Error", "Failed to open browser.")
                    self.status_var.set("Ready")

            self.after(0, done)

        threading.Thread(target=worker, daemon=True).start()

    def _hide_to_tray(self):
        """X button: hide window; app stays in the system tray."""
        self.withdraw()
        if self._tray_icon is None:
            # Tray failed to start — quit instead of leaving a ghost process
            self._quit_app()

    def _show_from_tray(self, icon=None, item=None):
        self.after(0, self._restore_window)

    def _restore_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _quit_from_tray(self, icon=None, item=None):
        self.after(0, self._quit_app)

    def _quit_app(self):
        """Fully exit: stop tray, release mutex, close browsers, destroy window."""
        if self._launch_running:
            self._launch_cancel.set()
        try:
            close_managed_browsers()
        except Exception:
            pass
        if self._tray_icon is not None:
            try:
                self._tray_icon.stop()
            except Exception:
                pass
            self._tray_icon = None
        if self.multi_instance_active:
            release_multi_instance()
            self.multi_instance_active = False
        self.destroy()

    def _start_tray(self):
        """System tray icon (notification area / hidden icons)."""
        try:
            import pystray
            from PIL import Image
        except ImportError:
            self.status_var.set("Tray unavailable (pip install pystray pillow)")
            return

        search_dirs = []
        try:
            search_dirs.append(_resource_dir())
        except Exception:
            pass
        search_dirs.append(self._app_dir())
        icon_img = None
        # Prefer pre-rendered 64px; otherwise LANCZOS downscale from master PNG
        for name in ("app_icon_64.png", "app_icon.png"):
            for base in search_dirs:
                path = base / name
                if path.exists():
                    try:
                        icon_img = Image.open(path).convert("RGBA")
                        if icon_img.size != (64, 64):
                            icon_img = icon_img.resize((64, 64), Image.Resampling.LANCZOS)
                        break
                    except Exception:
                        icon_img = None
            if icon_img is not None:
                break
        if icon_img is None:
            icon_img = Image.new("RGBA", (64, 64), color=(40, 40, 40, 255))

        menu = pystray.Menu(
            pystray.MenuItem("Show", self._show_from_tray, default=True),
            pystray.MenuItem("Exit", self._quit_from_tray),
        )
        self._tray_icon = pystray.Icon(
            "RobloxAltManager",
            icon_img,
            "Roblox Alt Manager",
            menu,
        )

        def run_tray():
            try:
                self._tray_icon.run()
            except Exception:
                pass

        self._tray_thread = threading.Thread(target=run_tray, daemon=True)
        self._tray_thread.start()

def _show_unlock_dialog() -> bool:
    """
    Modal master-password dialog.
    - First run / plaintext file → create a new password (and encrypt).
    - Already encrypted → verify password.
    Returns True if the vault was unlocked successfully.
    """
    if not is_crypto_available():
        messagebox.showerror(
            "Missing dependency",
            "The 'cryptography' package is required for secure storage.\n\n"
            "Run:  pip install cryptography",
        )
        return False

    root = tk.Tk()
    root.withdraw()
    root.title("Roblox Alt Manager")
    _apply_window_icon(root)

    encrypted = is_accounts_encrypted()
    title = "Enter Master Password" if encrypted else "Create Master Password"
    prompt = (
        "Enter your master password to unlock the account vault:"
        if encrypted
        else (
            "Set a master password.\n"
            "Your cookies will be encrypted on disk.\n"
            "Without this password the file cannot be decrypted."
        )
    )

    dlg = tk.Toplevel(root)
    dlg.title(title)
    dlg.resizable(False, False)
    dlg.attributes("-topmost", True)
    dlg.grab_set()
    _apply_window_icon(dlg)

    result = {"ok": False}

    frm = ttk.Frame(dlg, padding=16)
    frm.grid(row=0, column=0, sticky="nsew")

    ttk.Label(frm, text=prompt, wraplength=320, justify="left").grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
    )

    ttk.Label(frm, text="Password:").grid(row=1, column=0, sticky="w")
    pw_var = tk.StringVar()
    pw_entry = ttk.Entry(frm, textvariable=pw_var, show="•", width=32)
    pw_entry.grid(row=1, column=1, sticky="ew", pady=4)
    pw_entry.focus_set()

    confirm_var = tk.StringVar()
    if not encrypted:
        ttk.Label(frm, text="Confirm:").grid(row=2, column=0, sticky="w")
        confirm_entry = ttk.Entry(frm, textvariable=confirm_var, show="•", width=32)
        confirm_entry.grid(row=2, column=1, sticky="ew", pady=4)

    status_var = tk.StringVar()
    status_lbl = ttk.Label(frm, textvariable=status_var, foreground="#c44")
    status_lbl.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def try_unlock(event=None):
        pw = pw_var.get()
        if not pw:
            status_var.set("Password cannot be empty.")
            return
        if not encrypted:
            if pw != confirm_var.get():
                status_var.set("Passwords do not match.")
                return
            if len(pw) < 6:
                status_var.set("Use at least 6 characters.")
                return
        try:
            if unlock(pw):
                result["ok"] = True
                dlg.destroy()
                root.destroy()
            else:
                status_var.set("Wrong password.")
                pw_var.set("")
                pw_entry.focus_set()
        except EncryptionError as e:
            status_var.set(str(e))

    def on_cancel():
        result["ok"] = False
        dlg.destroy()
        root.destroy()

    btn_frm = ttk.Frame(frm)
    btn_frm.grid(row=4, column=0, columnspan=2, pady=(16, 0), sticky="e")
    ttk.Button(btn_frm, text="Cancel", command=on_cancel).pack(side="right", padx=(8, 0))
    ttk.Button(btn_frm, text="Unlock" if encrypted else "Create & Encrypt", command=try_unlock).pack(
        side="right"
    )

    dlg.bind("<Return>", try_unlock)
    dlg.protocol("WM_DELETE_WINDOW", on_cancel)

    dlg.update_idletasks()
    w, h = dlg.winfo_width(), dlg.winfo_height()
    x = (dlg.winfo_screenwidth() - w) // 2
    y = (dlg.winfo_screenheight() - h) // 2
    dlg.geometry(f"+{x}+{y}")

    root.wait_window(dlg)
    return result["ok"]


def _write_crash_log(exc: BaseException) -> None:
    """When running as a windowed EXE, silent crashes are hard to debug — log them."""
    try:
        import traceback
        log_path = _app_dir_path() / "crash.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 60 + "\n")
            f.write(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
            traceback.print_exc(file=f)
        # Best-effort message box if Tk is still usable
        try:
            messagebox.showerror(
                "Roblox Alt Manager crashed",
                f"{type(exc).__name__}: {exc}\n\nDetails written to:\n{log_path}",
            )
        except Exception:
            pass
    except Exception:
        pass


if __name__ == "__main__":
    try:
        # Must run before any Tk window so the taskbar uses our icon, not Python's
        _set_windows_app_id()
        if not _ensure_single_instance():
            # Another copy is already running — it was brought to the front
            raise SystemExit(0)
        if not _show_unlock_dialog():
            raise SystemExit(0)
        app = RobloxAltManagerGUI()
        app.title(_WINDOW_TITLE)
        try:
            app.mainloop()
        finally:
            lock()  # wipe key from memory on exit
            if getattr(app, "_tray_icon", None) is not None:
                try:
                    app._tray_icon.stop()
                except Exception:
                    pass
            try:
                lock_path = _app_dir_path() / ".roblox_alt_manager.lock"
                if lock_path.exists():
                    lock_path.unlink(missing_ok=True)
            except Exception:
                pass
    except SystemExit:
        raise
    except BaseException as e:
        _write_crash_log(e)
        raise
