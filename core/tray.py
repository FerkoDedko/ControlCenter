"""System tray icon (optional: needs the pystray and Pillow packages)."""
import importlib.util
import queue


def missing_packages():
    return [pkg for module, pkg in (("pystray", "pystray"), ("PIL", "Pillow"))
            if importlib.util.find_spec(module) is None]


def available():
    return not missing_packages()


class TrayIcon:
    """Clicking the tray icon, or its menu items, drops events on a queue.
    The main window reads them on its own thread (Tk isn't thread-safe)."""

    def __init__(self):
        self.events = queue.Queue()
        self._icon = None

    @staticmethod
    def _image(color):
        from PIL import Image, ImageDraw
        size = 64
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((2, 2, size - 2, size - 2), radius=16, fill=color)
        # A simple "C" made of an arc, so no font is needed.
        draw.arc((16, 16, 48, 48), start=40, end=320, fill="white", width=7)
        return image

    def start(self, color="#2f6df2"):
        import pystray
        menu = pystray.Menu(
            pystray.MenuItem("Show / hide Command Center",
                             lambda *_: self.events.put("toggle"), default=True),
            pystray.MenuItem("Quit", lambda *_: self.events.put("quit")),
        )
        self._icon = pystray.Icon("CommandCenter", self._image(color),
                                  "Command Center", menu)
        self._icon.run_detached()

    def stop(self):
        icon, self._icon = self._icon, None
        if icon:
            try:
                icon.stop()
            except Exception:
                pass
