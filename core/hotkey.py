"""Global keyboard shortcuts (work even when the window is hidden). Windows only.

Uses the Windows RegisterHotKey call directly, so no extra packages are needed.
Shortcuts are written like "ctrl+alt+c" or "win+shift+f5".
"""
import queue
import sys
import threading

MODIFIERS = {"alt": 0x0001, "ctrl": 0x0002, "control": 0x0002,
             "shift": 0x0004, "win": 0x0008, "windows": 0x0008}
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
WM_USER = 0x0400

_NAMED_KEYS = {
    "space": 0x20, "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B,
    "escape": 0x1B, "home": 0x24, "end": 0x23, "insert": 0x2D, "delete": 0x2E,
    "pageup": 0x21, "pagedown": 0x22, "left": 0x25, "up": 0x26,
    "right": 0x27, "down": 0x28,
}


def _key_code(name):
    if len(name) == 1 and name.isascii() and name.isalnum():
        return ord(name.upper())
    if name.startswith("f") and name[1:].isdigit() and 1 <= int(name[1:]) <= 24:
        return 0x70 + int(name[1:]) - 1
    return _NAMED_KEYS.get(name)


def parse_hotkey(text):
    """'ctrl+alt+c' -> (modifier bits, virtual-key code). Raises ValueError."""
    parts = [p for p in (text or "").lower().replace(" ", "").split("+") if p]
    if len(parts) < 2:
        raise ValueError("Use at least one modifier, like Ctrl+Alt+C.")
    modifiers = 0
    for part in parts[:-1]:
        if part not in MODIFIERS:
            raise ValueError(f"“{part}” isn't a modifier. Use Ctrl, Alt, Shift or Win.")
        modifiers |= MODIFIERS[part]
    key = _key_code(parts[-1])
    if key is None:
        raise ValueError(f"I don't know the key “{parts[-1]}”.")
    return modifiers, key


class HotkeyManager:
    def __init__(self):
        self.events = queue.Queue()      # names of shortcuts that were pressed
        self._thread = None
        self._thread_id = None
        self._errors = {}

    @staticmethod
    def supported():
        return sys.platform.startswith("win")

    def start(self, bindings):
        """Register {name: 'ctrl+alt+c'}. Returns {name: problem} for any that failed."""
        self.stop()
        self._errors = {}
        if not self.supported():
            return {name: "Global shortcuts only work on Windows." for name in bindings}
        parsed = {}
        for name, text in bindings.items():
            try:
                parsed[name] = parse_hotkey(text)
            except ValueError as exc:
                self._errors[name] = str(exc)
        if parsed:
            ready = threading.Event()
            self._thread = threading.Thread(target=self._run, args=(parsed, ready),
                                            daemon=True)
            self._thread.start()
            ready.wait(2)
        return dict(self._errors)

    def _run(self, parsed, ready):
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()
        message = wintypes.MSG()
        # Touching the message queue creates it, so stop() can post to it safely.
        user32.PeekMessageW(ctypes.byref(message), None, WM_USER, WM_USER, 0)

        registered = {}
        for index, (name, (modifiers, key)) in enumerate(parsed.items(), start=1):
            if user32.RegisterHotKey(None, index, modifiers | MOD_NOREPEAT, key):
                registered[index] = name
            else:
                self._errors[name] = "Another program is already using that shortcut."
        ready.set()

        while True:
            result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
            if result in (0, -1):
                break
            if message.message == WM_HOTKEY and message.wParam in registered:
                self.events.put(registered[message.wParam])
        for index in registered:
            user32.UnregisterHotKey(None, index)

    def stop(self):
        thread, self._thread = self._thread, None
        if thread and thread.is_alive() and self._thread_id and self.supported():
            import ctypes
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            thread.join(1)
