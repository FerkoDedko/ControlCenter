import os
import threading
from pathlib import Path

import customtkinter as ctk
import psutil

from core import anim, theme
from core.scanner import CATEGORIES, StorageScan
from core.utils import format_bytes, reveal_in_folder, shorten
from core.widgets import bind_tree, card, font, hover_fade, label
from .base import BasePage

CATEGORY_COLORS = {
    "games": ("#7c5cf0", "#a78bfa"),
    "photos": ("#169c70", "#42d6a0"),
    "videos": ("#d9486f", "#f272a0"),
    "music": ("#e07b1a", "#f5a04a"),
    "documents": ("#2f6df2", "#579bff"),
    "archives": ("#c9a21a", "#f2d05c"),
    "apps": ("#1c97b5", "#4cc4e0"),
    "system": ("#6b7a90", "#8e9bb0"),
    "other": ("#8a94a6", "#6f7c92"),
}


def usage_color(percent):
    if percent >= 90:
        return theme.DANGER
    if percent >= 75:
        return theme.WARN
    return theme.METRIC["disk"]


class DriveCard(ctk.CTkFrame):
    def __init__(self, master, mountpoint, fstype):
        super().__init__(master, fg_color=theme.CARD, corner_radius=16,
                         border_width=1, border_color=theme.BORDER)
        self._display = 0.0
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=18, pady=(16, 4))
        label(top, f"▦  {mountpoint}", 13, True).pack(side="left")
        label(top, fstype or "drive", 10, False, theme.MUTED).pack(side="right")
        self.percent = label(self, "—", 24, True)
        self.percent.pack(anchor="w", padx=18)
        self.detail = label(self, "", 10, False, theme.MUTED)
        self.detail.pack(anchor="w", padx=18, pady=(0, 8))
        self.bar = ctk.CTkProgressBar(self, height=8, corner_radius=8,
                                      fg_color=theme.TRACK)
        self.bar.pack(fill="x", padx=18, pady=(0, 17))
        self.bar.set(0)

    def update_usage(self, usage):
        self.detail.configure(
            text=f"{format_bytes(usage.used)} used of {format_bytes(usage.total)}"
                 f"  ·  {format_bytes(usage.free)} free")
        color = usage_color(usage.percent)
        self.bar.configure(progress_color=color)
        self.percent.configure(text_color=color if usage.percent >= 75 else theme.TEXT)

        def step(value):
            self._display = value
            self.percent.configure(text=f"{value:.1f}% used")
            self.bar.set(value / 100)

        anim.animate(self, "fill", self._display, usage.percent, 600, step, kind="meters")


class CategoryCard(ctk.CTkFrame):
    """One tile such as Games or Photos. Click it to see its biggest files."""

    def __init__(self, master, key, name, icon, on_select):
        super().__init__(master, fg_color=theme.CARD, corner_radius=16,
                         border_width=1, border_color=theme.BORDER)
        self.key = key
        self._size = 0.0
        self._selected = False
        color = CATEGORY_COLORS[key]

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(14, 2))
        ctk.CTkLabel(top, text=icon, width=38, height=38, corner_radius=11,
                     font=font(17), fg_color=theme.INPUT).pack(side="left")
        names = ctk.CTkFrame(top, fg_color="transparent")
        names.pack(side="left", padx=11)
        label(names, name, 12, True).pack(anchor="w")
        self.detail = label(names, "Not scanned yet", 9, False, theme.MUTED)
        self.detail.pack(anchor="w", pady=(1, 0))

        self.size_label = label(self, "—", 22, True)
        self.size_label.pack(anchor="w", padx=16, pady=(6, 6))
        self.bar = ctk.CTkProgressBar(self, height=7, corner_radius=8,
                                      fg_color=theme.TRACK, progress_color=color)
        self.bar.pack(fill="x", padx=16, pady=(0, 16))
        self.bar.set(0)

        bind_tree(self, "<Button-1>", lambda _e: on_select(key))
        hover_fade(self, theme.CARD, theme.CARD_ALT)

    def set_data(self, size, files, total):
        share = (size / total) if total else 0.0
        self.detail.configure(text=f"{files:,} files  ·  {share * 100:.1f}%")

        def step(value):
            self._size = value
            self.size_label.configure(text=format_bytes(value))

        anim.animate(self, "size", self._size, float(size), 280, step, kind="meters")
        anim.animate(self.bar, "share", self.bar.get(), share, 280, self.bar.set, kind="meters")

    def set_selected(self, selected):
        if selected == self._selected:
            return
        self._selected = selected
        if selected:
            self.configure(border_color=theme.accent("main"), border_width=2)
        else:
            self.configure(border_color=theme.BORDER, border_width=1)


