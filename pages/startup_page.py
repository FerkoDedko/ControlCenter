import customtkinter as ctk

from core import startup, theme
from core.utils import reveal_in_folder, shorten
from core.widgets import card, font, label
from .base import BasePage


class StartupPage(BasePage):
    def __init__(self, master, toast=None):
        super().__init__(master, toast)
        actions = self.header("Startup Manager",
                              "Choose which programs start when you sign in to Windows")
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                             corner_radius=0)

        if not startup.supported():
            self.scroll.pack(fill="both", expand=True)
            note = card(self.scroll)
            note.pack(fill="x", padx=34, pady=10)
            label(note, "Windows only", 13, True).pack(anchor="w", padx=20, pady=(18, 4))
            label(note, "The Startup Manager reads the Windows registry, so it only "
                  "works on Windows. Run Command Center on a Windows PC to use it.",
                  10, False, theme.MUTED, wraplength=640, justify="left").pack(
                anchor="w", padx=20, pady=(0, 18))
            return

        refresh = ctk.CTkButton(actions, text="Refresh", width=100, height=36,
                                corner_radius=10, font=font(12, True),
                                command=self.reload)
        theme.bind(refresh, fg_color="main", hover_color="hover")
        refresh.pack()

        self.summary = label(self, "", 10, False, theme.MUTED)
        self.summary.pack(anchor="w", padx=36, pady=(0, 6))
        self.scroll.pack(fill="both", expand=True)
        self._entries = []
        self.reload()

    # ---- list ---------------------------------------------------------------
    def reload(self):
        for child in self.scroll.winfo_children():
            child.destroy()
        self._entries = startup.list_entries()
        enabled = sum(1 for e in self._entries if e.enabled)
        self.summary.configure(
            text=f"{enabled} of {len(self._entries)} startup items are on. "
                 "Switching one off keeps it listed, so you can turn it back on. "
                 "Changes take effect the next time you sign in.")

        if not self._entries:
            label(self.scroll, "No startup programs found.", 11, False,
                  theme.MUTED).pack(anchor="w", padx=36, pady=10)
            return
        for entry in self._entries:
            self._row(entry)

    def _row(self, entry):
        row = card(self.scroll, corner_radius=12)
        row.pack(fill="x", padx=34, pady=5)

        text = ctk.CTkFrame(row, fg_color="transparent")
        text.pack(side="left", fill="x", expand=True, padx=16, pady=12)
        top = ctk.CTkFrame(text, fg_color="transparent")
        top.pack(anchor="w")
        label(top, shorten(entry.name, 40), 11, True).pack(side="left")
        label(top, entry.source, 9, True, theme.MUTED, fg_color=theme.INPUT,
              corner_radius=8, height=20).pack(side="left", padx=10)
        label(text, shorten(entry.command, 70), 9, False, theme.MUTED).pack(
            anchor="w", pady=(3, 0))

        var = ctk.BooleanVar(value=entry.enabled)
        switch = ctk.CTkSwitch(row, text="", variable=var, onvalue=True,
                               offvalue=False, fg_color=theme.TRACK)
        switch.configure(command=lambda e=entry, v=var: self._toggle(e, v))
        theme.bind(switch, progress_color="main")
        switch.pack(side="right", padx=18)

        ctk.CTkButton(row, text="📂", width=34, height=30, fg_color="transparent",
                      hover_color=theme.HOVER, text_color=theme.TEXT_SOFT,
                      command=lambda e=entry: self._reveal(e)).pack(
            side="right", padx=(0, 4))

    # ---- actions ------------------------------------------------------------
    def _toggle(self, entry, var):
        wanted = bool(var.get())
        try:
            startup.set_enabled(entry, wanted)
        except OSError as exc:
            var.set(not wanted)          # put the switch back
            self.toast("Couldn't change it", f"Windows refused: {exc}", "error")
            return
        verb = "will start" if wanted else "won't start"
        self.toast("Saved", f"{entry.name} {verb} with Windows. Task Manager only "
                            "shows this after you close and reopen it.", "info")
        self.reload()          # show what Windows really has now

    def _reveal(self, entry):
        target = entry.command if entry.kind.endswith("folder") \
            else startup.executable_of(entry.command)
        try:
            reveal_in_folder(target)
        except OSError as exc:
            self.toast("Couldn't open the folder", str(exc), "error")
