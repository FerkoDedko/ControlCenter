"""Find and remove files that are safe to throw away.

Safety rules built in:
  * Only the folders listed in a target are ever touched, nothing else.
  * Shortcuts/links to other folders are skipped, never followed.
  * Files that are in use are simply skipped (and counted as "failed").
  * Temp folders keep anything changed in the last 24 hours, so a running
    installer doesn't get its files pulled out from under it.
  * Too-short paths like C:\\ or C:\\Users are refused.
"""
import ctypes
import glob
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from .utils import IS_WINDOWS


@dataclass
class CleanTarget:
    key: str
    name: str
    description: str
    paths: list = field(default_factory=list)   # folders (wildcards allowed)
    min_age_hours: float = 0.0                  # keep files newer than this
    special: str = ""                           # "recycle" = the Recycle Bin


@dataclass
class CleanResult:
    freed: int = 0
    deleted: int = 0
    failed: int = 0


def expand_paths(patterns):
    found = []
    for pattern in patterns:
        matches = glob.glob(pattern) if any(c in pattern for c in "*?[") else [pattern]
        found += [m for m in matches if os.path.isdir(m)]
    return found


def safe_root(path):
    p = Path(path)
    return p.is_absolute() and len(p.parts) >= 3 and not _is_link(str(p))


def _is_link(path):
    return os.path.islink(path) or getattr(os.path, "isjunction", lambda _p: False)(path)


def iter_files(target, now=None):
    """Yield (path, size) for every file this target would remove."""
    now = time.time() if now is None else now
    keep_after = target.min_age_hours * 3600
    for root in expand_paths(target.paths):
        if not safe_root(root):
            continue
        for folder, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [d for d in dirs if not _is_link(os.path.join(folder, d))]
            for name in files:
                path = os.path.join(folder, name)
                try:
                    if _is_link(path):
                        continue
                    info = os.stat(path)
                except OSError:
                    continue
                if keep_after and now - info.st_mtime < keep_after:
                    continue
                yield path, info.st_size


def scan_target(target, now=None):
    """(bytes, files) that cleaning would free."""
    if target.special == "recycle":
        return recycle_bin_info() or (0, 0)
    total = count = 0
    for _path, size in iter_files(target, now):
        total += size
        count += 1
    return total, count


def clean_target(target, cancel=None, now=None):
    result = CleanResult()
    if target.special == "recycle":
        before = (recycle_bin_info() or (0, 0))
        if empty_recycle_bin():
            result.freed, result.deleted = before
        else:
            result.failed = before[1]
        return result
    for path, size in iter_files(target, now):
        if cancel and cancel():
            break
        try:
            os.remove(path)
            result.freed += size
            result.deleted += 1
        except OSError:
            result.failed += 1
    _remove_empty_folders(target)
    return result


def _remove_empty_folders(target):
    for root in expand_paths(target.paths):
        if not safe_root(root):
            continue
        for folder, dirs, _files in os.walk(root, topdown=False, followlinks=False):
            for name in dirs:
                path = os.path.join(folder, name)
                if _is_link(path):
                    continue
                try:
                    os.rmdir(path)       # only succeeds if the folder is empty
                except OSError:
                    pass


# ---- the Recycle Bin (Windows) -------------------------------------------------
class _RecycleBinInfo(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("cbSize", ctypes.c_uint32), ("size", ctypes.c_int64),
                ("items", ctypes.c_int64)]


def recycle_bin_info():
    """(bytes, items) in the Recycle Bin, or None if it can't be read."""
    if not IS_WINDOWS:
        return None
    try:
        info = _RecycleBinInfo()
        info.cbSize = ctypes.sizeof(_RecycleBinInfo)
        if ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info)) != 0:
            return None
        return int(info.size), int(info.items)
    except Exception:
        return None


def empty_recycle_bin():
    if not IS_WINDOWS:
        return False
    try:
        # NOCONFIRMATION | NOPROGRESSUI | NOSOUND
        return ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, 0x7) == 0
    except Exception:
        return False


# ---- what to offer -----------------------------------------------------------
def default_targets(env=None):
    env = os.environ if env is None else env
    local = env.get("LOCALAPPDATA", "")
    system_root = env.get("SystemRoot", r"C:\Windows")
    temp = env.get("TEMP") or tempfile.gettempdir()

    targets = [CleanTarget(
        "temp", "Temporary files",
        "Leftovers from programs. Files changed in the last 24 hours are kept.",
        [temp], 24)]
    if not IS_WINDOWS:
        return targets

    targets.append(CleanTarget(
        "wintemp", "Windows temporary files",
        "System temp folder. Some files need administrator rights and will be skipped.",
        [os.path.join(system_root, "Temp")], 24))
    if local:
        chromium = [(r"Google\Chrome"), (r"Microsoft\Edge"),
                    (r"BraveSoftware\Brave-Browser")]
        browser_paths = []
        for vendor in chromium:
            base = os.path.join(local, vendor, "User Data", "*")
            browser_paths += [os.path.join(base, "Cache"),
                              os.path.join(base, "Code Cache"),
                              os.path.join(base, "GPUCache")]
        browser_paths.append(os.path.join(local, "Mozilla", "Firefox", "Profiles",
                                          "*", "cache2"))
        targets.append(CleanTarget(
            "browsers", "Browser caches",
            "Chrome, Edge, Brave and Firefox caches. Close your browsers first. "
            "You stay signed in; pages may load a little slower once.",
            browser_paths))
        targets.append(CleanTarget(
            "dumps", "Crash reports",
            "Memory dumps left behind by programs that crashed.",
            [os.path.join(local, "CrashDumps")]))
    targets.append(CleanTarget(
        "recycle", "Recycle Bin",
        "Files you already deleted. This empties it for good.",
        special="recycle"))
    return targets
