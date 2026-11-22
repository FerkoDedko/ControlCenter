import os
import threading
import time
from tkinter import messagebox, ttk

import customtkinter as ctk
import psutil

from core import procs, theme
from core.utils import format_bytes
from core.widgets import card, font, label
from .base import BasePage


class ProcessesPage(BasePage):
    """Live process list. Data is collected on a background thread so the
    window never freezes while Windows is being queried."""

    INTERVAL = 2.0   # seconds between refreshes
    COLUMNS = (
        ("name", "Name", 380, "w"),
        ("pid", "PID", 90, "e"),
        ("cpu", "CPU", 90, "e"),
        ("mem", "Memory", 120, "e"),
        ("threads", "Threads", 90, "e"),
    )

    def __init__(self, master, toast=None):
        super().__init__(master, toast)
        self._cpu_count = psutil.cpu_count() or 1
        self._tracker = procs.CpuTracker(self._cpu_count)
        self._rows = {}
        self._sort_key, self._sort_desc = "cpu", True
        self._chunks = []          # batches of rows handed over by the worker thread
        self._building = {}
        self._read_ms = 0.0
        self._busy = False
        self._first_done = False
        self._active = False
        self._job = None
        self._last_start = 0.0
        self._rounds = 0

        actions = self.header("Processes", "Everything running on this PC")
        self.search = ctk.CTkEntry(actions, placeholder_text="Search by name or PID…",
                                   width=240, height=36, corner_radius=10,
                                   fg_color=theme.INPUT, border_width=0,
                                   text_color=theme.TEXT)
        self.search.pack(side="left", padx=(0, 10))
        self.search.bind("<KeyRelease>", lambda _e: self._update_tree())
        end_button = ctk.CTkButton(actions, text="End task", width=110, height=36,
                                   corner_radius=10, font=font(12, True),
                                   fg_color=theme.DANGER, hover_color=theme.WARN,
                                   text_color="white", command=self._end_task)
        end_button.pack(side="left")

        body = card(self)
        body.pack(fill="both", expand=True, padx=34, pady=(0, 10))
        inner = ctk.CTkFrame(body, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=8, pady=8)

        self.tree = ttk.Treeview(inner, columns=[c[0] for c in self.COLUMNS],
                                 show="headings", style="CC.Treeview",
                                 selectmode="browse")
        scroll = ttk.Scrollbar(inner, orient="vertical", command=self.tree.yview,
                               style="CC.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        for key, title, width, anchor in self.COLUMNS:
            self.tree.column(key, width=width, anchor=anchor, stretch=(key == "name"))
            self.tree.heading(key, anchor=anchor,
                              command=lambda k=key: self._sort_by(k))
        self._update_headings()
        self._style_tags()
        theme.on_change(self._style_tags)

        self.summary = label(self, "Reading processes…", 10, False, theme.MUTED)
        self.summary.pack(anchor="w", padx=36, pady=(0, 18))

    def _style_tags(self):
        self.tree.tag_configure("hot", foreground=theme.resolve(theme.WARN))

    # ---- lifecycle --------------------------------------------------------
    def on_show(self):
        self._active = True
        self._last_start = 0.0
        self._rounds = 0
        self._tick()

    def on_hide(self):
        self._active = False
        if self._job:
            self.after_cancel(self._job)
            self._job = None

    CHUNK = 40

    def _tick(self):
        if not self._active:
            return
        # Rows arrive in small batches, so the list fills in right away instead of
        # appearing all at once after the slow part is over.
        fresh = False
        while self._chunks:
            batch = self._chunks.pop(0)
            if batch is None:                       # end of one full reading
                self._rows, self._building = self._building, {}
                self._first_done = True
                fresh = True
            else:
                for row in batch:
                    self._building[row["pid"]] = row
                    if not self._first_done:
                        self._rows[row["pid"]] = row     # very first reading: show as it comes
                fresh = True
        if fresh:
            self._update_tree()
        # The first reading has no CPU numbers yet, so take a second one soon.
        wait = 1.0 if self._rounds < 2 else self.INTERVAL
        if not self._busy and time.monotonic() - self._last_start >= wait:
            self._busy = True
            self._last_start = time.monotonic()
            self._rounds += 1
            threading.Thread(target=self._worker, daemon=True).start()
        self._job = self.after(250, self._tick)

    def _worker(self):
        started = time.perf_counter()
        try:
            rows = self._tracker.update(procs.snapshot())
            for start in range(0, len(rows), self.CHUNK):
                self._chunks.append(rows[start:start + self.CHUNK])
            self._chunks.append(None)
            self._read_ms = (time.perf_counter() - started) * 1000
        except Exception:
            pass
        finally:
            self._busy = False

    # ---- table ------------------------------------------------------------
    def _sort_by(self, key):
        if key == self._sort_key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key = key
            self._sort_desc = key in ("cpu", "mem", "threads")
        self._update_headings()
        self._update_tree()

    def _update_headings(self):
        for key, title, _width, _anchor in self.COLUMNS:
            arrow = ""
            if key == self._sort_key:
                arrow = "  ▼" if self._sort_desc else "  ▲"
            self.tree.heading(key, text=title + arrow)

    def _update_tree(self):
        query = self.search.get().strip().lower()
        rows = [r for r in self._rows.values()
                if not query or query in r["name"].lower() or query in str(r["pid"])]
        key = self._sort_key
        rows.sort(key=lambda r: r["name"].lower() if key == "name" else r[key],
                  reverse=self._sort_desc)

        existing = set(self.tree.get_children())
        order = [str(r["pid"]) for r in rows]
        for iid in existing - set(order):
            self.tree.delete(iid)
        for row in rows:
            iid = str(row["pid"])
            values = (row["name"], row["pid"], f"{row['cpu']:.1f}%",
                      format_bytes(row["mem"]), row["threads"])
            tags = ("hot",) if row["cpu"] >= 50 else ()
            if iid in existing:
                self.tree.item(iid, values=values, tags=tags)
            else:
                self.tree.insert("", "end", iid=iid, values=values, tags=tags)
        # Re-ordering hundreds of rows is the slow part, so only do it if needed.
        if list(self.tree.get_children()) != order:
            for index, iid in enumerate(order):
                self.tree.move(iid, "", index)

        threads = sum(r["threads"] for r in self._rows.values())
        self.summary.configure(
            text=f"{len(rows)} of {len(self._rows)} processes shown · "
                 f"{threads:,} threads · refreshes every {int(self.INTERVAL)} s · "
                 f"read in {self._read_ms:,.0f} ms")

    # ---- ending a process -------------------------------------------------
    def _end_task(self):
        selected = self.tree.selection()
        if not selected:
            self.toast("Pick a process", "Select a process in the list first.", "info")
            return
        pid = int(selected[0])
        row = self._rows.get(pid)
        name = row["name"] if row else f"PID {pid}"
        if pid == os.getpid():
            messagebox.showinfo("End task", "That's Command Center itself.",
                                parent=self.winfo_toplevel())
            return
        level = procs.protection(name, pid)
        if level == "blocked":
            messagebox.showwarning(
                "Can't end this one",
                f"“{name}” is a core part of Windows. Ending it would crash or log you out, "
                "so Command Center won't do it.", parent=self.winfo_toplevel())
            return
        if level == "risky":
            if not messagebox.askyesno(
                    "This can disturb Windows",
                    f"“{name}” is part of Windows.\n\n{procs.risk_note(name)}\n\n"
                    f"End it anyway?", icon="warning", default="no",
                    parent=self.winfo_toplevel()):
                return
        elif not messagebox.askyesno(
                "End task",
                f"End “{name}” (PID {pid})?\n\nUnsaved work in that program will be lost.",
                parent=self.winfo_toplevel()):
            return
        try:
            psutil.Process(pid).terminate()
            self.toast("Process ended", f"{name} was asked to close.", "info")
        except psutil.NoSuchProcess:
            self.toast("Already closed", f"{name} is no longer running.", "info")
        except psutil.AccessDenied:
            self.toast("Access denied",
                       "Windows won't let Command Center end this one. "
                       "Try running it as administrator.", "error")
