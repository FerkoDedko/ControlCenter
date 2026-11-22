"""Start Command Center automatically when you sign in to Windows."""
import sys
from pathlib import Path

from .utils import IS_WINDOWS

if IS_WINDOWS:
    import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "CommandCenter"


def supported():
    return IS_WINDOWS


def launch_command(minimized=False):
    """The command Windows will run at sign-in (uses pythonw so no console shows)."""
    if getattr(sys, "frozen", False):                  # packaged .exe: it is the program
        command = f'"{sys.executable}"'
        return command + " --minimized" if minimized else command
    exe = Path(sys.executable)
    windowless = exe.with_name("pythonw.exe")
    if windowless.exists():
        exe = windowless
    script = Path(__file__).resolve().parent.parent / "main.py"
    command = f'"{exe}" "{script}"'
    return command + " --minimized" if minimized else command


def is_enabled():
    if not IS_WINDOWS:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
            return True
    except OSError:
        return False


def set_enabled(enabled, minimized=False):
    """Turn start-with-Windows on or off. Raises OSError if Windows refuses."""
    if not IS_WINDOWS:
        raise OSError("Start with Windows is only available on Windows.")
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ,
                              launch_command(minimized))
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
