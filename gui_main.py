#!/usr/bin/env python3
"""
Roblox Alt Manager - GUI with 24x24 avatars, favorites, cookie rotation
"""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import time
import threading
import re
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
    unlock,
    lock,
    is_accounts_encrypted,
    is_crypto_available,
    EncryptionError,
    change_password,
)
import uuid

class RobloxAltManagerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("Roblox Alt Manager")
        self.geometry("980x560")
        self.minsize(820, 460)
        
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
        
        self.colors = {
            "dark": {
                "bg": "#2b2b2b", "fg": "#ffffff", "frame_bg": "#383838",
                "btn_bg": "#505050", "btn_fg": "#ffffff",
                "tree_bg": "#333333", "tree_fg": "#ffffff",
            },
            "light": {
                "bg": "#f0f0f0", "fg": "#000000", "frame_bg": "#e0e0e0",
                "btn_bg": "#d0d0d0", "btn_fg": "#000000",
                "tree_bg": "#ffffff", "tree_fg": "#000000",
            },
        }
        
        self.style = ttk.Style()
        self.apply_theme()
        self.create_widgets()
        
        # Restore multi-instance from saved setting (works even if Roblox is already open)
        if self.config.get("multi_instance", False):
            if enable_multi_instance():
                self.multi_instance_active = True
                self.status_var.set("Multi-instance ACTIVE")
            else:
                # Keep the preference saved; user can retry from Settings
                self.status_var.set("Multi-instance saved but failed to enable")
        
        # Release mutex cleanly on close
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
        # Force avatar re-check on every launch, then populate list
        self.status_var.set("Refreshing avatars...")
        self.after(50, self._startup_avatar_refresh)
        
        if self.auto_refresh:
            self.schedule_cookie_refresh()
        
    def apply_theme(self):
        theme_colors = self.colors[self.current_theme]
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
            background=[("selected", "#0078d7")],
            foreground=[("selected", "#ffffff")],
        )

    def toggle_theme(self):
        self.current_theme = "light" if self.current_theme == "dark" else "dark"
        self.config["theme"] = self.current_theme
        save_config(self.config)
        self.apply_theme()
        self.update_widget_colors(self, self.colors[self.current_theme])
        if hasattr(self, "tab_bar"):
            self._rebuild_tab_bar()
        
    def update_widget_colors(self, widget, colors):
        widget_type = widget.winfo_class()
        if widget_type in ["Frame", "Labelframe"]:
            try:
                widget.configure(bg=colors["frame_bg"])
            except Exception:
                pass
        elif widget_type in ["Label", "Button"]:
            try:
                widget.configure(bg=colors["btn_bg"], fg=colors["btn_fg"])
            except Exception:
                pass
        elif widget_type in ["Entry"]:
            try:
                widget.configure(bg="#ffffff", fg="#000000")
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
        
        # Browser-style tab bar
        self.tab_bar = tk.Frame(list_frame, bg=theme_colors["frame_bg"])
        self.tab_bar.pack(fill="x", padx=2, pady=(2, 0))
        self._rebuild_tab_bar()
        
        columns = ("Username", "User ID", "Display Name", "Notes")
        self.tree = ttk.Treeview(
            list_frame, columns=columns, show="tree headings", selectmode="extended",
        )
        
        self.tree.heading("#0", text="")
        self.tree.heading("Username", text="Username")
        self.tree.heading("User ID", text="User ID")
        self.tree.heading("Display Name", text="Display Name")
        self.tree.heading("Notes", text="Notes")
        
        # Icon column: tight + left-aligned so avatars sit next to usernames
        self.tree.column("#0", width=32, minwidth=28, stretch=False, anchor="w")
        self.tree.column("Username", width=150, minwidth=100)
        self.tree.column("User ID", width=100, minwidth=80)
        self.tree.column("Display Name", width=140, minwidth=80)
        self.tree.column("Notes", width=180, minwidth=80)
        
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Bind once (not on every list refresh)
        self._drag = {"item": None, "y": 0, "active": False}
        self.tree.bind("<ButtonPress-1>", self.on_tree_press)
        self.tree.bind("<B1-Motion>", self.on_tree_motion)
        self.tree.bind("<ButtonRelease-1>", self.on_tree_release)
        self.tree.bind("<Double-Button-1>", self.on_tree_double_click)
        self.tree.bind("<Button-3>", self.on_tree_right_click)
        
        # --- Favorites panel ---
        fav_frame = tk.LabelFrame(
            content, text="  ★ Favorite Games  ",
            bg=theme_colors["frame_bg"], fg=theme_colors["fg"],
            padx=4, pady=4,
        )
        fav_frame.pack(side="right", fill="y", padx=(6, 0))
        
        self.fav_list = tk.Listbox(
            fav_frame, width=28, height=14,
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
        
        # Bottom launch bar
        bottom_frame = tk.Frame(self, bg=theme_colors["frame_bg"], pady=5)
        bottom_frame.pack(fill="x", padx=5)
        
        tk.Label(
            bottom_frame, text="Place ID:",
            bg=theme_colors["frame_bg"], fg=theme_colors["fg"],
        ).pack(side="left", padx=2)
        self.place_id_entry = tk.Entry(bottom_frame, width=16)
        self.place_id_entry.pack(side="left", padx=2)
        
        tk.Label(
            bottom_frame, text="Job ID:",
            bg=theme_colors["frame_bg"], fg=theme_colors["fg"],
        ).pack(side="left", padx=2)
        self.job_id_entry = tk.Entry(bottom_frame, width=16)
        self.job_id_entry.pack(side="left", padx=2)
        
        tk.Label(
            bottom_frame, text="Link Code:",
            bg=theme_colors["frame_bg"], fg=theme_colors["fg"],
        ).pack(side="left", padx=2)
        self.link_code_entry = tk.Entry(bottom_frame, width=16)
        self.link_code_entry.pack(side="left", padx=2)
        
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

    # ------------------------------------------------------------------
    # Startup: force avatar refresh every launch
    # ------------------------------------------------------------------
    def _startup_avatar_refresh(self):
        def worker():
            ids = [a.user_id for a in self.accounts]
            if ids:
                refresh_all_avatars(ids)
            def done():
                self._photo_images.clear()
                self.update_account_list()
                if self.multi_instance_active:
                    self.status_var.set("Multi-instance ACTIVE")
                else:
                    self.status_var.set("Ready")
            self.after(0, done)
        threading.Thread(target=worker, daemon=True).start()

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
        self.status_var.set(f"Loaded: {g.name} ({g.place_id})")

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
        
        theme_var = tk.StringVar(
            value="Dark Mode" if self.current_theme == "dark" else "Light Mode"
        )
        theme_box = ttk.Combobox(
            theme_row,
            textvariable=theme_var,
            values=("Dark Mode", "Light Mode"),
            state="readonly",
            width=14,
        )
        theme_box.pack(side="left", padx=(8, 0))
        
        def on_theme_change(_event=None):
            choice = theme_var.get()
            new_theme = "dark" if choice == "Dark Mode" else "light"
            if new_theme != self.current_theme:
                self.current_theme = new_theme
                self.config["theme"] = new_theme
                save_config(self.config)
                self.apply_theme()
                self.update_widget_colors(self, self.colors[self.current_theme])
                if hasattr(self, "tab_bar"):
                    self._rebuild_tab_bar()
                # Refresh settings window colors
                settings_win.configure(bg=self.colors[self.current_theme]["frame_bg"])
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
                    self.accounts = load_accounts()
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
                usernames.append(vals[0])

        menu = tk.Menu(self, tearoff=0)
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
    def _load_avatar_image(self, user_id: int):
        if user_id in self._photo_images:
            return self._photo_images[user_id]
        path = download_avatar(user_id, size="48x48", force=False)
        if path and path.exists():
            try:
                img = tk.PhotoImage(file=str(path))
                # 48 → ~24 px
                img = img.subsample(2, 2)
                self._photo_images[user_id] = img
                return img
            except Exception:
                pass
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

    def update_account_list(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        for acc in self._accounts_for_active_tab():
            note_text = self._notes_preview(acc.notes)
            img = self._load_avatar_image(acc.user_id)
            self.tree.insert(
                "",
                "end",
                text="",
                image=img if img else "",
                values=(acc.username, acc.user_id, acc.display_name, note_text),
            )

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
                usernames.append(vals[0])

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
        username = item_values[0]
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
        if note_cell.startswith("ⓘ") and self._notes_icon_hit(event, row_id):
            username = item_values[0]
            account = next((a for a in self.accounts if a.username == username), None)
            if account and account.notes:
                messagebox.showinfo(f"Notes for {username}", account.notes)
            return
        username = item_values[0]
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

    def add_account_browser(self):
        self.status_var.set("Starting browser... Please wait.")
        self.update()
        
        result = login_with_browser(timeout_seconds=300)
        
        if result:
            self.process_browser_result(result)
        else:
            messagebox.showerror("Error", "Failed to capture login. Please try again.")
            self.status_var.set("Ready")
            
    def process_browser_result(self, result: dict):
        cookie = result["cookie"]
        user_id = result["id"]
        username = result["name"]
        display_name = result["displayName"]
        
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
                    # Force fresh avatar for this user
                    download_avatar(user_id, force=True)
                    self._photo_images.pop(user_id, None)
                    self.update_account_list()
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
        download_avatar(user_id, force=True)
        self.update_account_list()
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
                usernames.append(vals[0])
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
                self.accounts = load_accounts()
                self.update_account_list()
                message = f"{valid}/{total} accounts are valid."
                if invalid:
                    message += f"\n\nInvalid: {', '.join(invalid)}"
                messagebox.showinfo("Validation / Refresh Complete", message)
                self.status_var.set("Ready")
            self.after(0, done)
        
        threading.Thread(target=worker, daemon=True).start()
        
    def launch_selected(self):
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

        accounts_to_launch = []
        for item_id in selected:
            vals = self.tree.item(item_id, "values")
            if not vals:
                continue
            acc = next((a for a in self.accounts if a.username == vals[0]), None)
            if acc:
                accounts_to_launch.append(acc)
        if not accounts_to_launch:
            return

        # Busy cursor + status only — no success popups
        delay = float(self.config.get("launch_delay", 3.0) or 0)
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            ok_count = 0
            failed = []
            total = len(accounts_to_launch)
            for i, account in enumerate(accounts_to_launch):
                self.status_var.set(
                    f"Launching {account.username} ({i + 1}/{total})..."
                )
                self.update_idletasks()
                success = launch_account(
                    account, place_id, job_id=job_id, link_code=link_code, accounts=self.accounts,
                )
                if success:
                    ok_count += 1
                else:
                    failed.append(account.username)

                # Wait between launches so each Roblox client can start
                if i < total - 1 and delay > 0:
                    remaining = delay
                    while remaining > 0:
                        self.status_var.set(
                            f"Next launch in {remaining:.1f}s "
                            f"({i + 1}/{total} done)..."
                        )
                        self.update()
                        step = min(0.25, remaining)
                        time.sleep(step)
                        remaining -= step

            self.accounts = load_accounts()
            if failed:
                # Only popup on real failure
                messagebox.showerror(
                    "Launch failed",
                    f"Launched {ok_count}/{total}.\n\n"
                    f"Failed: {', '.join(failed)}\n\n"
                    "Cookie may be invalid or auth ticket failed.\n"
                    "Try 'Validate / Refresh Cookies' first.",
                )
                self.status_var.set(f"Launch: {ok_count} ok, {len(failed)} failed")
            else:
                if total == 1:
                    self.status_var.set(f"Launched {accounts_to_launch[0].username}")
                else:
                    self.status_var.set(f"Launched {ok_count} accounts")
        finally:
            self.configure(cursor="")
            
    def open_browser_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Warning", "Please select an account first.")
            return

        # Open browser for the first selected account (browser is single-window)
        item_values = self.tree.item(selected[0], "values")
        username = item_values[0]
        
        account = next((a for a in self.accounts if a.username == username), None)
        if not account:
            return

        self.configure(cursor="watch")
        self.status_var.set(f"Opening browser for {username}...")
        self.update_idletasks()
        try:
            if open_browser_for_account(account):
                self.status_var.set("Browser opened.")
            else:
                messagebox.showerror("Error", "Failed to open browser.")
                self.status_var.set("Ready")
        finally:
            self.configure(cursor="")

    def _on_close(self):
        """Release multi-instance mutex and exit cleanly."""
        if self.multi_instance_active:
            release_multi_instance()
            self.multi_instance_active = False
        self.destroy()

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
    root.title("Roblox Alt Manager – Unlock")
    root.attributes("-topmost", True)

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

    # Simple custom dialog so we can ask for confirmation on first run
    dlg = tk.Toplevel(root)
    dlg.title(title)
    dlg.resizable(False, False)
    dlg.attributes("-topmost", True)
    dlg.grab_set()

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

    # Center
    dlg.update_idletasks()
    w, h = dlg.winfo_width(), dlg.winfo_height()
    x = (dlg.winfo_screenwidth() - w) // 2
    y = (dlg.winfo_screenheight() - h) // 2
    dlg.geometry(f"+{x}+{y}")

    root.wait_window(dlg)
    return result["ok"]


if __name__ == "__main__":
    if not _show_unlock_dialog():
        raise SystemExit(0)
    app = RobloxAltManagerGUI()
    app.mainloop()
    lock()  # wipe key from memory on exit
