"""A fast list of running processes.

psutil asks Windows about every process separately, and on Windows each of those
questions makes Windows list ALL processes again, so reading 300 processes took
seconds. Here we ask Windows once (NtQuerySystemInformation) and get every process
with its name, threads, memory and CPU time in a single call (about 10 ms).

On other systems, or if that call ever fails, we fall back to psutil.
"""
import ctypes
import time
from ctypes import wintypes          # only types: importable on any system

from .utils import IS_WINDOWS

_SYSTEM_PROCESS_INFORMATION = 5
_STATUS_INFO_LENGTH_MISMATCH = 0xC0000004


class SystemProcessInformation(ctypes.Structure):
    """The start of Windows' SYSTEM_PROCESS_INFORMATION record."""
    _fields_ = [
        ("NextEntryOffset", ctypes.c_uint32),
        ("NumberOfThreads", ctypes.c_uint32),
        ("WorkingSetPrivateSize", ctypes.c_int64),
        ("HardFaultCount", ctypes.c_uint32),
        ("NumberOfThreadsHighWatermark", ctypes.c_uint32),
        ("CycleTime", ctypes.c_uint64),
        ("CreateTime", ctypes.c_int64),
        ("UserTime", ctypes.c_int64),
        ("KernelTime", ctypes.c_int64),
        ("ImageNameLength", ctypes.c_uint16),
        ("ImageNameMaximumLength", ctypes.c_uint16),
        ("ImageNameBuffer", ctypes.c_void_p),
        ("BasePriority", ctypes.c_int32),
        ("UniqueProcessId", ctypes.c_void_p),
        ("InheritedFromUniqueProcessId", ctypes.c_void_p),
        ("HandleCount", ctypes.c_uint32),
        ("SessionId", ctypes.c_uint32),
        ("UniqueProcessKey", ctypes.c_void_p),
        ("PeakVirtualSize", ctypes.c_size_t),
        ("VirtualSize", ctypes.c_size_t),
        ("PageFaultCount", ctypes.c_uint32),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
    ]


def parse_buffer(buffer):
    """Turn the raw bytes Windows returned into a list of process dicts."""
    base = ctypes.addressof(buffer)
    rows, offset = [], 0
    while True:
        info = SystemProcessInformation.from_address(base + offset)
        pid = info.UniqueProcessId or 0
        if pid:                                    # pid 0 is the "System Idle Process"
            if info.ImageNameLength and info.ImageNameBuffer:
                name = ctypes.wstring_at(info.ImageNameBuffer, info.ImageNameLength // 2)
            else:
                name = "System" if pid == 4 else f"PID {pid}"
            rows.append({
                "pid": int(pid), "name": name, "threads": info.NumberOfThreads,
                "mem": int(info.WorkingSetSize),
                "cpu_time": (info.UserTime + info.KernelTime) / 1e7,       # seconds
                "created": info.CreateTime,
            })
        if not info.NextEntryOffset:
            break
        offset += info.NextEntryOffset
    return rows


def _snapshot_windows():
    ntdll = ctypes.windll.ntdll
    size = 1 << 20
    for _ in range(6):
        buffer = ctypes.create_string_buffer(size)
        needed = wintypes.ULONG(0)
        status = ntdll.NtQuerySystemInformation(
            _SYSTEM_PROCESS_INFORMATION, buffer, size, ctypes.byref(needed))
        if (status & 0xFFFFFFFF) == _STATUS_INFO_LENGTH_MISMATCH:
            size = max(size * 2, needed.value + (1 << 16))        # the list grew: try again
            continue
        if status != 0:
            raise OSError(f"NtQuerySystemInformation failed (0x{status & 0xFFFFFFFF:X})")
        return parse_buffer(buffer)
    raise OSError("The process list kept growing.")


def _snapshot_psutil():
    import psutil
    rows = []
    for proc in psutil.process_iter(["pid", "name", "memory_info", "num_threads", "cpu_times"]):
        info = proc.info
        if not info.get("pid"):
            continue
        times, memory = info.get("cpu_times"), info.get("memory_info")
        rows.append({
            "pid": info["pid"], "name": info.get("name") or f"PID {info['pid']}",
            "threads": info.get("num_threads") or 0, "mem": memory.rss if memory else 0,
            "cpu_time": (times.user + times.system) if times else 0.0, "created": 0,
        })
    return rows


def snapshot():
    """Every running process: pid, name, threads, mem (bytes), cpu_time (seconds)."""
    if IS_WINDOWS:
        try:
            return _snapshot_windows()
        except Exception:
            pass                                    # fall back to the slower, safe way
    return _snapshot_psutil()


class CpuTracker:
    """Turns two snapshots into CPU percentages (100% = every core fully busy)."""

    def __init__(self, cores):
        self.cores = max(1, cores)
        self._last = {}
        self._last_time = None

    def update(self, rows, now=None):
        now = time.monotonic() if now is None else now
        elapsed = None if self._last_time is None else max(now - self._last_time, 0.001)
        seen = {}
        for row in rows:
            key = (row["pid"], row["created"])      # same pid + start time = same process
            before = self._last.get(key)
            if before is None or elapsed is None:
                row["cpu"] = 0.0
            else:
                row["cpu"] = max(0.0, (row["cpu_time"] - before) / elapsed / self.cores * 100)
            seen[key] = row["cpu_time"]
        self._last, self._last_time = seen, now
        return rows


# Ending these makes Windows crash or log you out, so Command Center refuses.
PROTECTED = {"system", "registry", "smss.exe", "csrss.exe", "wininit.exe", "services.exe",
             "lsass.exe", "winlogon.exe", "fontdrvhost.exe", "memory compression",
             "secure system", "lsaiso.exe"}
# These are fine to end but disturb things (taskbar, windows, many background services).
RISKY = {"explorer.exe": "This is your taskbar and desktop. They disappear until it restarts.",
         "dwm.exe": "This draws every window. The screen will flicker or go black.",
         "svchost.exe": "Windows runs many background services inside this one.",
         "audiodg.exe": "Windows' audio engine. Sound stops until it restarts.",
         "sihost.exe": "Part of the Windows shell. The taskbar may break.",
         "taskhostw.exe": "Hosts Windows background tasks."}


def protection(name, pid=None):
    """'blocked', 'risky' or None for a process."""
    lowered = (name or "").lower()
    if pid in (0, 4) or lowered in PROTECTED:
        return "blocked"
    if lowered in RISKY:
        return "risky"
    return None


def risk_note(name):
    return RISKY.get((name or "").lower(), "")
