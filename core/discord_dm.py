"""Discord direct messages, handled 100% on this PC.

No bot, no Discord API and no account token is involved. Instead:

  * READ   Windows shows a pop-up (toast) when a DM arrives. The Windows
           notification listener lets us see those pop-ups. Only DMs count: the
           pop-up title for server and group messages contains "(...)", DMs don't.
  * REPLY  We bring the Discord window to the front, press Ctrl+K (Discord's quick
           switcher), type the person's name, press Enter, type the message, press
           Enter, and then go back to the window you were using.
  * BUSY   If you are in VS Code or on a call, the same reply routine sends
           your "I'm busy" message, at most once every 5 minutes per person.

Because replying works by pressing keys, don't type while it runs (about 3 seconds).
Every step checks that Discord still has the focus, so text never lands in another app.
"""
import asyncio
import collections
import importlib
import importlib.util
import os
import subprocess
import threading
import time

from .utils import IS_WINDOWS

COOLDOWN_SECONDS = 5 * 60          # busy reply: once per person per 5 minutes
RECENT_SECONDS = 2 * 60 * 60       # a DM older than this isn't "recent" any more
POLL_SECONDS = 1.5
DEFAULT_BUSY_MESSAGE = "Hey, this person is busy right now!"
MAX_MESSAGE = 1900                 # Discord's limit is 2000 characters

# pauses (seconds) while Discord reacts to the keys
PAUSE_AFTER_FOCUS = 0.45
PAUSE_AFTER_SWITCHER = 0.45
PAUSE_FOR_SEARCH = 0.9
PAUSE_AFTER_JUMP = 0.8

# windows that are "fullscreen" only because they ARE the desktop or the Start menu
SHELL_PROGRAMS = {"explorer.exe", "searchhost.exe", "shellexperiencehost.exe",
                  "startmenuexperiencehost.exe", "applicationframehost.exe", "lockapp.exe",
                  "textinputhost.exe"}
INSTALL_HINT = ("py -m pip install winrt-runtime winrt-Windows.ApplicationModel "
                "winrt-Windows.Foundation "
                "winrt-Windows.Foundation.Collections winrt-Windows.UI.Notifications "
                "winrt-Windows.UI.Notifications.Management pycaw")


WINRT_MODULES = ("winrt.windows.applicationmodel", "winrt.windows.foundation",
                 "winrt.windows.foundation.collections", "winrt.windows.ui.notifications",
                 "winrt.windows.ui.notifications.management")


def package_problem():
    """None when the notification packages load. Otherwise a sentence saying what's wrong:
    a package that isn't installed, or one Windows refused to load (Smart App Control,
    antivirus). Those need different fixes."""
    import importlib
    if importlib.util.find_spec("winrt") is None and importlib.util.find_spec("winsdk") is not None:
        return None                                      # the older winsdk package
    try:
        for name in WINRT_MODULES:
            importlib.import_module(name)
    except ModuleNotFoundError as exc:
        return f"Not installed: {exc.name}. Install with:  {INSTALL_HINT}"
    except ImportError as exc:
        return ("Installed, but Windows blocked a Python file "
                f"({exc}). Check Windows Security / Smart App Control, or use Python 3.12-3.13.")
    return None


def missing_packages():
    """Names of optional packages that aren't installed (empty list = all good)."""
    import importlib.util
    has_winrt = importlib.util.find_spec("winrt") is not None
    has_winsdk = importlib.util.find_spec("winsdk") is not None
    return [] if (has_winrt or has_winsdk) else [
        "winrt-Windows.UI.Notifications.Management (and the other winrt-… packages)"]


def is_dm_title(title):
    """Direct messages have just the person's name as the title. Server channels look like
    'name (#channel, Server)' and group chats like 'name (Group)', so any bracket = not a DM."""
    title = (title or "").strip()
    return bool(title) and "(" not in title and ")" not in title


# ---- Windows plumbing (ctypes only, so there's nothing extra to install) -------------
if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _user32.IsWindow.argtypes = [wintypes.HWND]
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    _user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
    _WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t)]

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT)]

    class _INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    class _MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

    _user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetWindowLongW.restype = ctypes.c_long
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    _user32.MonitorFromWindow.restype = ctypes.c_void_p
    _user32.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MONITORINFO)]

