import platform
import threading
import time
from collections import deque


class AlertManager:
    """Threshold alerts that stay quiet unless something is really wrong.

    - A metric has to stay over its limit for `alert_delay_seconds` before an
      alert fires, so a one-second spike (opening a program, say) is ignored.
    - After an alert fires it won't repeat until the metric has clearly dropped
      back down (a few points under the limit), so a value hovering around the
      threshold can't spam notifications.
    """

    HYSTERESIS = 3  # percentage points below the limit needed to re-arm

    def __init__(self, root, config, toast_callback):
        self.root = root
        self.config = config
        self.toast_callback = toast_callback
        self.active = set()
        self.history = deque(maxlen=20)   # (time text, title, message)
        self._since = {}

    def update_config(self, config):
        self.config = config
        if not config.get("alerts_enabled", True):
            self.active.clear()
            self._since.clear()

    def _number(self, key, default):
        try:
            return float(self.config.get(key, default))
        except (TypeError, ValueError):
            return float(default)

    def check(self, stats, now=None):
        if not self.config.get("alerts_enabled", True):
            return
        now = time.monotonic() if now is None else now
        delay = max(0.0, self._number("alert_delay_seconds", 5))

        cpu_limit = self._number("cpu_threshold", 85)
        ram_limit = self._number("ram_threshold", 90)
        disk_limit = self._number("disk_free_threshold", 10)
        disk = stats.get("disk")

        # key -> (is over the limit, has recovered enough to re-arm)
        states = {
            "CPU": (stats["cpu"] >= cpu_limit,
                    stats["cpu"] < cpu_limit - self.HYSTERESIS),
            "RAM": (stats["memory_percent"] >= ram_limit,
                    stats["memory_percent"] < ram_limit - self.HYSTERESIS),
        }
        if disk:
            free = 100 - disk.percent
            states["DISK"] = (free <= disk_limit, free > disk_limit + 2)
        else:
            self.active.discard("DISK")
            self._since.pop("DISK", None)

        for key, (over, recovered) in states.items():
            if key in self.active:
                if recovered:
                    self.active.discard(key)
                continue
            if not over:
                self._since.pop(key, None)
                continue
            started = self._since.setdefault(key, now)
            if now - started >= delay:
                self._since.pop(key, None)
                self.active.add(key)
                self.send_alert(key, stats)

    def send_alert(self, key, stats):
        if key == "CPU":
            title, message = "High CPU usage", f"Processor usage is {stats['cpu']:.0f}%."
        elif key == "RAM":
            title, message = "High memory usage", f"RAM usage is {stats['memory_percent']:.0f}%."
        else:
            free = 100 - stats["disk"].percent
            title, message = "Low disk space", f"Only {free:.1f}% disk space is free."
        self.history.appendleft((time.strftime("%H:%M"), title, message))
        self._deliver(title, message)

    def send_test(self):
        self._deliver("Test alert", "This is how Command Center warnings look.")

    def _deliver(self, title, message):
        delivery = self.config.get("alert_delivery", "both")
        if delivery in ("both", "app"):
            self.toast_callback(title, message, "warning")
        if delivery in ("both", "windows"):
            self._windows_notification(title, message)
        if self.config.get("alert_sound", True):
            self._play_sound()

    def _windows_notification(self, title, message):
        def notify():
            try:
                from plyer import notification
                notification.notify(
                    title=title,
                    message=message,
                    app_name="Command Center",
                    timeout=6
                )
            except Exception:
                # In-app alert still works if Windows notification support is unavailable.
                pass

        threading.Thread(target=notify, daemon=True).start()

    @staticmethod
    def _play_sound():
        if platform.system() == "Windows":
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                pass
