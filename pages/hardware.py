import threading
from tkinter import ttk

import customtkinter as ctk

from core import anim, hardware, theme
from core.widgets import card, label
from .base import BasePage


def temp_color(value):
    if value is None:
        return theme.TEXT
    if value >= 85:
        return theme.DANGER
    if value >= 70:
        return theme.WARN
    return theme.TEXT


class StatCard(ctk.CTkFrame):
    """A card with a title, a big value, a detail line and an optional bar."""

    def __init__(self, master, title, color, with_bar=True):
        super().__init__(master, fg_color=theme.CARD, corner_radius=16,
                         border_width=1, border_color=theme.BORDER)
        self._shown = 0.0
        label(self, title, 10, True, color).pack(anchor="w", padx=18, pady=(16, 3))
        self.value = label(self, "—", 26, True)
        self.value.pack(anchor="w", padx=18)
        self.detail = label(self, "", 10, False, theme.MUTED, justify="left",
                            wraplength=300)
        self.detail.pack(anchor="w", padx=18, pady=(2, 8))
        self.bar = None
        if with_bar:
            self.bar = ctk.CTkProgressBar(self, height=7, corner_radius=8,
                                          fg_color=theme.TRACK, progress_color=color)
            self.bar.pack(fill="x", padx=18, pady=(0, 17))
            self.bar.set(0)
        else:
            ctk.CTkFrame(self, height=10, fg_color="transparent").pack()

    def show(self, text, detail="", fraction=None, text_color=theme.TEXT):
        self.value.configure(text=text, text_color=text_color)
        self.detail.configure(text=detail)
        if self.bar is not None and fraction is not None:
            def step(value):
                self._shown = value
                self.bar.set(max(0.0, min(1.0, value)))
            anim.animate(self.bar, "fill", self._shown, fraction, 400, step, kind="meters")


class HardwarePage(BasePage):
    HINT = ("Windows doesn't share CPU temperatures with normal programs. To see them "
            "here, run the free LibreHardwareMonitor, open Options → Remote Web Server → "
            "Run, and leave it running. NVIDIA graphics cards work without it.")
    COLUMNS = (
        ("hardware", "Hardware", 260, "w"),
        ("sensor", "Sensor", 220, "w"),
        ("value", "Now", 90, "e"),
        ("max", "Highest", 90, "e"),
    )

    def __init__(self, master, toast=None):
        super().__init__(master, toast)
        self._active = False
        self._job = None
        self._busy = False
        self._pending = None

        self.header("Hardware", "Graphics card, temperatures and battery")

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", padx=25)
        grid.grid_columnconfigure((0, 1, 2), weight=1, uniform="hw")
        self.gpu_card = StatCard(grid, "GRAPHICS CARD", theme.METRIC["ram"])
        self.cpu_card = StatCard(grid, "CPU TEMPERATURE", theme.METRIC["cpu"])
        self.battery_card = StatCard(grid, "BATTERY", theme.METRIC["disk"])
        for column, tile in enumerate((self.gpu_card, self.cpu_card, self.battery_card)):
            tile.grid(row=0, column=column, sticky="nsew", padx=9, pady=9)

        table = card(self)
        table.pack(fill="both", expand=True, padx=34, pady=(10, 10))
        head = ctk.CTkFrame(table, fg_color="transparent")
        head.pack(fill="x", padx=19, pady=(17, 8))
        label(head, "TEMPERATURE SENSORS", 10, True, theme.MUTED).pack(side="left")
        self.source_label = label(head, "", 10, False, theme.MUTED)
        self.source_label.pack(side="right")

        inner = ctk.CTkFrame(table, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.tree = ttk.Treeview(inner, columns=[c[0] for c in self.COLUMNS],
                                 show="headings", style="CC.Treeview", selectmode="none")
        scroll = ttk.Scrollbar(inner, orient="vertical", command=self.tree.yview,
                               style="CC.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        for key, title, width, anchor in self.COLUMNS:
            self.tree.heading(key, text=title, anchor=anchor)
            self.tree.column(key, width=width, anchor=anchor, stretch=(key == "hardware"))

        self.hint = label(self, self.HINT, 10, False, theme.MUTED, wraplength=900,
                          justify="left")
        self.hint.pack(anchor="w", padx=36, pady=(0, 18))

    # ---- lifecycle ---------------------------------------------------------------
    def on_show(self):
        self._active = True
        self._tick()

    def on_hide(self):
        self._active = False
        if self._job:
            self.after_cancel(self._job)
            self._job = None

    def _tick(self):
        if not self._active:
            return
        if self._pending is not None:
            data, self._pending = self._pending, None
            self._render(data)
        if not self._busy:
            self._busy = True
            threading.Thread(target=self._worker, daemon=True).start()
        self._job = self.after(500, self._tick)

    def _worker(self):
        try:
            self._pending = hardware.read_all()
        except Exception:
            self._pending = None
        finally:
            # Wait a moment before the next reading so we don't hammer nvidia-smi.
            threading.Timer(1.5, self._release).start()

    def _release(self):
        self._busy = False

    # ---- drawing -----------------------------------------------------------------
    def _render(self, data):
        gpus = data["gpus"]
        if gpus:
            gpu = gpus[0]
            util = gpu.get("util")
            bits = [gpu["name"]]
            if gpu.get("temp") is not None:
                bits.append(f"{gpu['temp']:.0f} °C")
            if gpu.get("mem_used") is not None and gpu.get("mem_total"):
                bits.append(f"VRAM {gpu['mem_used'] / 1024:.1f} / "
                            f"{gpu['mem_total'] / 1024:.1f} GB")
            if gpu.get("power") is not None:
                bits.append(f"{gpu['power']:.0f} W")
            self.gpu_card.show(f"{util:.0f}%" if util is not None else "—",
                               "  ·  ".join(bits),
                               util / 100 if util is not None else None,
                               temp_color(gpu.get("temp")))
        else:
            self.gpu_card.show("—", "No NVIDIA card found. Other cards appear here "
                                    "when LibreHardwareMonitor is running.", 0)

        cpu = data["cpu_temp"]
        if cpu:
            self.cpu_card.show(f"{cpu.value:.0f} °C", f"{cpu.hardware} · {cpu.name}",
                               min(cpu.value / 100, 1.0), temp_color(cpu.value))
        else:
            self.cpu_card.show("—", "Not available (see the note below)", 0)

        battery = data["battery"]
        if battery:
            left = battery["minutes_left"]
            state = "Charging / plugged in" if battery["plugged"] else (
                f"{left // 60} h {left % 60:02d} min left" if left else "On battery")
            self.battery_card.show(f"{battery['percent']:.0f}%", state,
                                   battery["percent"] / 100)
        else:
            self.battery_card.show("—", "No battery (desktop PC)", 0)

        temps = [s for s in data["sensors"] if s.group == "Temperatures"]
        self.source_label.configure(text=f"Source: {data['source']}" if temps else "")
        self.hint.configure(text="" if temps else self.HINT)
        existing = set(self.tree.get_children())
        wanted = set()
        for index, sensor in enumerate(temps):
            iid = f"{index}"
            wanted.add(iid)
            values = (sensor.hardware, sensor.name, f"{sensor.value:.0f} °C",
                      f"{sensor.maximum:.0f} °C" if sensor.maximum else "—")
            if iid in existing:
                self.tree.item(iid, values=values)
            else:
                self.tree.insert("", "end", iid=iid, values=values)
        for iid in existing - wanted:
            self.tree.delete(iid)
