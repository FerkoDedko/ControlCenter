import os
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core import theme
from core.config import LAUNCHER_PATH, load_json, save_json
from core.utils import IS_WINDOWS, launch, shorten
from core.widgets import font, hover_fade, label
from .base import BasePage

# Handy Windows tools. Windows finds these by name, so no paths are needed.
WINDOWS_TOOLS = [
    ("Notepad", "notepad.exe"),
    ("Calculator", "calc.exe"),
    ("Task Manager", "taskmgr.exe"),
    ("File Explorer", "explorer.exe"),
    ("Command Prompt", "cmd.exe"),
    ("PowerShell", "powershell.exe"),
    ("Control Panel", "control.exe"),
    ("Windows Settings", "ms-settings:"),
]


class AppTile(ctk.CTkFrame):
    """One clickable launcher tile."""

    def __init__(self, master, name, subtitle, on_launch, on_edit=None, on_remove=None):
        super().__init__(master, fg_color=theme.CARD, corner_radius=14,
                         border_width=1, border_color=theme.BORDER)
        badge = ctk.CTkLabel(self, text=(name[:1] or "?").upper(), width=42,
                             height=42, corner_radius=12, font=font(16, True))
        theme.bind(badge, fg_color="soft", text_color="text")
        badge.pack(side="left", padx=(14, 12), pady=14)

        text = ctk.CTkFrame(self, fg_color="transparent")
        text.pack(side="left", fill="x", expand=True, pady=12)
        title = label(text, shorten(name, 22), 12, True)
        title.pack(anchor="w")
        sub = label(text, shorten(subtitle, 30), 9, False, theme.MUTED)
        sub.pack(anchor="w", pady=(2, 0))

        if on_edit or on_remove:
            buttons = ctk.CTkFrame(self, fg_color="transparent")
            buttons.pack(side="right", padx=(0, 8))
            for symbol, action in (("✎", on_edit), ("✕", on_remove)):
                if action:
                    ctk.CTkButton(buttons, text=symbol, width=26, height=26,
                                  fg_color="transparent", hover_color=theme.HOVER,
                                  text_color=theme.MUTED, command=action).pack(
                        side="left")

        # Click the tile (not the little buttons) to launch.
        for widget in (self, badge, text, title, sub):
            widget.bind("<Button-1>", lambda _e: on_launch(), add="+")
        hover_fade(self, theme.CARD, theme.CARD_ALT)


class AppDialog(ctk.CTkToplevel):
    def __init__(self, master, entry, on_save):
        super().__init__(master)
        self.on_save = on_save
        self.title("Edit app" if entry else "Add app")
        self.geometry("500x360")
        self.resizable(False, False)
        self.configure(fg_color=theme.BG)
        self.transient(master.winfo_toplevel())

        label(self, "Edit app" if entry else "Add an app", 18, True).pack(
            anchor="w", padx=24, pady=(22, 14))
        self.name = self._field("Name", entry.get("name", "") if entry else "")

        label(self, "Program or file", 10, True, theme.MUTED).pack(
            anchor="w", padx=24, pady=(10, 4))
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", padx=24)
        self.path = ctk.CTkEntry(row, height=36, corner_radius=10,
                                 fg_color=theme.INPUT, border_width=0,
                                 text_color=theme.TEXT)
        self.path.insert(0, entry.get("path", "") if entry else "")
        self.path.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(row, text="Browse", width=90, height=36, corner_radius=10,
                      fg_color=theme.INPUT, hover_color=theme.HOVER,
                      text_color=theme.TEXT, command=self._browse).pack(
            side="left", padx=(8, 0))

        self.args = self._field("Arguments (optional)",
                                entry.get("args", "") if entry else "")
        self.error = label(self, "", 10, False, theme.DANGER)
        self.error.pack(anchor="w", padx=24, pady=(10, 0))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=14)
        save = ctk.CTkButton(footer, text="Save", width=110, height=38,
                             corner_radius=10, font=font(12, True),
                             command=self._save)
        theme.bind(save, fg_color="main", hover_color="hover")
        save.pack(side="right")
        ctk.CTkButton(footer, text="Cancel", width=100, height=38, corner_radius=10,
                      fg_color=theme.INPUT, hover_color=theme.HOVER,
                      text_color=theme.TEXT, command=self.destroy).pack(
            side="right", padx=8)
        self.after(150, self._focus)

    def _field(self, title, value):
        label(self, title, 10, True, theme.MUTED).pack(anchor="w", padx=24, pady=(10, 4))
        entry = ctk.CTkEntry(self, height=36, corner_radius=10, fg_color=theme.INPUT,
                             border_width=0, text_color=theme.TEXT)
        entry.insert(0, value)
        entry.pack(fill="x", padx=24)
        return entry

    def _focus(self):
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
        except Exception:
            pass

    def _browse(self):
        filetypes = [("Programs and shortcuts", "*.exe *.lnk *.bat *.cmd"),
                     ("All files", "*.*")] if IS_WINDOWS else [("All files", "*.*")]
        chosen = filedialog.askopenfilename(parent=self, title="Choose an app or file",
                                            filetypes=filetypes)
        if chosen:
            self.path.delete(0, "end")
            self.path.insert(0, chosen)
            if not self.name.get().strip():
                self.name.insert(0, Path(chosen).stem)

    def _save(self):
        name, path = self.name.get().strip(), self.path.get().strip()
        if not name or not path:
            self.error.configure(text="Please give the app a name and choose a file.")
            return
        self.on_save({"name": name, "path": path, "args": self.args.get().strip()})
        self.destroy()


