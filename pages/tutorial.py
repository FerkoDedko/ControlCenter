"""A short guided tour: shown the first time the app starts, and from the sidebar."""
import customtkinter as ctk

from core import theme
from core.widgets import font, label

# (title, text, [(button text, page to open)])
STEPS = [
    ("Welcome to Command Center",
     "It watches your PC and lets you control it with your voice.\n\n"
     "This quick tour takes about two minutes. You can open it again any time with the "
     "“How to use” button at the bottom of the menu.",
     []),
    ("What's on each page",
     "Dashboard: live CPU, memory, disk and network, plus warnings.\n"
     "Processes: see what is running and end a program.\n"
     "Storage: what is using your disk, as cards (games, photos, videos…).\n"
     "Network and Hardware: traffic, temperatures and your graphics card.\n"
     "Cleanup: free up space safely.\n"
     "App Launcher: open several programs with one click.\n"
     "Startup Manager: choose what starts with Windows.\n"
     "Voice Control: do things by talking.\n"
     "Settings: theme, colours, animations, tray and shortcuts.",
     [("Open the Dashboard", "Dashboard")]),
    ("Your first voice command",
     "1. Open Voice Control and switch on the online speech option "
     "(voice recognition uses Google's service, so it needs internet).\n"
     "2. Press “New command”, choose “Start from an example…” and pick “Open Spotify”.\n"
     "3. Press Save.\n"
     "4. Press the microphone (or Ctrl+Alt+V) and say “open spotify”.\n\n"
     "If it doesn't understand you, look at the “Heard:” line to see what it heard, and "
     "add that wording to the command with a “|”, like  open spotify | open spotty.\n"
     "Want ready-made ones? Press “Add preset pack” for “what time is it”, "
     "“what's the weather”, “what's the news”, “how's my pc”, volume, lock and more.\n"
     "Put a word in {curly brackets}, like  play {song} on spotify, and whatever you say "
     "there is used in the steps.",
     [("Open Voice Control", "Voice Control")]),
    ("Discord messages",
     "Command Center can read Discord DMs aloud and reply for you, without any bot or "
     "login details. It works from the Windows pop-ups Discord shows.\n\n"
     "1. In Voice Control, find the Discord card and switch on “Listen for new Discord DMs”.\n"
     "2. Press “Check setup”. It shows a ✓ or ✗ for each thing that has to work, and says "
     "what to fix.\n"
     "3. Press “Add the Read & Reply commands”. Now say “read my message”, or "
     "“reply I'll be there in five”.\n"
     "4. Try “Send a test message” on a friend first.\n\n"
     "Auto-Busy answers for you when you're on a call, in a fullscreen game, have a "
     "program open that you picked, or switched “busy” on yourself.",
     [("Open Voice Control", "Voice Control")]),
    ("Tray and shortcuts",
     "Ctrl+Alt+C shows or hides the window. Ctrl+Alt+V starts listening for a voice "
     "command.\n\n"
     "Closing the window can keep Command Center running in the tray, so voice commands "
     "and warnings keep working. You can change the shortcuts and this behaviour in "
     "Settings.",
     [("Open Settings", "Settings")]),
    ("You're ready",
     "That's it. If something looks cut off or doesn't work, tell the person who gave "
     "you this app, with a screenshot.\n\n"
     "Tip: Settings → Appearance has a switch for every animation if you'd like it calmer "
     "or faster.",
     []),
]


class TutorialDialog(ctk.CTkToplevel):
    def __init__(self, app, on_close=None):
        super().__init__(app)
        self.app = app
        self._on_close = on_close
        self._index = 0
        self.title("How to use Command Center")
        self.geometry("620x560")
        self.minsize(560, 520)
        self.configure(fg_color=theme.BG)
        self.transient(app)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.step_label = label(self, "", 10, True, theme.MUTED)
        self.step_label.pack(anchor="w", padx=30, pady=(26, 0))
        self.heading = label(self, "", 22, True, wraplength=560, justify="left")
        self.heading.pack(anchor="w", padx=30, pady=(4, 12))
        self.body = label(self, "", 12, False, theme.TEXT_SOFT, wraplength=560,
                          justify="left")
        self.body.pack(anchor="w", padx=30)

        self.actions = ctk.CTkFrame(self, fg_color="transparent")
        self.actions.pack(anchor="w", padx=30, pady=(16, 0))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(side="bottom", fill="x", padx=30, pady=22)
        self.next_button = ctk.CTkButton(footer, text="Next", width=110, height=38,
                                         corner_radius=10, font=font(12, True),
                                         command=self._next)
        theme.bind(self.next_button, fg_color="main", hover_color="hover")
        self.next_button.pack(side="right")
        self.back_button = ctk.CTkButton(footer, text="Back", width=90, height=38,
                                         corner_radius=10, fg_color=theme.INPUT,
                                         hover_color=theme.HOVER, text_color=theme.TEXT,
                                         command=self._back)
        self.back_button.pack(side="right", padx=8)
        self.skip_button = ctk.CTkButton(footer, text="Skip", width=70, height=38,
                                         corner_radius=10, fg_color="transparent",
                                         hover_color=theme.HOVER, text_color=theme.MUTED,
                                         command=self.close)
        self.skip_button.pack(side="left")
        self._show()
        self.after(120, self._raise)

    def _raise(self):
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _show(self):
        title, text, buttons = STEPS[self._index]
        last = self._index == len(STEPS) - 1
        self.step_label.configure(text=f"STEP {self._index + 1} OF {len(STEPS)}")
        self.heading.configure(text=title)
        self.body.configure(text=text)
        for child in self.actions.winfo_children():
            child.destroy()
        for caption, page in buttons:
            button = ctk.CTkButton(
                self.actions, text=caption, height=34, corner_radius=8,
                fg_color=theme.INPUT, hover_color=theme.HOVER, text_color=theme.TEXT,
                command=lambda p=page: self.app.show_page(p))
            button.pack(side="left", padx=(0, 8))
        self.next_button.configure(text="Finish" if last else "Next")
        self.back_button.configure(state="disabled" if self._index == 0 else "normal")
        self.skip_button.configure(text="" if last else "Skip")

    def _next(self):
        if self._index >= len(STEPS) - 1:
            self.close()
        else:
            self._index += 1
            self._show()

    def _back(self):
        if self._index:
            self._index -= 1
            self._show()

    def close(self):
        callback, self._on_close = self._on_close, None
        if callback:
            callback()
        self.destroy()
