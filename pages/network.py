import socket
import threading
import time
from tkinter import ttk

import customtkinter as ctk
import psutil

from core import theme
from core.utils import format_bytes, format_speed
from core.widgets import Sparkline, card, label
from .base import BasePage


class SpeedCard(ctk.CTkFrame):
    def __init__(self, master, title, color):
        super().__init__(master, fg_color=theme.CARD, corner_radius=16,
                         border_width=1, border_color=theme.BORDER)
        self.peak = 0.0
        label(self, title, 10, True, color).pack(anchor="w", padx=18, pady=(16, 3))
        self.value = label(self, "0.0 KB/s", 26, True)
        self.value.pack(anchor="w", padx=18)
        self.peak_label = label(self, "Peak this session: —", 10, False, theme.MUTED)
        self.peak_label.pack(anchor="w", padx=18, pady=(0, 6))
        self.spark = Sparkline(self, color, height=80, floor=100 * 1024.0)
        self.spark.pack(fill="x", padx=18, pady=(0, 16))

    def update_speed(self, speed):
        self.value.configure(text=format_speed(speed))
        self.spark.push(speed)
        if speed > self.peak:
            self.peak = speed
            self.peak_label.configure(text=f"Peak this session: {format_speed(speed)}")


class NetworkPage(BasePage):
    COLUMNS = (
        ("name", "Interface", 220, "w"),
        ("status", "Status", 70, "w"),
        ("ip", "IPv4 address", 140, "w"),
        ("speed", "Link speed", 90, "e"),
        ("down", "Download", 100, "e"),
        ("up", "Upload", 100, "e"),
        ("received", "Received", 100, "e"),
        ("sent", "Sent", 100, "e"),
    )

    def __init__(self, master, toast=None):
        super().__init__(master, toast)
        self._active = False
        self._job = None
        self._last_time = None
        self._last_total = None
        self._last_nic = {}
        self._connections = None
        self._conn_busy = False
        self._conn_checked = 0.0

        self.header("Network", "Live traffic and your network connections")

        speeds = ctk.CTkFrame(self, fg_color="transparent")
        speeds.pack(fill="x", padx=25)
        speeds.grid_columnconfigure((0, 1), weight=1, uniform="speed")
        self.down_card = SpeedCard(speeds, "↓  DOWNLOAD", theme.METRIC["down"])
        self.down_card.grid(row=0, column=0, sticky="ew", padx=9, pady=9)
        self.up_card = SpeedCard(speeds, "↑  UPLOAD", theme.METRIC["up"])
        self.up_card.grid(row=0, column=1, sticky="ew", padx=9, pady=9)

        totals = ctk.CTkFrame(self, fg_color="transparent")
        totals.pack(fill="x", padx=25)
        totals.grid_columnconfigure((0, 1, 2), weight=1, uniform="totals")
        self.received = self._stat(totals, 0, "RECEIVED SINCE BOOT")
        self.sent = self._stat(totals, 1, "SENT SINCE BOOT")
        self.connections = self._stat(totals, 2, "OPEN CONNECTIONS")

        table = card(self)
        table.pack(fill="both", expand=True, padx=34, pady=(10, 24))
        label(table, "INTERFACES", 10, True, theme.MUTED).pack(
            anchor="w", padx=19, pady=(17, 8))
        inner = ctk.CTkFrame(table, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tree = ttk.Treeview(inner, columns=[c[0] for c in self.COLUMNS],
                                 show="headings", style="CC.Treeview",
                                 selectmode="browse")
        scroll = ttk.Scrollbar(inner, orient="vertical", command=self.tree.yview,
                               style="CC.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        for key, title, width, anchor in self.COLUMNS:
            self.tree.heading(key, text=title, anchor=anchor)
            self.tree.column(key, width=width, anchor=anchor, stretch=(key == "name"))

    @staticmethod
    def _stat(parent, column, title):
        box = card(parent, corner_radius=14)
        box.grid(row=0, column=column, sticky="ew", padx=9, pady=9)
        label(box, title, 9, True, theme.MUTED).pack(anchor="w", padx=16, pady=(13, 2))
        value = label(box, "—", 17, True)
        value.pack(anchor="w", padx=16, pady=(0, 13))
        return value

    # ---- lifecycle --------------------------------------------------------
    def on_show(self):
        self._active = True
        self._last_total = None       # restart the baseline after being away
        self._last_nic = {}
        self._tick()

    def on_hide(self):
        self._active = False
        if self._job:
            self.after_cancel(self._job)
            self._job = None

    def _tick(self):
        if not self._active:
            return
        now = time.monotonic()
        total = psutil.net_io_counters()
        per_nic = psutil.net_io_counters(pernic=True)

        down = up = 0.0
        rates = {}
        if self._last_total is not None:
            elapsed = max(now - self._last_time, 0.001)
            down = max(0, total.bytes_recv - self._last_total.bytes_recv) / elapsed
            up = max(0, total.bytes_sent - self._last_total.bytes_sent) / elapsed
            for name, counters in per_nic.items():
                before = self._last_nic.get(name)
                if before:
                    rates[name] = (
                        max(0, counters.bytes_recv - before.bytes_recv) / elapsed,
                        max(0, counters.bytes_sent - before.bytes_sent) / elapsed)
            self.down_card.update_speed(down)
            self.up_card.update_speed(up)
        self._last_total, self._last_time, self._last_nic = total, now, per_nic

        self.received.configure(text=format_bytes(total.bytes_recv))
        self.sent.configure(text=format_bytes(total.bytes_sent))
        self._update_table(per_nic, rates)
        self._update_connections(now)
        self._job = self.after(1000, self._tick)

    # ---- interface table --------------------------------------------------
    def _update_table(self, per_nic, rates):
        try:
            addresses = psutil.net_if_addrs()
            stats = psutil.net_if_stats()
        except OSError:
            return

        rows = []
        for name, info in stats.items():
            ipv4 = next((a.address for a in addresses.get(name, [])
                         if a.family == socket.AF_INET), "—")
            counters = per_nic.get(name)
            rate_down, rate_up = rates.get(name, (0.0, 0.0))
            speed = f"{info.speed:,} Mbps" if info.speed else "—"
            rows.append((not info.isup, name, (
                name, "Up" if info.isup else "Down", ipv4, speed,
                format_speed(rate_down), format_speed(rate_up),
                format_bytes(counters.bytes_recv) if counters else "—",
                format_bytes(counters.bytes_sent) if counters else "—")))
        rows.sort(key=lambda item: (item[0], item[1].lower()))

        existing = set(self.tree.get_children())
        wanted = {name for _down, name, _values in rows}
        for iid in existing - wanted:
            self.tree.delete(iid)
        for index, (_down, name, values) in enumerate(rows):
            if name in existing:
                self.tree.item(name, values=values)
            else:
                self.tree.insert("", "end", iid=name, values=values)
            self.tree.move(name, "", index)

    # ---- connection count (slow call, so it runs in the background) -------
    def _update_connections(self, now):
        if not self._conn_busy and now - self._conn_checked >= 5:
            self._conn_busy = True
            self._conn_checked = now
            threading.Thread(target=self._count_connections, daemon=True).start()
        self.connections.configure(
            text="—" if self._connections is None else f"{self._connections:,}")

    def _count_connections(self):
        try:
            self._connections = len(psutil.net_connections(kind="inet"))
        except (psutil.AccessDenied, OSError):
            self._connections = None
        finally:
            self._conn_busy = False
