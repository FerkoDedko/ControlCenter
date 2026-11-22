import threading
from tkinter import messagebox

import customtkinter as ctk

from core import anim, cleanup, theme
from core.utils import format_bytes
from core.widgets import card, font, label
from .base import BasePage


class CleanupPage(BasePage):
    """Scan for junk, tick what you want gone, press Clean. Nothing is removed
    until you confirm, and only the folders listed on this page are touched."""

    def __init__(self, master, toast=None):
        super().__init__(master, toast)
        self.targets = cleanup.default_targets()
        self.sizes = {}                  # key -> (bytes, files)
        self.checks = {}                 # key -> BooleanVar
        self.size_labels = {}
        self._job = None                 # background work: {"kind", "done", ...}
        self._shown_total = 0.0

        actions = self.header("Cleanup", "Free up space by removing files you don't need")
        self.scan_button = ctk.CTkButton(actions, text="Scan", width=100, height=36,
                                         corner_radius=10, font=font(12, True),
                                         command=self.scan)
        theme.bind(self.scan_button, fg_color="main", hover_color="hover")
        self.scan_button.pack(side="left", padx=(0, 10))
        self.clean_button = ctk.CTkButton(actions, text="Clean selected", width=140,
                                          height=36, corner_radius=10,
                                          font=font(12, True), fg_color=theme.DANGER,
                                          hover_color=theme.WARN, text_color="white",
                                          command=self.clean)
        self.clean_button.pack(side="left")

        summary = card(self)
        summary.pack(fill="x", padx=34, pady=(0, 14))
        label(summary, "YOU CAN FREE UP", 10, True, theme.MUTED).pack(
            anchor="w", padx=20, pady=(16, 2))
        self.total_label = label(summary, "—", 30, True)
        self.total_label.pack(anchor="w", padx=20)
        self.status = label(summary, "Press Scan to see what can be cleaned.",
                            10, False, theme.MUTED)
        self.status.pack(anchor="w", padx=20, pady=(2, 16))

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                             corner_radius=0)
        self.scroll.pack(fill="both", expand=True)
        for target in self.targets:
            self._row(target)

    def _row(self, target):
        row = card(self.scroll, corner_radius=12)
        row.pack(fill="x", padx=34, pady=5)
        var = ctk.BooleanVar(value=True)
        self.checks[target.key] = var
        box = ctk.CTkCheckBox(row, text="", variable=var, width=24, checkbox_width=22,
                              checkbox_height=22, corner_radius=6, border_width=2,
                              command=self._update_total)
        theme.bind(box, fg_color="main", hover_color="hover")
        box.pack(side="left", padx=(16, 4), pady=14)

        text = ctk.CTkFrame(row, fg_color="transparent")
        text.pack(side="left", fill="x", expand=True, pady=12)
        label(text, target.name, 11, True).pack(anchor="w")
        label(text, target.description, 9, False, theme.MUTED, wraplength=560,
              justify="left").pack(anchor="w", pady=(3, 0))
        size = label(row, "—", 12, True, anchor="e", width=110)
        size.pack(side="right", padx=18)
        self.size_labels[target.key] = size

    # ---- totals ---------------------------------------------------------------
    def _selected_total(self):
        return sum(self.sizes.get(t.key, (0, 0))[0] for t in self.targets
                   if self.checks[t.key].get())

    def _update_total(self):
        total = float(self._selected_total())

        def step(value):
            self._shown_total = value
            self.total_label.configure(text=format_bytes(value))

        anim.animate(self.total_label, "total", self._shown_total, total, 500, step, kind="meters")

    # ---- scanning ---------------------------------------------------------------
    def on_show(self):
        if not self.sizes and not self._job:
            self.scan()

    def scan(self):
        if self._job:
            return
        job = {"kind": "scan", "done": False, "results": {}}
        self._job = job
        self._set_busy(True, "Scanning…")
        for label_widget in self.size_labels.values():
            label_widget.configure(text="…")

        def work():
            for target in self.targets:
                try:
                    job["results"][target.key] = cleanup.scan_target(target)
                except Exception:
                    job["results"][target.key] = (0, 0)
            job["done"] = True

        threading.Thread(target=work, daemon=True).start()
        self._poll()

    # ---- cleaning ----------------------------------------------------------------
    def clean(self):
        if self._job:
            return
        chosen = [t for t in self.targets if self.checks[t.key].get()
                  and self.sizes.get(t.key, (0, 0))[0] > 0]
        if not chosen:
            self.toast("Nothing to clean", "Scan first, and tick at least one item.", "info")
            return
        total = sum(self.sizes[t.key][0] for t in chosen)
        names = "\n".join(f"  •  {t.name}" for t in chosen)
        if not messagebox.askyesno(
                "Clean selected",
                f"Permanently remove about {format_bytes(total)}?\n\n{names}\n\n"
                "This can't be undone.", parent=self.winfo_toplevel()):
            return
        job = {"kind": "clean", "done": False, "freed": 0, "deleted": 0, "failed": 0}
        self._job = job
        self._set_busy(True, "Cleaning…")

        def work():
            for target in chosen:
                result = cleanup.clean_target(target)
                job["freed"] += result.freed
                job["deleted"] += result.deleted
                job["failed"] += result.failed
            job["done"] = True

        threading.Thread(target=work, daemon=True).start()
        self._poll()

    # ---- background polling ---------------------------------------------------------
    def _poll(self):
        job = self._job
        if job is None:
            return
        if not job["done"]:
            self.after(200, self._poll)
            return
        self._job = None
        self._set_busy(False)
        if job["kind"] == "scan":
            self.sizes = dict(job["results"])
            for target in self.targets:
                size, files = self.sizes.get(target.key, (0, 0))
                self.size_labels[target.key].configure(
                    text=format_bytes(size) if size else "Nothing to clean")
            self.status.configure(text="Tick what you want removed, then press Clean selected.")
            self._update_total()
        else:
            note = f" ({job['failed']:,} files were in use and skipped)" if job["failed"] else ""
            self.toast("Cleanup finished",
                       f"Freed {format_bytes(job['freed'])} from {job['deleted']:,} files.{note}",
                       "info")
            self.sizes = {}
            self.scan()

    def _set_busy(self, busy, text=None):
        state = "disabled" if busy else "normal"
        self.scan_button.configure(state=state)
        self.clean_button.configure(state=state)
        if text:
            self.status.configure(text=text)