class LauncherPage(BasePage):
    COLUMNS = 3

    def __init__(self, master, toast=None):
        super().__init__(master, toast)
        data = load_json(LAUNCHER_PATH, [])
        self.apps = [a for a in data if isinstance(a, dict) and a.get("path")] \
            if isinstance(data, list) else []

        actions = self.header("App Launcher", "Start your favourite apps in one click")
        self.search = ctk.CTkEntry(actions, placeholder_text="Search apps…",
                                   width=220, height=36, corner_radius=10,
                                   fg_color=theme.INPUT, border_width=0,
                                   text_color=theme.TEXT)
        self.search.pack(side="left", padx=(0, 10))
        self.search.bind("<KeyRelease>", lambda _e: self._render())
        add = ctk.CTkButton(actions, text="+  Add app", width=120, height=36,
                            corner_radius=10, font=font(12, True),
                            command=lambda: self._open_dialog(None))
        theme.bind(add, fg_color="main", hover_color="hover")
        add.pack(side="left")

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                             corner_radius=0)
        self.scroll.pack(fill="both", expand=True)
        self._render()

    # ---- drawing ----------------------------------------------------------
    def _render(self):
        for child in self.scroll.winfo_children():
            child.destroy()
        query = self.search.get().strip().lower()

        mine = [(i, a) for i, a in enumerate(self.apps)
                if not query or query in a["name"].lower()]
        self._section("YOUR APPS")
        if mine:
            self._grid([(a["name"], a["path"],
                         lambda a=a: self._launch(a["path"], a.get("args", "")),
                         lambda i=i: self._open_dialog(i),
                         lambda i=i: self._remove(i)) for i, a in mine])
        else:
            label(self.scroll, "Nothing here yet — click “Add app” to pin your first "
                  "program." if not query else "No apps match your search.",
                  10, False, theme.MUTED).pack(anchor="w", padx=36, pady=(0, 10))

        if IS_WINDOWS:
            tools = [(n, c) for n, c in WINDOWS_TOOLS if not query or query in n.lower()]
            if tools:
                self._section("WINDOWS TOOLS")
                self._grid([(n, c, lambda c=c: self._launch(c, ""), None, None)
                            for n, c in tools])

    def _section(self, title):
        label(self.scroll, title, 10, True, theme.MUTED).pack(
            anchor="w", padx=36, pady=(8, 8))

    def _grid(self, items):
        grid = ctk.CTkFrame(self.scroll, fg_color="transparent")
        grid.pack(fill="x", padx=25, pady=(0, 14))
        grid.grid_columnconfigure(tuple(range(self.COLUMNS)), weight=1, uniform="tiles")
        for index, (name, subtitle, launch_cb, edit_cb, remove_cb) in enumerate(items):
            AppTile(grid, name, subtitle, launch_cb, edit_cb, remove_cb).grid(
                row=index // self.COLUMNS, column=index % self.COLUMNS,
                sticky="ew", padx=9, pady=7)

    # ---- actions ----------------------------------------------------------
    def _launch(self, target, args):
        # Our own pinned apps are real paths, so tell the user clearly if one moved.
        if os.path.isabs(target) and not os.path.exists(target):
            self.toast("Can't find that file", f"{target} no longer exists.", "error")
            return
        try:
            launch(target, args)
        except OSError as exc:
            self.toast("Couldn't start it", str(exc), "error")

    def _open_dialog(self, index):
        entry = self.apps[index] if index is not None else None

        def saved(new_entry):
            if index is None:
                self.apps.append(new_entry)
            else:
                self.apps[index] = new_entry
            self._store()
            self._render()

        AppDialog(self, entry, saved)

    def _remove(self, index):
        removed = self.apps.pop(index)
        self._store()
        self._render()
        self.toast("Removed", f"{removed['name']} was removed from the launcher.", "info")

    def _store(self):
        try:
            save_json(LAUNCHER_PATH, self.apps)
        except OSError as exc:
            self.toast("Couldn't save", str(exc), "error")