VK_CONTROL, VK_RETURN, VK_ESCAPE, VK_MENU, VK_K = 0x11, 0x0D, 0x1B, 0x12, 0x4B
_KEYUP, _UNICODE = 0x0002, 0x0004
_SW_SHOW, _SW_RESTORE = 5, 9


def _require_windows():
    if not IS_WINDOWS:
        raise OSError("Discord replies only work on Windows.")


def _foreground():
    return _user32.GetForegroundWindow()


def _process_name(hwnd):
    import psutil
    pid = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        return psutil.Process(pid.value).name().lower()
    except Exception:
        return ""


def _window_title(hwnd):
    length = _user32.GetWindowTextLengthW(hwnd)
    if not length:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    _user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def find_discord_window():
    """The main Discord window (visible ones first), or None."""
    _require_windows()
    found = []

    def visit(hwnd, _lparam):
        if _window_title(hwnd).endswith("Discord") and \
                _process_name(hwnd).startswith("discord"):
            found.append((not _user32.IsWindowVisible(hwnd), hwnd))
        return True

    _user32.EnumWindows(_WNDENUMPROC(visit), 0)
    found.sort()
    return found[0][1] if found else None


def _key(vk, up=False):
    _user32.keybd_event(vk, 0, _KEYUP if up else 0, 0)


def _chord(*vks):
    for vk in vks:
        _key(vk)
    for vk in reversed(vks):
        _key(vk, up=True)
    time.sleep(0.03)


def _type_text(text):
    """Type any text (accents, emoji…) as real characters, without using the clipboard."""
    text = " ".join(text.replace("\r", "\n").split("\n"))[:MAX_MESSAGE]
    units = text.encode("utf-16-le")
    codes = [units[i] | (units[i + 1] << 8) for i in range(0, len(units), 2)]
    for start in range(0, len(codes), 40):            # small batches, so nothing is dropped
        batch = codes[start:start + 40]
        events = (_INPUT * (len(batch) * 2))()
        for n, code in enumerate(batch):
            for part, flags in enumerate((_UNICODE, _UNICODE | _KEYUP)):
                item = events[n * 2 + part]
                item.type = 1                          # INPUT_KEYBOARD
                item.u.ki = _KEYBDINPUT(0, code, flags, 0, 0)
        _user32.SendInput(len(events), ctypes.byref(events), ctypes.sizeof(_INPUT))
        time.sleep(0.02)


def _bring_to_front(hwnd):
    """Focus a window. Windows only allows this in some situations, so try two tricks."""
    _user32.ShowWindow(hwnd, _SW_RESTORE if _user32.IsIconic(hwnd) else _SW_SHOW)
    for attempt in range(2):
        if attempt == 0:
            here = _kernel32.GetCurrentThreadId()
            there = _user32.GetWindowThreadProcessId(_foreground(), None)
            _user32.AttachThreadInput(here, there, True)
            _user32.SetForegroundWindow(hwnd)
            _user32.AttachThreadInput(here, there, False)
        else:
            _chord(VK_MENU)                            # a key press makes Windows allow it
            _user32.SetForegroundWindow(hwnd)
        for _ in range(20):
            if _foreground() == hwnd:
                return True
            time.sleep(0.05)
    return False


def _still_in(hwnd):
    if _foreground() != hwnd:
        raise OSError("You switched windows, so I stopped before typing anything.")


_send_lock = threading.Lock()


