import customtkinter as ctk

from core import anim, theme
from core.utils import format_bytes, format_speed
from core.widgets import Sparkline, card, label
from .base import BasePage


class MetricCard(ctk.CTkFrame):
    def __init__(self, master, title, subtitle, color,
                 spark_max=None, spark_floor=1.0):
        super().__init__(master, fg_color=theme.CARD, corner_radius=16,
                         border_width=1, border_color=theme.BORDER)
        self.color = color
        self._display = 0.0
        self._warn = False

        label(self, title.upper(), 10, True, color).pack(
            anchor="w", padx=18, pady=(16, 3))
        self.value_label = label(self, "—", 24, True)
        self.value_label.pack(anchor="w", padx=18)
        label(self, subtitle, 10, False, theme.MUTED).pack(
            anchor="w", padx=18, pady=(0, 6))
        self.spark = Sparkline(self, color, height=34,
                               fixed_max=spark_max, floor=spark_floor)
        self.spark.pack(fill="x", padx=18, pady=(0, 8))
        self.bar = ctk.CTkProgressBar(self, height=7, corner_radius=8,
                                      fg_color=theme.TRACK, progress_color=color)
        self.bar.pack(fill="x", padx=18, pady=(0, 17))
        self.bar.set(0)

    def set_value(self, value, text_fn, scale=100.0, duration=450):
        """Glide the number and the bar to a new value together."""
        value = float(value)
        self.spark.push(value)

        def step(current):
            self._display = current
            self.value_label.configure(text=text_fn(current))
            self.bar.set(max(0.0, min(1.0, current / scale)))

        anim.animate(self, "value", self._display, value, duration, step, kind="meters")

    def set_warn(self, warn):
        if warn == self._warn:
            return
        self._warn = warn
        self.bar.configure(progress_color=theme.WARN if warn else self.color)
        self.value_label.configure(text_color=theme.WARN if warn else theme.TEXT)


