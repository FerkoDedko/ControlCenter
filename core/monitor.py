import platform
import time

import psutil

from . import utils


class SystemMonitor:
    def __init__(self):
        self.last_network = psutil.net_io_counters()
        self.last_network_time = time.time()
        psutil.cpu_percent(interval=None)

    @staticmethod
    def format_bytes(value):
        return utils.format_bytes(value)

    @staticmethod
    def format_speed(value):
        return utils.format_speed(value)

    def snapshot(self):
        cpu = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()

        partitions = psutil.disk_partitions(all=False)
        target = next((p for p in partitions if p.mountpoint.upper() == "C:\\"), None)
        if target is None:
            target = next((p for p in partitions if p.fstype), None)

        disk = None
        if target:
            try:
                disk = psutil.disk_usage(target.mountpoint)
            except (PermissionError, OSError):
                disk = None

        now = time.time()
        net = psutil.net_io_counters()
        elapsed = max(now - self.last_network_time, 0.001)
        download = max(0, net.bytes_recv - self.last_network.bytes_recv) / elapsed
        upload = max(0, net.bytes_sent - self.last_network.bytes_sent) / elapsed
        self.last_network = net
        self.last_network_time = now

        uptime_seconds = max(0, int(time.time() - psutil.boot_time()))
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)
        uptime = f"{days}d {hours:02}:{minutes:02}:{seconds:02}"

        frequency = psutil.cpu_freq()

        return {
            "cpu": cpu,
            "cpu_count": psutil.cpu_count(logical=True) or 0,
            "cpu_frequency": frequency.current if frequency else None,
            "memory_percent": memory.percent,
            "memory_total": memory.total,
            "memory_available": memory.available,
            "disk": disk,
            "disk_mount": target.mountpoint if target else "Unavailable",
            "download": download,
            "upload": upload,
            "uptime": uptime,
            "processor": platform.processor() or platform.machine(),
            "windows": f"{platform.system()} {platform.release()}",
            "platform": platform.platform()
        }