def send_discord_dm(sender, text):
    """Send `text` as a DM to `sender` (the name shown on their notification).

    Raises OSError with a plain explanation if it can't. Blocks for ~3 seconds.
    """
    _require_windows()
    sender, text = (sender or "").strip(), (text or "").strip()
    if not sender or not text:
        raise OSError("There is nobody to send to, or nothing to send.")
    if not _send_lock.acquire(timeout=20):
        raise OSError("Already sending another Discord message.")
    previous = _foreground()
    discord = None
    try:
        discord = find_discord_window()
        if discord is None:
            raise OSError("I can't find the Discord window. Open Discord once "
                          "(it can't be closed all the way to the tray).")
        if not _bring_to_front(discord):
            raise OSError("Windows wouldn't let me bring Discord to the front.")
        time.sleep(PAUSE_AFTER_FOCUS)

        _still_in(discord)
        _chord(VK_CONTROL, VK_K)                       # Discord's quick switcher
        time.sleep(PAUSE_AFTER_SWITCHER)
        _still_in(discord)
        _type_text("@" + sender)                       # "@" = people only, not channels
        time.sleep(PAUSE_FOR_SEARCH)
        _still_in(discord)
        _chord(VK_RETURN)                              # jump to their DM
        time.sleep(PAUSE_AFTER_JUMP)

        _still_in(discord)
        _type_text(text)
        time.sleep(0.15)
        _still_in(discord)
        _chord(VK_RETURN)                              # send
        time.sleep(0.2)
    except OSError:
        if discord is not None and _foreground() == discord:
            _chord(VK_ESCAPE)                          # close the quick switcher if it's open
        raise
    finally:
        if previous and previous != discord and _user32.IsWindow(previous):
            _bring_to_front(previous)                  # back to VS Code (or whatever it was)
        _send_lock.release()


# ---- speaking, and "am I busy?" -----------------------------------------------------------
_speech = {"process": None}


def speak(text):
    """Say something out loud with Windows' built-in voice, without waiting for it."""
    _require_windows()
    previous = _speech["process"]
    if previous is not None and previous.poll() is None:
        previous.terminate()                            # a newer message cuts the old one off
    env = dict(os.environ, CC_SPEAK=(text or "")[:600])   # via an env var: never parsed as code
    command = ("Add-Type -AssemblyName System.Speech; "
               "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
               "$s.Speak($env:CC_SPEAK)")
    _speech["process"] = subprocess.Popen(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=0x08000000)     # no console window


def exe_name(name):
    """'Code', 'code.exe' and 'CODE.EXE' are all the same program."""
    name = (name or "").strip().lower()
    return name if not name or name.endswith(".exe") else name + ".exe"


def running_program_names():
    import psutil
    return {(p.info["name"] or "").lower() for p in psutil.process_iter(["name"])}


def foreground_program():
    return _process_name(_foreground()) if IS_WINDOWS else ""


def running_apps():
    """Programs that have a window open right now (for the 'add an app' list)."""
    if not IS_WINDOWS:
        return []
    names = set()

    def visit(hwnd, _lparam):
        if _user32.IsWindowVisible(hwnd) and _window_title(hwnd):
            name = _process_name(hwnd)
            if name and name not in SHELL_PROGRAMS:
                names.add(name)
        return True

    _user32.EnumWindows(_WNDENUMPROC(visit), 0)
    return sorted(names)


def fullscreen_active():
    """Is a game or video filling the whole screen? (borderless / F11 style windows)"""
    if not IS_WINDOWS:
        return False
    hwnd = _foreground()
    if not hwnd or _process_name(hwnd) in SHELL_PROGRAMS:
        return False
    if _user32.GetWindowLongW(hwnd, -16) & 0x00C00000 == 0x00C00000:   # has a title bar
        return False
    rect = wintypes.RECT()
    _user32.GetWindowRect(hwnd, ctypes.byref(rect))
    monitor = _user32.MonitorFromWindow(hwnd, 2)                     # nearest monitor
    info = _MONITORINFO()
    info.cbSize = ctypes.sizeof(_MONITORINFO)
    if not _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return False
    area = info.rcMonitor
    return (rect.left <= area.left and rect.top <= area.top
            and rect.right >= area.right and rect.bottom >= area.bottom)


def _discord_capture_active():
    """Is Discord using the microphone right now? (needs pycaw)"""
    import comtypes
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import IAudioSessionControl2, IAudioSessionManager2
    try:
        from pycaw.constants import CLSID_MMDeviceEnumerator
    except ImportError:
        from pycaw.api.mmdeviceapi import CLSID_MMDeviceEnumerator
    try:
        from pycaw.pycaw import IMMDeviceEnumerator
    except ImportError:
        from pycaw.api.mmdeviceapi import IMMDeviceEnumerator
    import psutil

    enumerator = comtypes.CoCreateInstance(
        CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, comtypes.CLSCTX_INPROC_SERVER)
    device = enumerator.GetDefaultAudioEndpoint(1, 1)           # 1 = capture (microphone)
    manager = device.Activate(IAudioSessionManager2._iid_, CLSCTX_ALL, None) \
        .QueryInterface(IAudioSessionManager2)
    sessions = manager.GetSessionEnumerator()
    for index in range(sessions.GetCount()):
        control = sessions.GetSession(index)
        pid = control.QueryInterface(IAudioSessionControl2).GetProcessId()
        try:
            name = psutil.Process(pid).name().lower()
        except Exception:
            continue
        if name.startswith("discord") and control.GetState() == 1:      # 1 = active
            return True
    return False


