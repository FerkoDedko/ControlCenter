import tkinter.messagebox as messagebox

import customtkinter as ctk

from core import theme
from core.config import ACCENTS, DEFAULT_CONFIG, THEMES
from core.hotkey import parse_hotkey
from core.widgets import card, font, label
from .base import BasePage


class SettingsPage(BasePage):
    """Every change is saved automatically a moment after you make it."""

    def __init__(self, master, config, save_callback, test_callback=None, toast=None):
        super().__init__(master, toast)
        self.config_data = config
        self.save_callback = save_callback
        self.test_callback = test_callback
        self._getters = {}
        self._setters = {}
        self._save_job = None

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                             corner_radius=0)
        self.scroll.pack(fill="both", expand=True)
        self._build()

    # ---- layout -----------------------------------------------------------
    def _build(self):
        label(self.scroll, "Settings", 27, True).pack(
            anchor="w", padx=34, pady=(30, 4))
        label(self.scroll, "Make Command Center work the way you want", 11,
              False, theme.MUTED).pack(anchor="w", padx=34, pady=(0, 20))

        self._section("Appearance")
        self._switch("animations", "Animations (master switch)",
                     "Turns every animation below on or off at once.")
        self._switch("anim_pages", "   Page transitions",
                     "A wipe with an accent edge when you change page.")
        self._switch("anim_sidebar", "   Sidebar motion",
                     "The sliding highlight and colour fade on the menu.")
        self._switch("anim_scenes", "   Moving side-panel pictures",
                     "The globe, radar, gears… off keeps one still picture.")
        self._switch("anim_meters", "   Bars and numbers",
                     "Gauges, bars and counters glide to their new value.")
        self._switch("anim_toasts", "   Notifications",
                     "Pop-up messages slide in and out.")
        self._switch("anim_effects", "   Hover and pulse effects",
                     "Button hover fades, the live dot and the microphone pulse.")
        self._choice("theme", "Theme", THEMES)
        self._choice("accent_color", "Accent color", ACCENTS)

        self._section("When Command Center opens")
        self._switch("news_on_start", "Read me the news",
                     "Says the top headlines out loud when the app starts (needs internet).")
        self._switch("weather_on_start", "Tell me the weather",
                     "Says the weather out loud when the app starts (needs internet).")

        self._section("System alerts")
        self._switch("alerts_enabled", "Enable system warnings",
                     "Get notified when CPU, memory or disk thresholds are reached.")
        self._choice("alert_delivery", "Notification delivery",
                     ["both", "app", "windows"])
        self._switch("alert_sound", "Warning sound",
                     "Play a Windows alert sound when a new warning appears.")

        self._section("Warning thresholds")
        self._slider("cpu_threshold", "CPU warning threshold", 50, 100, "%")
        self._slider("ram_threshold", "RAM warning threshold", 50, 100, "%")
        self._slider("disk_free_threshold", "Low disk space warning", 1, 30, "% free")
        self._slider("alert_delay_seconds", "Alert delay", 0, 30, " s",
                     "Only warn if the limit stays exceeded this long. "
                     "Ignores short spikes.")

        self._section("Monitoring")
        self._switch("power_saver", "Power saver",
                     "While the window is hidden or minimised, refresh much less often "
                     "and stop the pictures. Warnings and voice commands keep working.")
        self._choice("refresh_interval_ms", "Dashboard refresh rate",
                     ["500", "1000", "2000", "3000"], numeric=True)

        self._section("System tray and start-up")
        self._switch("tray_icon", "Show icon in the system tray",
                     "Needs:  py -m pip install pystray Pillow")
        self._switch("close_to_tray", "Closing the window keeps it running in the tray",
                     "Alerts and voice commands keep working. Quit from the tray icon.")
        self._switch("start_with_windows", "Start with Windows",
                     "Opens Command Center when you sign in.")
        self._switch("start_minimized", "Start hidden in the tray",
                     "Only used with the tray icon on and Start with Windows.")
        self._entry("hotkey_toggle", "Show / hide shortcut",
                    "Works anywhere in Windows, e.g.  ctrl+alt+c")
        self._entry("hotkey_voice", "Voice shortcut",
                    "Starts listening for a voice command, e.g.  ctrl+alt+v")

        footer = ctk.CTkFrame(self.scroll, fg_color="transparent")
        footer.pack(fill="x", padx=34, pady=24)
        if self.test_callback:
            button = ctk.CTkButton(footer, text="Send test alert", height=40,
                                   width=150, corner_radius=10, font=font(12, True),
                                   command=self.test_callback)
            theme.bind(button, fg_color="main", hover_color="hover")
            button.pack(side="left")
        ctk.CTkButton(footer, text="Reset to defaults", height=40, width=150,
                      corner_radius=10, font=font(12, True),
                      fg_color=theme.INPUT, hover_color=theme.HOVER,
                      text_color=theme.TEXT,
                      command=self._reset).pack(side="left", padx=10)
        self.saved_label = label(footer, "Changes are saved automatically.",
                                 10, False, theme.MUTED)
        self.saved_label.pack(side="left", padx=14)

    def _section(self, title):
        label(self.scroll, title.upper(), 10, True, theme.MUTED).pack(
            anchor="w", padx=36, pady=(19, 8))

    def _row(self, title, description=None):
        frame = card(self.scroll, corner_radius=12)
        frame.pack(fill="x", padx=34, pady=5)
        left = ctk.CTkFrame(frame, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True, padx=16, pady=12)
        label(left, title, 11, True).pack(anchor="w")
        if description:
            label(left, description, 9, False, theme.MUTED).pack(
                anchor="w", pady=(3, 0))
        frame.left = left
        return frame

    def _value(self, key):
        return self.config_data.get(key, DEFAULT_CONFIG[key])

    def _switch(self, key, title, description):
        row = self._row(title, description)
        var = ctk.BooleanVar(value=bool(self._value(key)))
        switch = ctk.CTkSwitch(row, text="", variable=var, onvalue=True,
                               offvalue=False, fg_color=theme.TRACK,
                               command=self._queue_save)
        theme.bind(switch, progress_color="main")
        switch.pack(side="right", padx=18)
        self._getters[key] = lambda: bool(var.get())
        self._setters[key] = lambda value: var.set(bool(value))

    def _choice(self, key, title, options, numeric=False):
        row = self._row(title)
        var = ctk.StringVar(value=str(self._value(key)))
        menu = ctk.CTkOptionMenu(
            row, values=[str(v) for v in options], variable=var,
            width=145, height=32, fg_color=theme.INPUT, text_color=theme.TEXT,
            dropdown_fg_color=theme.CARD, dropdown_text_color=theme.TEXT,
            dropdown_hover_color=theme.HOVER,
            command=lambda _value: self._queue_save(0))
        theme.bind(menu, button_color="main", button_hover_color="hover")
        menu.pack(side="right", padx=16)
        self._getters[key] = (lambda: int(var.get())) if numeric else var.get
        self._setters[key] = lambda value: var.set(str(value))

    def _entry(self, key, title, description):
        """A shortcut box. Invalid text shows a message and is not saved."""
        row = self._row(title, description)
        var = ctk.StringVar(value=str(self._value(key)))
        problem = label(row.left, "", 9, False, theme.DANGER)
        problem.pack(anchor="w")
        entry = ctk.CTkEntry(row, textvariable=var, width=170, height=32,
                             corner_radius=8, fg_color=theme.INPUT, border_width=0,
                             text_color=theme.TEXT)
        entry.pack(side="right", padx=16)

        def commit(_event=None):
            try:
                parse_hotkey(var.get().strip())
            except ValueError as exc:
                problem.configure(text=str(exc))
                return
            problem.configure(text="")
            self._queue_save(0)

        entry.bind("<Return>", commit)
        entry.bind("<FocusOut>", commit)

        def current():
            text = var.get().strip()
            try:
                parse_hotkey(text)
                return text
            except ValueError:
                return self._value(key)      # keep the last good shortcut

        self._getters[key] = current
        self._setters[key] = lambda value: (var.set(str(value)), problem.configure(text=""))

    def _slider(self, key, title, minimum, maximum, suffix, description=None):
        row = self._row(title, description)
        text = ctk.StringVar()
        label_widget = ctk.CTkLabel(row, textvariable=text, width=65,
                                    font=font(11, True), text_color=theme.TEXT_SOFT)
        label_widget.pack(side="right", padx=(0, 16))

        def moved(value):
            text.set(f"{value:.0f}{suffix}")
            self._queue_save()

        slider = ctk.CTkSlider(row, from_=minimum, to=maximum,
                               number_of_steps=maximum - minimum, width=190,
                               command=moved)
        theme.bind(slider, progress_color="main", button_color="main",
                   button_hover_color="hover")
        slider.pack(side="right", padx=10)

        def set_value(value):
            slider.set(float(value))
            text.set(f"{float(value):.0f}{suffix}")

        set_value(self._value(key))
        self._getters[key] = lambda: int(round(slider.get()))
        self._setters[key] = set_value

    # ---- saving -----------------------------------------------------------
    def _queue_save(self, delay=400):
        if self._save_job:
            self.after_cancel(self._save_job)
        self.saved_label.configure(text="Saving…", text_color=theme.MUTED)
        self._save_job = self.after(delay, self._save_now)

    def _save_now(self):
        self._save_job = None
        try:
            self.save_callback({key: get() for key, get in self._getters.items()})
            self.saved_label.configure(text="✓ Saved", text_color=theme.OK)
        except OSError as exc:
            self.saved_label.configure(text=f"Couldn't save: {exc}",
                                       text_color=theme.DANGER)

    def _reset(self):
        if not messagebox.askyesno("Reset settings",
                                   "Put every setting back to its default?",
                                   parent=self.winfo_toplevel()):
            return
        # Only the settings shown on this page (voice options live on the Voice page).
        self.save_callback({key: DEFAULT_CONFIG[key] for key in self._getters})
        self.refresh_from_config()
        self.saved_label.configure(text="✓ Defaults restored", text_color=theme.OK)

    def refresh_from_config(self):
        """Make every control match the current config."""
        for key, setter in self._setters.items():
            setter(self._value(key))