class DashboardPage(BasePage):
    def __init__(self, master, config, alert_manager, toast=None):
        super().__init__(master, toast)
        self.config = config
        self.alert_manager = alert_manager
        self._visible = False
        self._last_stats = None
        self._peak_down = 1024 * 1024
        self._pulse_level = 1.0
        self._pulse_running = False
        self._build()

    # ---- layout -----------------------------------------------------------
    def _build(self):
        right = self.header("System overview", "Live performance and hardware status")
        self.live_label = label(right, "●  LIVE", 10, True, theme.OK,
                                fg_color=theme.OK_BG, corner_radius=20,
                                width=82, height=28)
        self.live_label.pack(pady=8)

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", padx=25)
        grid.grid_columnconfigure((0, 1, 2, 3), weight=1, uniform="cards")
        self.cards = {}
        definitions = [
            ("CPU", "Processor load", theme.METRIC["cpu"], 100.0, 1.0),
            ("RAM", "Memory in use", theme.METRIC["ram"], 100.0, 1.0),
            ("DISK", "System drive usage", theme.METRIC["disk"], 100.0, 1.0),
            ("DOWNLOAD", "Current download", theme.METRIC["down"], None, 100 * 1024.0),
        ]
        for index, (key, subtitle, color, spark_max, floor) in enumerate(definitions):
            metric = MetricCard(grid, key, subtitle, color, spark_max, floor)
            metric.grid(row=0, column=index, sticky="ew", padx=9, pady=9)
            self.cards[key] = metric

        lower = ctk.CTkFrame(self, fg_color="transparent")
        lower.pack(fill="both", expand=True, padx=34, pady=(10, 22))
        lower.grid_columnconfigure(0, weight=3)
        lower.grid_columnconfigure(1, weight=2)
        lower.grid_rowconfigure(0, weight=1)

        info = card(lower)
        info.grid(row=0, column=0, sticky="nsew", padx=(0, 9))
        label(info, "DEVICE INFORMATION", 10, True, theme.MUTED).pack(
            anchor="w", padx=19, pady=(17, 12))
        self.info_labels = {}
        for key in ("Processor", "Windows", "Logical processors",
                    "CPU frequency", "Total memory", "Available memory",
                    "System drive", "System uptime"):
            row = ctk.CTkFrame(info, fg_color="transparent")
            row.pack(fill="x", padx=19, pady=5)
            label(row, key, 10, False, theme.MUTED).pack(side="left")
            value = label(row, "Reading…", 10, True)
            value.pack(side="right")
            self.info_labels[key] = value

        network = card(lower)
        network.grid(row=0, column=1, sticky="nsew", padx=(9, 0))
        label(network, "NETWORK ACTIVITY", 10, True, theme.MUTED).pack(
            anchor="w", padx=18, pady=(17, 6))
        self.download_label, self.download_spark = self._network_row(
            network, "↓  Download", theme.METRIC["down"])
        self.upload_label, self.upload_spark = self._network_row(
            network, "↑  Upload", theme.METRIC["up"])
        ctk.CTkFrame(network, height=1, fg_color=theme.DIVIDER).pack(
            fill="x", padx=18, pady=(10, 10))
        label(network, "RECENT ALERTS", 10, True, theme.MUTED).pack(
            anchor="w", padx=18, pady=(0, 4))
        self.alerts_label = label(network, "No alerts so far.", 10, False,
                                  theme.TEXT_SOFT, justify="left", wraplength=300)
        self.alerts_label.pack(anchor="w", padx=18)
        self.status_label = label(network, "Monitoring is active", 9, False,
                                  theme.MUTED)
        self.status_label.pack(anchor="w", padx=18, pady=(10, 0))

    @staticmethod
    def _network_row(parent, title, color):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(4, 2))
        label(row, title, 11, True, color).pack(anchor="w")
        value = label(row, "0 KB/s", 18, True)
        value.pack(anchor="w", pady=(2, 0))
        spark = Sparkline(row, color, height=30, floor=100 * 1024.0)
        spark.pack(fill="x", pady=(4, 0))
        return value, spark

    # ---- lifecycle --------------------------------------------------------
    def on_show(self):
        self._visible = True
        if self._last_stats:
            self.update_stats(self._last_stats)
        if not self._pulse_running:
            self._pulse_running = True
            self._pulse()

    def on_hide(self):
        self._visible = False

    def update_config(self, config):
        self.config = config

    def show_error(self, exc):
        self.status_label.configure(text=f"Monitoring issue: {exc}")

    # ---- the pulsing LIVE dot ----------------------------------------------
    def _pulse(self, target=0.35):
        if not self._visible:
            self._pulse_running = False
            return
        if not anim.is_enabled("effects"):
            self.live_label.configure(text_color=theme.OK)
            self.after(2000, self._pulse)
            return

        def step(level):
            self._pulse_level = level
            self.live_label.configure(text_color=theme.lerp(
                theme.resolve(theme.OK_BG), theme.resolve(theme.OK), level))

        anim.animate(self.live_label, "pulse", self._pulse_level, target, 900,
                     step, done=lambda: self._pulse(1.0 if target < 0.5 else 0.35),
                     easing=anim.ease_in_out, kind="effects")

    # ---- live data --------------------------------------------------------
    def update_stats(self, stats):
        self._last_stats = stats
        if not self._visible:
            return

        interval = max(500, int(self.config.get("refresh_interval_ms", 1000)))
        duration = min(450, int(interval * 0.8))
        percent = lambda v: f"{v:.1f}%"

        cpu_card = self.cards["CPU"]
        cpu_card.set_value(stats["cpu"], percent, 100.0, duration)
        cpu_card.set_warn(stats["cpu"] >= float(self.config.get("cpu_threshold", 85)))

        ram_card = self.cards["RAM"]
        ram_card.set_value(stats["memory_percent"], percent, 100.0, duration)
        ram_card.set_warn(stats["memory_percent"] >= float(self.config.get("ram_threshold", 90)))

        disk = stats["disk"]
        disk_card = self.cards["DISK"]
        if disk:
            disk_card.set_value(disk.percent, percent, 100.0, duration)
            disk_card.set_warn(100 - disk.percent <= float(
                self.config.get("disk_free_threshold", 10)))
            self.info_labels["System drive"].configure(
                text=f"{stats['disk_mount']} • {format_bytes(disk.free)} free")
        else:
            disk_card.value_label.configure(text="Unavailable")

        # The bar is relative to the fastest download seen this session.
        self._peak_down = max(self._peak_down, stats["download"])
        self.cards["DOWNLOAD"].set_value(stats["download"], format_speed,
                                         self._peak_down, duration)

        frequency = stats["cpu_frequency"]
        values = {
            "Processor": stats["processor"][:42],
            "Windows": stats["windows"],
            "Logical processors": str(stats["cpu_count"]),
            "CPU frequency": f"{frequency:.0f} MHz" if frequency else "Unavailable",
            "Total memory": format_bytes(stats["memory_total"]),
            "Available memory": format_bytes(stats["memory_available"]),
            "System uptime": stats["uptime"],
        }
        for key, value in values.items():
            self.info_labels[key].configure(text=value)

        self.download_label.configure(text=format_speed(stats["download"]))
        self.upload_label.configure(text=format_speed(stats["upload"]))
        self.download_spark.push(stats["download"])
        self.upload_spark.push(stats["upload"])
        self.status_label.configure(text=f"Refresh: {interval} ms")

        history = list(self.alert_manager.history)[:3]
        self.alerts_label.configure(
            text="\n".join(f"{when}  {title} — {message}"
                           for when, title, message in history)
            if history else "No alerts so far.")