def _discord_playing_audio():
    """Is Discord playing sound right now (people talking in a call)?"""
    from pycaw.pycaw import AudioUtilities
    for session in AudioUtilities.GetAllSessions():
        process = session.Process
        if process is not None and process.name().lower().startswith("discord") \
                and session.State == 1:
            return True
    return False


def in_discord_call():
    """True / False, or None when it can't be checked (pycaw missing). Best effort."""
    if not IS_WINDOWS:
        return None
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        return None
    try:
        for probe in (_discord_capture_active, _discord_playing_audio):
            try:
                if probe():
                    return True
            except ImportError:
                return None
            except Exception:
                continue
        return False
    finally:
        try:
            comtypes.CoUninitialize()
        except Exception:
            pass


DEFAULT_BUSY_SETTINGS = {
    "manual": False,          # "I'm busy right now" switch
    "apps": [],               # program names, e.g. ["Code.exe", "obs64.exe"]
    "apps_active_only": False,  # count an app only while it's the window in front
    "in_call": True,          # on a Discord call
    "fullscreen": False,      # a fullscreen game or video
}


def busy_reason(settings=None):
    """Why you're busy (a short phrase), or None when you're free."""
    cfg = dict(DEFAULT_BUSY_SETTINGS, **(settings or {}))
    if cfg["manual"]:
        return "busy mode is on"
    apps = {exe_name(a) for a in cfg["apps"] if exe_name(a)}
    if apps:
        try:
            if cfg["apps_active_only"]:
                front = foreground_program()
                if front in apps:
                    return front.replace(".exe", "")
            else:
                running = running_program_names() & apps
                if running:
                    return sorted(running)[0].replace(".exe", "") + " is open"
        except Exception:
            pass
    try:
        if cfg["fullscreen"] and fullscreen_active():
            return "a fullscreen app"
    except Exception:
        pass
    if cfg["in_call"] and in_discord_call():
        return "a Discord call"
    return None


def diagnose(svc=None):
    """A checklist for the 'Check setup' button: [(state, text)], state = ok / bad / info."""
    svc = svc or service()
    if not IS_WINDOWS:
        return [("bad", "This only works on Windows.")]
    out = []
    problem = package_problem()
    out.append(("bad", problem) if problem
               else ("ok", "The notification packages are installed."))
    status = svc.status
    if status.startswith("Listening"):
        out.append(("ok", "Windows lets this app read notifications."))
    elif status == "Off":
        out.append(("bad", "Switch on “Listen for new Discord DMs” first."))
    else:
        out.append(("bad", status))
    out.append(("ok", "The Discord window was found.") if find_discord_window()
               else ("bad", "I can't find the Discord window. Open Discord (not just the "
                            "tray icon) and try again."))
    latest = svc.latest()
    out.append(("ok", f"Last DM seen: {latest[0]}") if latest else
               ("info", "No DM seen yet. Ask a friend to message you while Discord is in the "
                        "background. A Windows pop-up must appear."))
    call = in_discord_call()
    out.append(("info", "Call detection needs the optional pycaw package.") if call is None
               else ("ok", "You're on a Discord call right now.") if call
               else ("ok", "Call detection works (you're not on a call)."))
    return out


