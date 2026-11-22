import os
import shlex
import subprocess
import sys

IS_WINDOWS = sys.platform.startswith("win")


def format_bytes(value):
    value = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def format_speed(value):
    if value >= 1024 * 1024:
        return f"{value / (1024 * 1024):.2f} MB/s"
    return f"{value / 1024:.1f} KB/s"


def shorten(text, limit):
    text = str(text)
    return text if len(text) <= limit else text[:limit - 1] + "…"


def open_path(path):
    """Open a folder or file with the system's default app."""
    path = str(path)
    if IS_WINDOWS:
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def reveal_in_folder(path):
    """Show a file inside its folder (selected, on Windows)."""
    path = str(path)
    if IS_WINDOWS and os.path.exists(path):
        subprocess.Popen(["explorer", f"/select,{os.path.normpath(path)}"])
    else:
        open_path(os.path.dirname(path) or ".")


def launch(target, args=""):
    """Start a program or open a file. Raises OSError if that fails."""
    target = str(target)
    args = (args or "").strip()
    if IS_WINDOWS:
        if args:
            os.startfile(target, arguments=args)
        else:
            os.startfile(target)
        return
    if sys.platform == "darwin":
        command = ["open", "-a", target, "--args", *shlex.split(args)] \
            if target.endswith(".app") else ["open", target]
    elif os.path.isfile(target) and os.access(target, os.X_OK):
        command = [target, *shlex.split(args)]
    else:
        command = ["xdg-open", target]
    subprocess.Popen(command, start_new_session=True)
