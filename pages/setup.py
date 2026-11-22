"""First-run setup: pick what you want, and see right away what works and what needs a fix."""
import customtkinter as ctk

from core import discord_dm, theme, voice
from core.widgets import font, label

CHOICES = [
    ("voice", "Voice commands",
     "Control your PC by talking. Short recordings of what you say are sent to Google's "
     "speech service to turn them into text, only while this is on."),
    ("discord", "Discord messages",
     "Read DMs aloud and reply by voice, from Windows pop-ups. Nothing leaves your PC."),
    ("briefing", "Weather and news when I open the app",
     "Says the weather and top headlines out loud at start-up (needs internet)."),
    ("tray", "Keep running in the tray",
     "Closing the window keeps voice commands and warnings working."),
]


class SetupDialog(ctk.CTkToplevel):
    def __init__(self, app, on_done):
        super().__init__(app)
        self.app, self._on_done = app, on_done
        self.title("Set up Command Center")
        self.geometry("620x600")
        self.minsize(560, 560)
        self.configure(fg_color=theme.BG)
        self.transient(app)
        self.protocol("WM_DELETE_WINDOW", self._skip)
        self.vars = {key: ctk.BooleanVar(value=key == "tray")
                     for key, _t, _d in CHOICES}

        self.heading = label(self, "Welcome", 22, True)
        self.heading.pack(anchor="w", padx=30, pady=(26, 4))
        self.sub = label(self, "", 12, False, theme.TEXT_SOFT, wraplength=560, justify="left")
        self.sub.pack(anchor="w", padx=30, pady=(0, 10))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=30)
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=30, pady=22)
        self.next = ctk.CTkButton(footer, text="Set it up", width=130, height=38,
                                  corner_radius=10, font=font(12, True), command=self._apply)
        theme.bind(self.next, fg_color="main", hover_color="hover")
        self.next.pack(side="right")
        self.skip = ctk.CTkButton(footer, text="Skip for now", width=100, height=38,
                                  corner_radius=10, fg_color="transparent",
                                  hover_color=theme.HOVER, text_color=theme.MUTED,
                                  command=self._skip)
        self.skip.pack(side="left")
        self._choices_page()
        self.after(120, lambda: (self.lift(), self.focus_force()))

    def _clear(self):
        for child in self.body.winfo_children():
            child.destroy()

    def _choices_page(self):
        self.heading.configure(text="Welcome to Command Center")
        self.sub.configure(text="Choose what you'd like. You can change any of this later "
                                "in Settings and Voice Control.")
        self._clear()
        for key, title, text in CHOICES:
            row = ctk.CTkFrame(self.body, fg_color=theme.CARD, corner_radius=12,
                               border_width=1, border_color=theme.BORDER)
            row.pack(fill="x", pady=5)
            switch = ctk.CTkSwitch(row, text="", variable=self.vars[key], fg_color=theme.TRACK)
            theme.bind(switch, progress_color="main")
            switch.pack(side="right", padx=14)
            box = ctk.CTkFrame(row, fg_color="transparent")
            box.pack(side="left", fill="x", expand=True, padx=14, pady=10)
            label(box, title, 12, True).pack(anchor="w")
            label(box, text, 10, False, theme.MUTED, wraplength=400,
                  justify="left").pack(anchor="w")

    def _apply(self):
        chosen = {key: bool(var.get()) for key, var in self.vars.items()}
        self.app.apply_setup(chosen)
        self._results_page(chosen)

    def _results_page(self, chosen):
        self.heading.configure(text="All set")
        self.sub.configure(text="Here's what works right now:")
        self._clear()
        for state, text in self._report(chosen):
            colour = {"ok": theme.OK, "bad": theme.DANGER}.get(state, theme.MUTED)
            mark = {"ok": "✓", "bad": "✗"}.get(state, "•")
            row = ctk.CTkFrame(self.body, fg_color="transparent")
            row.pack(fill="x", pady=4)
            label(row, mark, 14, True, colour).pack(side="left", anchor="n", padx=(0, 10))
            label(row, text, 11, False, theme.TEXT_SOFT, wraplength=480,
                  justify="left").pack(side="left", anchor="w")
        self.next.configure(text="Finish", command=self._finish)
        self.skip.configure(text="")

    @staticmethod
    def _report(chosen):
        out = []
        if chosen["voice"]:
            missing = voice.missing_packages()
            out.append(("bad", "Voice needs:  py -m pip install " + " ".join(missing))
                       if missing else
                       ("ok", "Voice commands are on. Press Ctrl+Alt+V and say “what time is it”."))
        if chosen["discord"]:
            problem = discord_dm.package_problem()
            out.append(("bad", problem) if problem else
                       ("ok", "Discord DMs are on. Open the Voice Control page and press "
                              "“Check setup” once to confirm Windows allows it."))
        if chosen["briefing"]:
            out.append(("ok", "You'll hear the weather and news next time you start the app."))
        if chosen["tray"]:
            out.append(("ok", "Closing the window keeps it running in the tray."))
        if not any(chosen.values()):
            out.append(("info", "Nothing switched on. Use Settings any time."))
        return out

    def _finish(self):
        callback, self._on_done = self._on_done, None
        if callback:
            callback()
        self.destroy()

    def _skip(self):
        self._finish()
