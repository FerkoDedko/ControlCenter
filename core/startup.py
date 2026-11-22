"""Windows startup programs: list them and switch them on or off.

Where Windows keeps them:
  * Registry "Run" keys (current user and all users)
  * The Startup folders (current user and all users)

Switching an item off the same way Task Manager does it: Windows records a
small flag under ...\\Explorer\\StartupApproved. Nothing is deleted, so the
item can always be switched back on.
"""
import os
import struct
import time
from dataclasses import dataclass

from .utils import IS_WINDOWS

if IS_WINDOWS:
    import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved"
FOLDER_TAIL = r"Microsoft\Windows\Start Menu\Programs\Startup"

RUN_KEY_32 = r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"

KIND_USER_RUN = "user_run"
KIND_MACHINE_RUN = "machine_run"
KIND_MACHINE_RUN32 = "machine_run32"
KIND_USER_FOLDER = "user_folder"
KIND_COMMON_FOLDER = "common_folder"

SOURCE_LABELS = {
    KIND_USER_RUN: "Registry · you",
    KIND_MACHINE_RUN: "Registry · all users",
    KIND_MACHINE_RUN32: "Registry · all users (32-bit)",
    KIND_USER_FOLDER: "Startup folder · you",
    KIND_COMMON_FOLDER: "Startup folder · all users",
}


@dataclass
class StartupEntry:
    name: str
    command: str
    kind: str
    enabled: bool

    @property
    def source(self):
        return SOURCE_LABELS[self.kind]

    @property
    def approved_subkey(self):
        """Which StartupApproved key Windows/Task Manager keeps this item's on/off flag in."""
        if self.kind == KIND_MACHINE_RUN32:
            return "Run32"
        if self.kind in (KIND_USER_RUN, KIND_MACHINE_RUN):
            return "Run"
        return "StartupFolder"

    @property
    def is_machine_wide(self):
        return self.kind in (KIND_MACHINE_RUN, KIND_MACHINE_RUN32, KIND_COMMON_FOLDER)


def supported():
    return IS_WINDOWS


def executable_of(command):
    """Best guess at the program path inside a startup command line."""
    command = (command or "").strip()
    if command.startswith('"'):
        end = command.find('"', 1)
        return command[1:end] if end > 0 else command[1:]
    lowered = command.lower()
    for ext in (".exe", ".bat", ".cmd", ".lnk", ".com"):
        position = lowered.find(ext)
        if position >= 0:
            return command[:position + len(ext)]
    return command.split(" ")[0] if command else ""


def flag_is_enabled(data):
    """StartupApproved values: an even first byte means enabled, odd disabled."""
    if not data:
        return True
    return (data[0] & 1) == 0


def make_flag(enabled):
    if enabled:
        return b"\x02\x00\x00\x00" + b"\x00" * 8
    filetime = int((time.time() + 11644473600) * 10_000_000)
    return b"\x03\x00\x00\x00" + struct.pack("<Q", filetime)


def _read_flags(hive, subkey):
    flags = {}
    try:
        with winreg.OpenKey(hive, f"{APPROVED_KEY}\\{subkey}", 0,
                            winreg.KEY_READ) as key:
            index = 0
            while True:
                try:
                    name, data, _kind = winreg.EnumValue(key, index)
                except OSError:
                    break
                flags[name.lower()] = bytes(data) if data else b""
                index += 1
    except OSError:
        pass
    return flags


def _approved(subkey, name):
    """The per-user flag wins over the machine-wide one."""
    key = name.lower()
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        flags = _read_flags(hive, subkey)
        if key in flags:
            return flag_is_enabled(flags[key])
    return True


def _run_entries(hive, kind, run_key=RUN_KEY, approved="Run"):
    entries = []
    try:
        with winreg.OpenKey(hive, run_key, 0, winreg.KEY_READ) as key:
            index = 0
            while True:
                try:
                    name, value, _kind = winreg.EnumValue(key, index)
                except OSError:
                    break
                index += 1
                if isinstance(value, str):
                    entries.append(StartupEntry(
                        name, value, kind, _approved(approved, name)))
    except OSError:
        pass
    return entries


def _folder_entries(path, kind):
    entries = []
    try:
        for item in sorted(os.listdir(path)):
            if item.lower() == "desktop.ini":
                continue
            entries.append(StartupEntry(
                item, os.path.join(path, item), kind,
                _approved("StartupFolder", item)))
    except OSError:
        pass
    return entries


def list_entries():
    if not IS_WINDOWS:
        return []
    entries = []
    entries += _run_entries(winreg.HKEY_CURRENT_USER, KIND_USER_RUN)
    entries += _run_entries(winreg.HKEY_LOCAL_MACHINE, KIND_MACHINE_RUN)
    entries += _run_entries(winreg.HKEY_LOCAL_MACHINE, KIND_MACHINE_RUN32,
                            RUN_KEY_32, "Run32")
    appdata = os.environ.get("APPDATA")
    programdata = os.environ.get("PROGRAMDATA")
    if appdata:
        entries += _folder_entries(os.path.join(appdata, FOLDER_TAIL),
                                   KIND_USER_FOLDER)
    if programdata:
        entries += _folder_entries(os.path.join(programdata, FOLDER_TAIL),
                                   KIND_COMMON_FOLDER)
    return entries


def set_enabled(entry, enabled):
    """Turn an entry on or off. Raises OSError if Windows refuses."""
    if not IS_WINDOWS:
        raise OSError("Startup management is only available on Windows.")
    path = f"{APPROVED_KEY}\\{entry.approved_subkey}"
    flag = make_flag(enabled)

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, path, 0,
                            winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, entry.name, 0, winreg.REG_BINARY, flag)

    # For all-users items also try the machine-wide flag. That needs administrator
    # rights, so it's best effort: the per-user flag above is the one that counts
    # for the current user.
    if entry.is_machine_wide:
        try:
            with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, path, 0,
                                    winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, entry.name, 0, winreg.REG_BINARY, flag)
        except OSError:
            pass

    # Read it back so we never claim a change that Windows didn't keep.
    if _approved(entry.approved_subkey, entry.name) != enabled:
        raise OSError("Windows didn't keep the change.")
    entry.enabled = enabled