# ---- the service ----------------------------------------------------------------------------
class DiscordService:
    def __init__(self, sender=send_discord_dm, busy_probe=busy_reason, speaker=speak,
                 clock=time.time):
        self._send, self._busy_probe, self._speak, self._clock = sender, busy_probe, speaker, clock
        self._lock = threading.Lock()
        self._latest = None                 # (sender, message, time)
        self._busy_sent = {}                # sender -> time of the last busy reply
        self._status = "Off"
        self._stop = threading.Event()
        self._thread = None
        self.events = []                    # ("busy_sent", name) / ("error", text) for the UI
        self.seen_log = collections.deque(maxlen=12)   # what Windows showed us, and what we did
        self.polls = 0
        self.visible = 0                    # notifications Windows listed at the last look
        self.last_error = ""
        self.auto_busy = False
        self.busy_message = DEFAULT_BUSY_MESSAGE
        self.busy_settings = dict(DEFAULT_BUSY_SETTINGS)

    # ---- settings and state ---------------------------------------------------------
    def configure(self, auto_busy, busy_message, busy_settings=None):
        self.auto_busy = bool(auto_busy)
        self.busy_message = (busy_message or "").strip() or DEFAULT_BUSY_MESSAGE
        self.busy_settings = dict(DEFAULT_BUSY_SETTINGS, **(busy_settings or {}))

    @property
    def status(self):
        return self._status

    def latest(self):
        """(sender, message) of the newest DM from the last two hours, or None."""
        with self._lock:
            if self._latest and self._clock() - self._latest[2] <= RECENT_SECONDS:
                return self._latest[0], self._latest[1]
        return None

    def take_events(self):
        with self._lock:
            events, self.events = self.events, []
        return events

    def _event(self, *item):
        with self._lock:
            self.events.append(item)
            del self.events[:-20]

    # ---- what the voice steps call ------------------------------------------------------
    def read_latest_aloud(self):
        latest = self.latest()
        if latest is None:
            self._speak("You have no recent Discord messages.")
        else:
            sender, message = latest
            self._speak(f"{sender} said: {message or 'something I can not read'}")

    def reply_to_latest(self, text):
        latest = self.latest()
        if latest is None:
            raise OSError("There's no recent Discord DM to reply to.")
        self._send(latest[0], text)

    # ---- a notification arrived ---------------------------------------------------------
    def _log(self, app_name, texts, verdict):
        with self._lock:
            self.seen_log.append((self._clock(), app_name or "?", list(texts or []), verdict))

    def handle_notification(self, app_name, texts):
        """Called with the pop-up's app name and text lines. Returns True if it was a DM."""
        if "discord" not in (app_name or "").lower():
            self._log(app_name, texts, "ignored: not Discord")
            return False
        if not texts:
            self._log(app_name, texts, "ignored: no text")
            return False
        title = (texts[0] or "").strip()
        body = "\n".join(t for t in texts[1:] if t).strip()
        if not is_dm_title(title):
            self._log(app_name, texts, "ignored: server or group message (title has brackets)")
            return False
        with self._lock:
            self._latest = (title, body, self._clock())
        self._log(app_name, texts, "DM saved ✓")
        if self.auto_busy:
            threading.Thread(target=self._auto_busy, args=(title,), daemon=True).start()
        return True

    def describe_log(self):
        """Plain-text report of what Windows has shown this app (for the 'what it sees' button)."""
        with self._lock:
            entries = list(self.seen_log)
        lines = [f"Windows lists {self.visible} notification(s) right now; checked {self.polls} "
                 f"times." + (f"  Last error: {self.last_error}" if self.last_error else "")]
        if not entries:
            lines.append("Nothing has arrived since this was switched on. Ask a friend to DM "
                         "you while Discord is in the background.")
        for when, app, texts, verdict in reversed(entries):
            clock = time.strftime("%H:%M:%S", time.localtime(when))
            shown = " | ".join(t[:40] for t in texts) or "(no text)"
            lines.append(f"{clock}  [{app}]  {shown}   →  {verdict}")
        return "\n".join(lines)

    def _auto_busy(self, sender):
        key = sender.lower()
        with self._lock:
            last = self._busy_sent.get(key)
            if last is not None and self._clock() - last < COOLDOWN_SECONDS:
                return                                   # already told them recently
            self._busy_sent[key] = self._clock()         # claim it before the slow part
        try:
            reason = self._busy_probe(self.busy_settings)
            if not reason:
                with self._lock:
                    self._busy_sent.pop(key, None)       # not busy: no cooldown started
                return
            self._send(sender, self.busy_message)
            self._event("busy_sent", sender, reason)
        except Exception as exc:
            with self._lock:
                self._busy_sent.pop(key, None)
            self._event("error", f"Couldn't send the busy reply to {sender}: {exc}")

    # ---- the background listener -----------------------------------------------------------
    def start(self):
        if not IS_WINDOWS:
            self._status = "Windows only"
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._status = "Starting…"
        self._thread = threading.Thread(target=self._main, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._status = "Off"

    def _main(self):
        try:
            try:
                for name in WINRT_MODULES[:3]:           # helpers winrt 2.x needs loaded first
                    try:
                        importlib.import_module(name)
                    except ModuleNotFoundError:
                        pass
                from winrt.windows.ui.notifications import (
                    KnownNotificationBindings, NotificationKinds)
                from winrt.windows.ui.notifications.management import (
                    UserNotificationListener, UserNotificationListenerAccessStatus)
            except ImportError:
                from winsdk.windows.ui.notifications import (
                    KnownNotificationBindings, NotificationKinds)
                from winsdk.windows.ui.notifications.management import (
                    UserNotificationListener, UserNotificationListenerAccessStatus)
        except ImportError:
            self._status = "Needs packages:  " + (package_problem() or INSTALL_HINT)
            return
        try:
            try:
                from winrt.runtime import init_apartment, MTA
                init_apartment(MTA)
            except Exception:
                pass
            asyncio.run(self._poll(KnownNotificationBindings, NotificationKinds,
                                   UserNotificationListener,
                                   UserNotificationListenerAccessStatus))
        except Exception as exc:
            self._status = f"Stopped: {exc}"

    async def _poll(self, bindings, kinds, listener_cls, access_cls):
        listener = listener_cls.current
        while not self._stop.is_set():
            access = await listener.request_access_async()
            if access == access_cls.ALLOWED:
                break
            self._status = ("Windows hasn't allowed notification access. Open Settings → "
                            "Privacy & security → Notifications, allow it for this app, "
                            "then switch this off and on.")
            await asyncio.sleep(5)
        # winrt 1.x: method; winrt 2.x/3.x and winsdk: property
        toast_template = (bindings.get_toast_generic()
                          if hasattr(bindings, "get_toast_generic")
                          else bindings.toast_generic)

        seen, first = set(), True
        while not self._stop.is_set():
            self._status = "Listening for Discord DMs"
            try:
                notifications = await listener.get_notifications_async(kinds.TOAST)
                current = set()
                count = 0
                for item in notifications:
                    if item is None:
                        continue
                    count += 1
                    try:
                        app_info = getattr(item, "app_info", None)
                        display_info = getattr(app_info, "display_info", None) if app_info else None
                        app = getattr(display_info, "display_name", "") if display_info else ""
                        if not app:
                            continue
                        notif = getattr(item, "notification", None)
                        visual = getattr(notif, "visual", None) if notif else None
                        if visual is None:
                            continue
                        binding = visual.get_binding(toast_template)
                        if binding is None:
                            continue
                        texts = _text_lines(binding.get_text_elements())
                    except Exception as exc:
                        self.last_error = f"couldn't read a notification: {exc}"
                        continue
                    # id + text: Discord may update one notification in place for new messages
                    key = (item.id, tuple(texts))
                    current.add(key)
                    if key in seen:
                        continue
                    if first:
                        self._log(app, texts, "was already there when the app started: skipped")
                    else:
                        self.handle_notification(app, texts)
                seen, first = current, False
                self.visible = count
                self.polls += 1
            except Exception as exc:
                self.last_error = str(exc)
                self._status = f"Can't read notifications: {exc}"
            await asyncio.sleep(POLL_SECONDS)


def _text_lines(elements):
    """The text lines of a toast. winrt vectors iterate in some versions and need
    size/get_at in others, so try both."""
    texts = []
    if elements is None:
        return texts
    try:
        items = list(elements)
    except Exception:
        items = [elements.get_at(i) for i in range(getattr(elements, "size", 0))]
    for el in items:
        text = getattr(el, "text", "") if el is not None else ""
        if text:
            texts.append(str(text))
    return texts


_service = DiscordService()


def service():
    return _service