class StoragePage(BasePage):
    REFRESH_MS = 5000
    POLL_MS = 300

    def __init__(self, master, toast=None):
        super().__init__(master, toast)
        self._active = False
        self._job = None
        self._drive_cards = {}
        self._cards = {}
        self._targets = {}
        self._scan = None
        self._selected = None

        self.header("Storage", "Your drives and what is using the space")
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                             corner_radius=0)
        self.scroll.pack(fill="both", expand=True)

        self.drives = ctk.CTkFrame(self.scroll, fg_color="transparent")
        self.drives.pack(fill="x", padx=25)
        self.drives.grid_columnconfigure((0, 1), weight=1, uniform="drives")

        self._build_breakdown()

    # ---- breakdown ----------------------------------------------------------
    def _build_breakdown(self):
        label(self.scroll, "WHAT'S TAKING UP SPACE", 10, True, theme.MUTED).pack(
            anchor="w", padx=36, pady=(18, 8))

        controls = ctk.CTkFrame(self.scroll, fg_color="transparent")
        controls.pack(fill="x", padx=34)
        self.target_var = ctk.StringVar()
        self.target_menu = ctk.CTkOptionMenu(
            controls, values=["…"], variable=self.target_var, width=330, height=36,
            fg_color=theme.INPUT, text_color=theme.TEXT,
            dropdown_fg_color=theme.CARD, dropdown_text_color=theme.TEXT,
            dropdown_hover_color=theme.HOVER)
        theme.bind(self.target_menu, button_color="main", button_hover_color="hover")
        self.target_menu.pack(side="left")
        self.scan_button = ctk.CTkButton(controls, text="Scan", width=100, height=36,
                                         corner_radius=10, font=font(12, True),
                                         command=self._toggle_scan)
        theme.bind(self.scan_button, fg_color="main", hover_color="hover")
        self.scan_button.pack(side="left", padx=10)
        self.status = label(controls, "Pick where to look, then press Scan.",
                            10, False, theme.MUTED)
        self.status.pack(side="left", padx=6)

        grid = ctk.CTkFrame(self.scroll, fg_color="transparent")
        grid.pack(fill="x", padx=25, pady=(8, 0))
        grid.grid_columnconfigure((0, 1, 2), weight=1, uniform="cats")
        for index, (key, name, icon) in enumerate(CATEGORIES):
            tile = CategoryCard(grid, key, name, icon, self._select)
            tile.grid(row=index // 3, column=index % 3, sticky="ew", padx=9, pady=8)
            self._cards[key] = tile

        self.files_panel = card(self.scroll)
        self.files_panel.pack(fill="x", padx=34, pady=(10, 26))
        self.files_title = label(self.files_panel, "LARGEST FILES", 10, True, theme.MUTED)
        self.files_title.pack(anchor="w", padx=19, pady=(17, 8))
        self.files_body = ctk.CTkFrame(self.files_panel, fg_color="transparent")
        self.files_body.pack(fill="x", padx=19, pady=(0, 14))
        label(self.files_body, "Run a scan, then click a card to see its biggest files.",
              10, False, theme.MUTED).pack(anchor="w")

    def _build_targets(self):
        targets = {f"My user folder   ({shorten(str(Path.home()), 30)})": str(Path.home())}
        for partition in psutil.disk_partitions(all=False):
            if partition.fstype:
                targets[f"Whole drive   {partition.mountpoint}"] = partition.mountpoint
        if list(targets) != list(self._targets):
            self._targets = targets
            self.target_menu.configure(values=list(targets))
            if self.target_var.get() not in targets:
                self.target_var.set(next(iter(targets)))

    def _toggle_scan(self):
        if self._scan and not self._scan.done:
            self._scan.cancel()
            self._scan = None
            self.scan_button.configure(text="Scan")
            self.status.configure(text="Scan cancelled.")
            return
        root = self._targets.get(self.target_var.get())
        if not root or not os.path.isdir(root):
            self.status.configure(text="That location isn't available.")
            return
        scan = StorageScan(root)
        self._scan = scan
        for tile in self._cards.values():
            tile.set_data(0, 0, 0)
        self.scan_button.configure(text="Cancel")
        threading.Thread(target=scan.run, daemon=True).start()
        self._poll_scan(scan)

    def _poll_scan(self, scan):
        if scan is not self._scan or scan.cancelled:
            return
        total = scan.total_bytes
        for key, tile in self._cards.items():
            tile.set_data(scan.bytes[key], scan.files[key], total)
        if scan.done:
            self.scan_button.configure(text="Scan")
            if scan.error:
                self.status.configure(text=f"Scan stopped: {scan.error}")
            else:
                self.status.configure(
                    text=f"Done — {scan.total_files:,} files, {format_bytes(total)} "
                         f"in {scan.elapsed:.0f} s")
            if self._selected is None:
                biggest = max(scan.bytes, key=scan.bytes.get)
                self._select(biggest)
            else:
                self._select(self._selected)
            return
        self.status.configure(
            text=f"Scanning…  {scan.total_files:,} files  ·  {format_bytes(total)}")
        self.after(self.POLL_MS, lambda: self._poll_scan(scan))

    # ---- largest files ------------------------------------------------------
    def _select(self, key):
        self._selected = key
        for tile_key, tile in self._cards.items():
            tile.set_selected(tile_key == key)
        name = next(n for k, n, _i in CATEGORIES if k == key)
        self.files_title.configure(text=f"LARGEST FILES  ·  {name.upper()}")
        for child in self.files_body.winfo_children():
            child.destroy()
        files = self._scan.top_files(key) if self._scan else []
        if not files:
            label(self.files_body, "Nothing found in this category yet.", 10, False,
                  theme.MUTED).pack(anchor="w")
            return
        for size, path in files:
            row = ctk.CTkFrame(self.files_body, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkButton(row, text="📂", width=34, height=28,
                          fg_color="transparent", hover_color=theme.HOVER,
                          text_color=theme.TEXT_SOFT,
                          command=lambda p=path: self._reveal(p)).pack(side="right")
            label(row, format_bytes(size), 10, True, anchor="e", width=90).pack(
                side="right", padx=(0, 6))
            text = ctk.CTkFrame(row, fg_color="transparent")
            text.pack(side="left", fill="x", expand=True)
            label(text, shorten(os.path.basename(path), 60), 10, True).pack(anchor="w")
            label(text, shorten(os.path.dirname(path), 90), 9, False,
                  theme.MUTED).pack(anchor="w")

    def _reveal(self, path):
        try:
            reveal_in_folder(path)
        except OSError as exc:
            self.toast("Couldn't open the folder", str(exc), "error")

    # ---- drives -------------------------------------------------------------
    def on_show(self):
        self._active = True
        self._build_targets()
        self._refresh_drives()

    def on_hide(self):
        self._active = False
        if self._job:
            self.after_cancel(self._job)
            self._job = None

    def _refresh_drives(self):
        if not self._active:
            return
        found = {}
        for partition in psutil.disk_partitions(all=False):
            if not partition.fstype:
                continue
            try:
                found[partition.mountpoint] = (partition.fstype,
                                               psutil.disk_usage(partition.mountpoint))
            except (PermissionError, OSError):
                continue

        if set(found) != set(self._drive_cards):
            for existing in self._drive_cards.values():
                existing.destroy()
            self._drive_cards = {}
            for index, (mount, (fstype, _usage)) in enumerate(found.items()):
                drive = DriveCard(self.drives, mount, fstype)
                drive.grid(row=index // 2, column=index % 2, sticky="ew",
                           padx=9, pady=9)
                self._drive_cards[mount] = drive
        for mount, (_fstype, usage) in found.items():
            self._drive_cards[mount].update_usage(usage)
        self._job = self.after(self.REFRESH_MS, self._refresh_drives)
