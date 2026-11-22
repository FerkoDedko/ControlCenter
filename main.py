import sys
import threading

import customtkinter as ctk

from core import anim, autostart, discord_dm, theme
from core.backdrop import SCENE_BY_PAGE, Backdrop
from pages.setup import SetupDialog
from pages.tutorial import TutorialDialog
from core import tray as tray_module
from core.alerts import AlertManager
from core.config import load_config, save_config
from core.hotkey import HotkeyManager
from core.monitor import SystemMonitor
from core.widgets import font, label
from pages.cleanup import CleanupPage
from pages.dashboard import DashboardPage
from pages.hardware import HardwarePage
from pages.launcher import LauncherPage
from pages.network import NetworkPage
from pages.processes import ProcessesPage
from pages.settings import SettingsPage
from pages.startup_page import StartupPage
from pages.storage import StoragePage
from pages.voice import VoicePage

ctk.set_default_color_theme("blue")


class CommandCenter(ctk.CTk):
    NAV_ITEMS = [
        ("⌂", "Dashboard"),
        ("▤", "Processes"),
        ("▦", "Storage"),
        ("⌁", "Network"),
        ("◈", "Hardware"),
        ("✧", "Cleanup"),
        ("▣", "App Launcher"),
        ("◷", "Startup Manager"),
        ("◍", "Voice Control"),
        ("⚙", "Settings"),
    ]
    TOAST_MS = 6500
    TOAST_OFFSET = 360

    def __init__(self):
        super().__init__()
        self.title("Command Center")
        self.geometry("1380x860")
        self.minsize(1100, 700)

        self.config_data = load_config()
        theme.apply(self.config_data)          # theme, accent and animations
        self.configure(fg_color=theme.BG)

        self.monitor = SystemMonitor()
        self.alerts = AlertManager(self, self.config_data, self.show_toast)
        self.hotkeys = HotkeyManager()
        self.tray = None
        self._applied = {}

        self._running = True
        self._tick_job = None
        self._toast_after = None
        self._toast_frame = None
        self._current = None
        self._pages = {}
        self._nav_buttons = {}
        self._nav_level = {}
        self._indicator_y = None

        self._build_shell()
        self._build_pages()
        theme.on_change(self._restyle_nav)

        self.update_idletasks()
        self.show_page("Dashboard")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self._tutorial = None
        if not self.config_data.get("setup_done") and "--minimized" not in sys.argv:
            self.after(900, self.open_setup)        # first run: choose features, then the tour
        elif not self.config_data.get("tutorial_seen") and "--minimized" not in sys.argv:
            self.after(900, self.open_tutorial)

        problems = self._apply_system_settings()
        if "--minimized" in sys.argv and self.tray is not None:
            self.withdraw()                    # started with Windows: wait in the tray
        if problems:
            self.after(900, lambda: self.show_toast("Heads up", "\n".join(problems), "warning"))

        if self.config_data.get("news_on_start") or self.config_data.get("weather_on_start"):
            self.after(4000, self._morning_briefing)

        self._tick_job = self.after(250, self._tick)
        self.after(1500, self._poll_theme)
        self.after(150, self._poll_events)

    # ---- layout -----------------------------------------------------------
    def _build_shell(self):
        self.sidebar = ctk.CTkFrame(self, width=238, corner_radius=0,
                                    fg_color=theme.SIDEBAR, border_width=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=22, pady=(24, 22))

        mark = ctk.CTkFrame(brand, width=38, height=38, corner_radius=12)
        theme.bind(mark, fg_color="main")
        mark.pack(side="left")
        mark.pack_propagate(False)
        ctk.CTkLabel(mark, text="C", font=font(21, True),
                     text_color="white").place(relx=.5, rely=.48, anchor="center")

        brand_text = ctk.CTkFrame(brand, fg_color="transparent")
        brand_text.pack(side="left", padx=11)
        label(brand_text, "COMMAND CENTER", 13, True).pack(anchor="w")
        label(brand_text, "PC CONTROL SUITE", 9, True, theme.MUTED).pack(
            anchor="w", pady=(2, 0))

        label(self.sidebar, "WORKSPACE", 9, True, theme.MUTED).pack(
            anchor="w", padx=25, pady=(0, 8))

        for icon, name in self.NAV_ITEMS:
            button = ctk.CTkButton(
                self.sidebar, text=f"  {icon}     {name}",
                height=40, corner_radius=10, anchor="w", font=font(12, True),
                fg_color="transparent", hover_color=theme.HOVER,
                text_color=theme.TEXT_SOFT,
                command=lambda n=name: self.show_page(n))
            button.pack(fill="x", padx=13, pady=2)
            self._nav_buttons[name] = button
            self._nav_level[name] = 0.0

        # A little bar that slides to whichever page is open.
        self.indicator = ctk.CTkFrame(self.sidebar, width=4, height=24,
                                      corner_radius=2)
        theme.bind(self.indicator, fg_color="main")

        bottom = ctk.CTkFrame(self.sidebar, fg_color=theme.CARD_ALT, corner_radius=12)
        bottom.pack(side="bottom", fill="x", padx=14, pady=16)
        ctk.CTkButton(self.sidebar, text="?   How to use", height=34, corner_radius=10,
                      fg_color="transparent", hover_color=theme.HOVER,
                      text_color=theme.TEXT_SOFT, anchor="w",
                      command=self.open_tutorial).pack(side="bottom", fill="x", padx=14)
        label(bottom, "●  SYSTEM ONLINE", 10, True, theme.OK).pack(
            anchor="w", padx=13, pady=(12, 3))
        label(bottom, "Monitoring this device", 10, False, theme.MUTED).pack(
            anchor="w", padx=13, pady=(0, 12))

        self.main_area = ctk.CTkFrame(self, fg_color=theme.BG, corner_radius=0)
        self.main_area.pack(side="right", fill="both", expand=True)

        # Page change: a cover in the page colour wipes away left to right, with a thin
        # accent edge leading it. Only these two small frames move, so it stays smooth.
        self.wipe = ctk.CTkFrame(self.main_area, fg_color=theme.BG, corner_radius=0)
        self.wipe_edge = ctk.CTkFrame(self.main_area, width=3, corner_radius=0)
        theme.bind(self.wipe_edge, fg_color="main")

        # A themed animated picture on the right of every page. Widgets can't be see-through,
        # so it gets its own strip; pages use the rest. On narrow windows it's left out.
        self.scene = Backdrop(self.main_area, "globe")
        self._panel_frac = 0.0
        self.main_area.bind("<Configure>", self._relayout)
        self.bind("<Unmap>", lambda e: self.scene.stop() if e.widget is self else None)
        self._geometry = None
        self._moving_job = None
        self.bind("<Configure>", self._on_window_moved, add="+")
        self.bind("<Map>", lambda e: self._relayout() if e.widget is self else None)

    def _build_pages(self):
        area, toast = self.main_area, self.show_toast
        self._pages["Dashboard"] = DashboardPage(
            area, self.config_data, self.alerts, toast)
        self._pages["Processes"] = ProcessesPage(area, toast)
        self._pages["Storage"] = StoragePage(area, toast)
        self._pages["Network"] = NetworkPage(area, toast)
        self._pages["Hardware"] = HardwarePage(area, toast)
        self._pages["Cleanup"] = CleanupPage(area, toast)
        self._pages["App Launcher"] = LauncherPage(area, toast)
        self._pages["Startup Manager"] = StartupPage(area, toast)
        self._pages["Voice Control"] = VoicePage(
            area, self.config_data, self.save_settings, toast)
        self._pages["Settings"] = SettingsPage(
            area, self.config_data, self.save_settings, self.alerts.send_test, toast)

    # ---- page switching ---------------------------------------------------
    def open_setup(self):
        def done():
            self.save_settings({"setup_done": True})
            if not self.config_data.get("tutorial_seen"):
                self.open_tutorial()
        SetupDialog(self, on_done=done)

    def apply_setup(self, chosen):
        """Turn on what the first-run setup asked for."""
        voice_page = self._pages["Voice Control"]
        changes = {"tray_icon": chosen["tray"], "close_to_tray": chosen["tray"],
                   "voice_consent": chosen["voice"], "discord_enabled": chosen["discord"],
                   "news_on_start": chosen["briefing"], "weather_on_start": chosen["briefing"]}
        try:
            voice_page.consent_var.set(chosen["voice"])
        except Exception:
            pass
        if chosen["voice"]:
            voice_page._add_presets()
        self.save_settings(changes)

    def open_tutorial(self):
        if self._tutorial is not None:
            try:
                if self._tutorial.winfo_exists():
                    self._tutorial.lift()
                    return
            except Exception:
                pass
        self._tutorial = TutorialDialog(
            self, on_close=lambda: self.save_settings({"tutorial_seen": True}))

    def _on_window_moved(self, event):
        """While the window is being dragged or resized, pause the side picture; Tk redraws
        it dozens of times a second and the window tears. It resumes when you let go."""
        if event.widget is not self:
            return
        geometry = (self.winfo_x(), self.winfo_y(), self.winfo_width(), self.winfo_height())
        if geometry == self._geometry:
            return
        self._geometry = geometry
        self.scene.stop()
        if self._moving_job is not None:
            self.after_cancel(self._moving_job)
        self._moving_job = self.after(220, self._after_move)

    def _after_move(self):
        self._moving_job = None
        if self._panel_frac and self.state() == "normal":
            self.scene.start()

    PANEL_MIN_WINDOW = 1100          # narrower than this: no picture panel
    def _relayout(self, event=None):
        width = self.main_area.winfo_width()
        frac = 0.0
        if width >= self.PANEL_MIN_WINDOW:
            frac = min(max(width * 0.25, 260), 380) / width
        if abs(frac - self._panel_frac) < 0.002 and event is not None:
            return
        if frac and self.scene._job is None and event is None:
            self.scene.start()
        self._panel_frac = frac
        if frac:
            self.scene.place(relx=1 - frac, y=0, relwidth=frac, relheight=1)
            self.scene.start()
        else:
            self.scene.stop()
            self.scene.place_forget()
        page = self._pages.get(self._current)
        if page is not None:
            page.place_configure(relwidth=1 - frac)

    def show_page(self, name):
        if name == self._current:
            return
        previous = self._pages.get(self._current)
        if previous:
            previous.on_hide()
            previous.place_forget()

        page = self._pages[name]
        self._current = name
        if name == "Settings":
            page.refresh_from_config()
        page.place(x=0, y=0, relwidth=1 - self._panel_frac, relheight=1)
        page.on_show()
        self.scene.set_kind(SCENE_BY_PAGE.get(name, "globe"))
        self._update_nav(name)
        self._wipe()

    def _wipe(self):
        if not anim.is_enabled("pages"):
            return
        span = 1 - self._panel_frac                    # the area the pages use
        self.wipe.place(relx=0, y=0, relwidth=span, relheight=1)
        self.wipe.tkraise()
        self.wipe_edge.place(relx=0, y=0, relheight=1)
        self.wipe_edge.tkraise()

        def step(v):
            self.wipe.place_configure(relx=v * span, relwidth=max(span * (1 - v), 0.001))
            self.wipe_edge.place_configure(relx=v * span)

        def finish():
            self.wipe.place_forget()
            self.wipe_edge.place_forget()

        anim.animate(self.wipe, "wipe", 0.0, 1.0, 300, step, done=finish,
                     easing=anim.ease_in_out, kind="pages")

    def _nav_colors(self, active):
        if active:
            return theme.accent("soft"), theme.accent("text")
        return "transparent", theme.TEXT_SOFT

    def _update_nav(self, name):
        for nav_name, button in self._nav_buttons.items():
            self._fade_nav(nav_name, button, nav_name == name)

        # The indicator is positioned in real pixels (read from the buttons), so
        # it uses place_configure, which skips customtkinter's DPI scaling.
        target = self._indicator_target(name)
        if self._indicator_y is None:
            self.indicator.place_configure(x=0, y=target)
            self._indicator_y = target
        else:
            def move(y):
                self._indicator_y = y
                self.indicator.place_configure(x=0, y=int(y))
            anim.animate(self.indicator, "move", self._indicator_y, target, 280,
                         move, easing=anim.ease_out_back, kind="sidebar")

    def _indicator_target(self, name):
        button = self._nav_buttons[name]
        return button.winfo_y() + (button.winfo_height()
                                   - self.indicator.winfo_reqheight()) // 2

    def _fade_nav(self, name, button, active):
        start = self._nav_level[name]
        end = 1.0 if active else 0.0

        def step(level):
            self._nav_level[name] = level
            button.configure(
                fg_color=theme.lerp(theme.resolve(theme.SIDEBAR),
                                    theme.resolve(theme.accent("soft")), level),
                text_color=theme.lerp(theme.resolve(theme.TEXT_SOFT),
                                      theme.resolve(theme.accent("text")), level))

        def settle():
            fg, text = self._nav_colors(active)
            button.configure(fg_color=fg, text_color=text)

        anim.animate(button, "fade", start, end, 200, step, done=settle, kind="sidebar")

    def _restyle_nav(self):
        for name, button in self._nav_buttons.items():
            fg, text = self._nav_colors(name == self._current)
            button.configure(fg_color=fg, text_color=text, hover_color=theme.HOVER)

    # ---- monitoring (runs for the whole life of the app) -------------------
    def _tick(self):
        if not self._running:
            return
        dashboard = self._pages["Dashboard"]
        interval = max(500, int(self.config_data.get("refresh_interval_ms", 1000)))
        hidden = self.config_data.get("power_saver", True) and self.state() in ("withdrawn", "iconic")
        try:
            stats = self.monitor.snapshot()
            self.alerts.check(stats)
            if not hidden:
                dashboard.update_stats(stats)          # nobody is looking: skip the drawing
        except Exception as exc:
            dashboard.show_error(exc)
        if hidden:
            interval = max(interval, 4000)
        self._tick_job = self.after(interval, self._tick)

    def _poll_theme(self):
        if not self._running:
            return
        theme.poll_system_mode()
        self.after(1500, self._poll_theme)

    # ---- tray icon, global shortcuts and window hiding ----------------------
    def _poll_events(self):
        if not self._running:
            return
        events = []
        if self.tray is not None:
            while not self.tray.events.empty():
                events.append(self.tray.events.get_nowait())
        while not self.hotkeys.events.empty():
            events.append(self.hotkeys.events.get_nowait())
        for kind, *details in discord_dm.service().take_events():
            if kind == "busy_sent":
                self.show_toast("Auto-Busy", f"Told {details[0]} you're busy ({details[1]}).",
                                "info")
            elif kind == "error":
                self.show_toast("Discord", details[0], "error")
        for event in events:
            if event == "toggle":
                self._toggle_window()
            elif event == "quit":
                self._quit()
                return
            elif event == "voice":
                self._pages["Voice Control"].push_to_talk()
        self.after(150, self._poll_events)

    def _toggle_window(self):
        if self.state() in ("withdrawn", "iconic"):
            self.deiconify()
            self.lift()
            self.focus_force()
        else:
            self.withdraw()

    def _apply_system_settings(self):
        """Make the tray icon, shortcuts and Windows start-up match the settings.
        Returns a list of problems to show the user."""
        cfg, problems = self.config_data, []

        if cfg.get("tray_icon"):
            if self.tray is None:
                missing = tray_module.missing_packages()
                if missing:
                    problems.append("Tray icon needs:  py -m pip install " + " ".join(missing))
                else:
                    try:
                        icon = tray_module.TrayIcon()
                        icon.start(theme.accent("main"))
                        self.tray = icon
                    except Exception as exc:
                        problems.append(f"Couldn't create the tray icon: {exc}")
        elif self.tray is not None:
            self.tray.stop()
            self.tray = None

        bindings = {"toggle": cfg.get("hotkey_toggle", ""), "voice": cfg.get("hotkey_voice", "")}
        if bindings != self._applied.get("hotkeys"):
            self._applied["hotkeys"] = dict(bindings)
            names = {"toggle": "Show / hide", "voice": "Voice"}
            errors = self.hotkeys.start({k: v for k, v in bindings.items() if v})
            problems += [f"{names[name]} shortcut: {message}" for name, message in errors.items()]

        wanted = (bool(cfg.get("start_with_windows")), bool(cfg.get("start_minimized")))
        if wanted != self._applied.get("autostart"):
            self._applied["autostart"] = wanted
            if not autostart.supported():
                if wanted[0]:
                    problems.append("Start with Windows only works on Windows.")
            else:
                try:
                    if wanted[0]:
                        autostart.set_enabled(True, minimized=wanted[1])
                    elif autostart.is_enabled():
                        autostart.set_enabled(False)
                except OSError as exc:
                    problems.append(f"Couldn't change Start with Windows: {exc}")

        discord = discord_dm.service()
        discord.configure(cfg.get("discord_auto_busy"), cfg.get("discord_busy_message"), {
            "manual": cfg.get("discord_busy_manual"),
            "apps": cfg.get("discord_busy_apps") or [],
            "apps_active_only": cfg.get("discord_busy_apps_active_only"),
            "in_call": cfg.get("discord_busy_in_call", True),
            "fullscreen": cfg.get("discord_busy_fullscreen"),
        })
        if cfg.get("discord_enabled"):
            if not discord_dm.IS_WINDOWS:
                problems.append("Discord DMs only work on Windows.")
            else:
                discord.start()
        else:
            discord.stop()
        return problems

    # ---- settings ---------------------------------------------------------
    def save_settings(self, new_config):
        self.config_data.update(new_config)
        save_config(self.config_data)
        self.alerts.update_config(self.config_data)
        theme.apply(self.config_data)
        self.configure(fg_color=theme.BG)
        self._pages["Dashboard"].update_config(self.config_data)
        problems = self._apply_system_settings()
        if self._panel_frac:
            self.scene.start()               # picks up the "side-panel pictures" switch
        if problems:
            self.show_toast("Heads up", "\n".join(problems), "warning")

    # ---- toast notifications ----------------------------------------------
    def _morning_briefing(self):
        """Read the weather and/or news aloud once, on a background thread."""
        from core import voice as voice_module
        want_weather = self.config_data.get("weather_on_start")
        want_news = self.config_data.get("news_on_start")

        def work():
            parts = []
            if want_weather:
                parts.append(voice_module.BUILTINS["weather"]())
            if want_news:
                parts.append(voice_module.news_text())
            text = "  ".join(parts)
            try:
                discord_dm.speak(text)
            except Exception:
                pass
            try:
                self.after(0, lambda: self.show_toast("Your briefing", text, "info"))
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def show_toast(self, title, message, level="warning"):
        self._dismiss_toast(immediate=True)
        accent = {"warning": theme.WARN, "error": theme.DANGER}.get(level, theme.OK)

        toast = ctk.CTkFrame(self.main_area, fg_color=theme.TOAST_BG,
                             corner_radius=13, border_width=1,
                             border_color=theme.TOAST_BORDER)
        self._toast_frame = toast

        top = ctk.CTkFrame(toast, fg_color="transparent")
        top.pack(fill="x", padx=15, pady=(11, 2))
        label(top, "●", 14, False, accent).pack(side="left")
        label(top, title, 12, True).pack(side="left", padx=8)
        ctk.CTkButton(top, text="×", width=24, height=22, fg_color="transparent",
                      hover_color=theme.TOAST_BORDER, text_color=theme.TEXT_SOFT,
                      command=self._dismiss_toast).pack(side="right")
        label(toast, message, 11, False, theme.TEXT_SOFT, wraplength=280,
              justify="left").pack(anchor="w", padx=37, pady=(0, 10))

        if anim.is_enabled("toasts"):
            bar = ctk.CTkProgressBar(toast, height=3, corner_radius=2,
                                     fg_color=theme.TOAST_BORDER,
                                     progress_color=accent)
            bar.pack(fill="x", padx=15, pady=(0, 11))
            bar.set(1)
            anim.animate(bar, "countdown", 1.0, 0.0, self.TOAST_MS, bar.set,
                         easing=anim.linear, kind="toasts")
        else:
            ctk.CTkFrame(toast, height=3, fg_color="transparent").pack(pady=(0, 4))

        self._place_toast(toast, self.TOAST_OFFSET)
        toast.tkraise()
        anim.animate(toast, "slide", self.TOAST_OFFSET, 0, 380,
                     lambda offset: self._place_toast(toast, offset),
                     easing=anim.ease_out_back, kind="toasts")
        self._toast_after = self.after(self.TOAST_MS, self._dismiss_toast)

    def _dismiss_toast(self, immediate=False):
        if self._toast_after:
            self.after_cancel(self._toast_after)
            self._toast_after = None
        toast, self._toast_frame = self._toast_frame, None
        if toast is None:
            return
        if immediate:
            toast.destroy()
            return
        anim.animate(toast, "slide", 0, self.TOAST_OFFSET, 240,
                     lambda offset: self._place_toast(toast, offset),
                     done=toast.destroy, easing=anim.ease_in_cubic, kind="toasts")

    @staticmethod
    def _place_toast(toast, offset):
        toast.place(relx=1.0, x=-18 + int(offset), y=18, anchor="ne")

    # ---- closing ----------------------------------------------------------
    def on_close(self):
        if self.config_data.get("close_to_tray") and self.tray is not None:
            self.withdraw()                    # keep running in the tray
            return
        self._quit()

    def _quit(self):
        self._running = False
        self.hotkeys.stop()
        discord_dm.service().stop()
        if self.tray is not None:
            self.tray.stop()
        self._pages["Voice Control"].shutdown()
        self.destroy()


if __name__ == "__main__":
    app = CommandCenter()
    app.mainloop()
