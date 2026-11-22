import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from core import anim, discord_dm, theme, voice
from core.config import DATA_DIR, load_json, save_json
from core.utils import shorten
from core.widgets import card, font, label
from .base import BasePage

VOICE_PATH = DATA_DIR / "voice.json"
MODES = {"Push to talk": "push", "Always listening": "always"}

STEP_TYPES = {
    "Open a program or file": "program",
    "Open a website": "website",
    "Spotify: search for a song": "spotify_search",
    "Spotify: open a song link and play it": "spotify_play",
    "Media key (play, volume…)": "media",
    "Wait a few seconds": "wait",
    "Show a message": "toast",
    "Say something out loud": "speak",
    "Lock the PC": "lock",
    "Discord: read the latest DM out loud": "discord_read",
    "Discord: reply to the latest DM": "discord_reply",
}
STEP_LABELS = {kind: label_text for label_text, kind in STEP_TYPES.items()}
HINTS = {
    "program": "Pick a program or file with Browse",
    "website": "for example: youtube.com",
    "spotify_search": "a song name, or {song} to use what you say",
    "spotify_play": "paste the song link (Share → Copy Song Link)",
    "wait": "seconds, for example: 3",
    "toast": "the message to show",
    "speak": "what to say. Built in: {time} {date} {weather} {news} {cpu} {memory} {disk} {battery}",
    "discord_reply": "what to send, for example {message}  (the words you say after “reply”)",
}
NO_VALUE = ("discord_read", "lock")      # steps with nothing to fill in
NOTES = {"discord_read": "Reads it out loud. Nothing to fill in.",
         "lock": "Locks Windows. Nothing to fill in."}
MEDIA_BY_KEY = {key: name for name, key in voice.MEDIA_LABELS.items()}

# name -> (phrase you say, steps)
EXAMPLES = {
    "Open Spotify": ("open spotify", [("program", "spotify:")]),
    "Say a song, search it on Spotify": (
        "play {song} on spotify",
        [("spotify_search", "{song}"), ("toast", "Searching Spotify for {song}")]),
    "Play one specific Spotify song": (
        "play my song",
        [("spotify_play", "https://open.spotify.com/track/PASTE_THE_SONG_ID_HERE")]),
    "Pause / resume music": ("pause the music", [("media", "play_pause")]),
    "Open a website": ("open youtube", [("website", "youtube.com")]),
    "Open a program": ("open notepad", [("program", "notepad.exe")]),
    "Read my latest Discord DM": (
        "read my message | read my discord message", [("discord_read", "")]),
    "Reply to my latest Discord DM": (
        "reply {message}", [("discord_reply", "{message}")]),
    # ---- ready-made presets (the "Add preset pack" button adds PRESET_PACK) ----
    "What time is it": ("what time is it | what's the time | tell me the time",
                        [("speak", "It's {time}")]),
    "What's the date": ("what's the date | what day is it | what's today",
                        [("speak", "Today is {date}")]),
    "What's the weather": ("what's the weather | how's the weather | weather",
                           [("speak", "{weather}")]),
    "What's the news": ("what's the news | tell me the news | news | headlines",
                        [("speak", "{news}")]),
    "PC status": ("how's my pc | pc status | system status",
                  [("speak", "CPU is at {cpu}, memory is at {memory}, "
                             "and your main disk is {disk} full.")]),
    "Battery level": ("battery | how's my battery | battery level",
                      [("speak", "Battery: {battery}")]),
    "Volume up": ("volume up | louder", [("media", "volume_up"), ("media", "volume_up"),
                                         ("media", "volume_up")]),
    "Volume down": ("volume down | quieter", [("media", "volume_down"), ("media", "volume_down"),
                                              ("media", "volume_down")]),
    "Mute": ("mute | unmute", [("media", "mute")]),
    "Next song": ("next song | skip | next track", [("media", "next")]),
    "Previous song": ("previous song | go back | last song", [("media", "previous")]),
    "Lock my PC": ("lock my pc | lock the computer | lock screen", [("lock", "")]),
    "Take a screenshot": ("take a screenshot | screenshot", [("program", "ms-screenclip:")]),
    "Open Windows Settings": ("open settings | open windows settings",
                              [("program", "ms-settings:")]),
    "Open Task Manager": ("open task manager", [("program", "taskmgr.exe")]),
}
PRESET_PACK = ("What time is it", "What's the date", "What's the weather", "What's the news",
               "PC status",
               "Battery level", "Volume up", "Volume down", "Mute", "Next song",
               "Previous song", "Lock my PC", "Take a screenshot", "Open Windows Settings",
               "Open Task Manager")



class StepRow(ctk.CTkFrame):
    """One step: pick an action, fill in one box."""

    def __init__(self, master, number, on_remove, kind="program", value=""):
        super().__init__(master, fg_color=theme.CARD, corner_radius=10,
                         border_width=1, border_color=theme.BORDER)
        self.number = label(self, str(number), 11, True, theme.MUTED, width=22)
        self.number.pack(side="left", padx=(10, 4), pady=10)

        self.type_var = ctk.StringVar(value=STEP_LABELS[kind])
        menu = ctk.CTkOptionMenu(
            self, values=list(STEP_TYPES), variable=self.type_var, width=250, height=32,
            fg_color=theme.INPUT, text_color=theme.TEXT, dropdown_fg_color=theme.CARD,
            dropdown_text_color=theme.TEXT, dropdown_hover_color=theme.HOVER,
            command=lambda _v: self._retype())
        theme.bind(menu, button_color="main", button_hover_color="hover")
        menu.pack(side="left", padx=4)

        ctk.CTkButton(self, text="✕", width=30, height=30, fg_color="transparent",
                      hover_color=theme.HOVER, text_color=theme.MUTED,
                      command=lambda: on_remove(self)).pack(side="right", padx=(0, 8))
        self.browse = ctk.CTkButton(self, text="Browse", width=70, height=32, corner_radius=8,
                                    fg_color=theme.INPUT, hover_color=theme.HOVER,
                                    text_color=theme.TEXT, command=self._browse)
        self.entry = ctk.CTkEntry(self, height=32, corner_radius=8, fg_color=theme.INPUT,
                                  border_width=0, text_color=theme.TEXT)
        self.note = label(self, NOTES["discord_read"], 10, False, theme.MUTED)
        self.media_var = ctk.StringVar(value="Play / pause")
        self.media_menu = ctk.CTkOptionMenu(
            self, values=list(voice.MEDIA_LABELS), variable=self.media_var, height=32,
            fg_color=theme.INPUT, text_color=theme.TEXT, dropdown_fg_color=theme.CARD,
            dropdown_text_color=theme.TEXT, dropdown_hover_color=theme.HOVER)
        theme.bind(self.media_menu, button_color="main", button_hover_color="hover")
        self.set(kind, value)

    @property
    def kind(self):
        return STEP_TYPES[self.type_var.get()]

    def _retype(self):
        kind = self.kind
        for widget in (self.browse, self.entry, self.media_menu, self.note):
            widget.pack_forget()
        if kind in NO_VALUE:
            self.note.configure(text=NOTES[kind])
            self.note.pack(side="left", padx=8)
        elif kind == "media":
            self.media_menu.pack(side="left", fill="x", expand=True, padx=4)
        else:
            if kind == "program":
                self.browse.pack(side="right", padx=(0, 4))
            self.entry.configure(placeholder_text=HINTS[kind])
            self.entry.pack(side="left", fill="x", expand=True, padx=4)

    def set(self, kind, value):
        self.type_var.set(STEP_LABELS[kind])
        self.entry.delete(0, "end")
        if kind == "media":
            self.media_var.set(MEDIA_BY_KEY.get(value, "Play / pause"))
        elif kind not in NO_VALUE:
            self.entry.insert(0, value)
        self._retype()

    def get(self):
        kind = self.kind
        if kind == "media":
            return kind, voice.MEDIA_LABELS[self.media_var.get()]
        if kind in NO_VALUE:
            return kind, ""
        return kind, self.entry.get().strip()

    def renumber(self, number):
        self.number.configure(text=str(number))

    def _browse(self):
        chosen = filedialog.askopenfilename(parent=self.winfo_toplevel(),
                                            title="Choose a program or file")
        if chosen:
            self.entry.delete(0, "end")
            self.entry.insert(0, chosen)


class CommandDialog(ctk.CTkToplevel):
    def __init__(self, page, command, on_save):
        super().__init__(page)
        self.page = page
        self.on_save = on_save
        self._events = queue.Queue()
        self._listener = voice.VoiceListener(lambda kind, text: self._events.put((kind, text)))
        self._rows = []
        self.title("Edit voice command" if command else "New voice command")
        self.geometry("720x700")
        self.configure(fg_color=theme.BG)
        self.transient(page.winfo_toplevel())

        label(self, "Edit voice command" if command else "New voice command", 18, True).pack(
            anchor="w", padx=24, pady=(20, 6))
        picker = ctk.CTkOptionMenu(
            self, values=list(EXAMPLES), width=300, height=32, fg_color=theme.INPUT,
            text_color=theme.TEXT, dropdown_fg_color=theme.CARD,
            dropdown_text_color=theme.TEXT, dropdown_hover_color=theme.HOVER,
            command=self._use_example)
        theme.bind(picker, button_color="main", button_hover_color="hover")
        picker.set("Start from an example…")
        picker.pack(anchor="w", padx=24)

        label(self, "1.  When I say…", 11, True).pack(anchor="w", padx=24, pady=(16, 4))
        line = ctk.CTkFrame(self, fg_color="transparent")
        line.pack(fill="x", padx=24)
        self.phrase = ctk.CTkEntry(line, height=38, corner_radius=10, fg_color=theme.INPUT,
                                   border_width=0, text_color=theme.TEXT,
                                   placeholder_text="type it, or press the microphone and say it")
        self.phrase.pack(side="left", fill="x", expand=True)
        self.say_button = ctk.CTkButton(line, text="🎤  Say it", width=110, height=38,
                                        corner_radius=10, font=font(12, True),
                                        command=self._say)
        theme.bind(self.say_button, fg_color="main", hover_color="hover")
        self.say_button.pack(side="left", padx=(8, 0))
        label(self, "Tip: put a word in curly brackets, like  play {song} on spotify, "
                    "and whatever you say there is used in the steps.",
              9, False, theme.MUTED).pack(anchor="w", padx=24, pady=(4, 0))

        label(self, "2.  …do this", 11, True).pack(anchor="w", padx=24, pady=(16, 4))
        self.steps_area = ctk.CTkScrollableFrame(self, fg_color="transparent", height=230,
                                                 corner_radius=0)
        self.steps_area.pack(fill="x", padx=18)
        add = ctk.CTkButton(self, text="+  Add another step", width=170, height=32,
                            corner_radius=8, fg_color=theme.INPUT, hover_color=theme.HOVER,
                            text_color=theme.TEXT, command=lambda: self._add_row())
        add.pack(anchor="w", padx=24, pady=(8, 0))

        self.error = label(self, "", 10, False, theme.DANGER, wraplength=660, justify="left")
        self.error.pack(anchor="w", padx=24, pady=(10, 0))
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=24, pady=14, side="bottom")
        save = ctk.CTkButton(footer, text="Save", width=110, height=38, corner_radius=10,
                             font=font(12, True), command=self._save)
        theme.bind(save, fg_color="main", hover_color="hover")
        save.pack(side="right")
        ctk.CTkButton(footer, text="Cancel", width=100, height=38, corner_radius=10,
                      fg_color=theme.INPUT, hover_color=theme.HOVER, text_color=theme.TEXT,
                      command=self.destroy).pack(side="right", padx=8)

        if command:
            self.phrase.insert(0, command["phrase"])
            try:
                for kind, value in voice.text_to_rows(command["steps"]):
                    self._add_row(kind, value)
            except ValueError:
                self._add_row()
        else:
            self._add_row()
        self.after(150, self._focus)

    def _focus(self):
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
        except Exception:
            pass

    # ---- steps ------------------------------------------------------------------------
    def _add_row(self, kind="program", value=""):
        row = StepRow(self.steps_area, len(self._rows) + 1, self._remove_row, kind, value)
        row.pack(fill="x", pady=4, padx=6)
        self._rows.append(row)

    def _remove_row(self, row):
        self._rows.remove(row)
        row.destroy()
        for number, remaining in enumerate(self._rows, start=1):
            remaining.renumber(number)

    def _use_example(self, name):
        phrase, rows = EXAMPLES[name]
        self.phrase.delete(0, "end")
        self.phrase.insert(0, phrase)
        for row in list(self._rows):
            self._remove_row(row)
        for kind, value in rows:
            self._add_row(kind, value)

    # ---- say the phrase out loud -----------------------------------------------------------
    def _say(self):
        reason = self.page._blocker()
        if reason is None and self.page.listener.running:
            reason = "Stop the microphone on the main page first."
        if reason:
            self.error.configure(text=reason)
            return
        self.error.configure(text="")
        self.say_button.configure(text="Listening…", state="disabled")
        self._listener.start(voice.LANGUAGES.get(self.page.lang_var.get(), "en-US"),
                             continuous=False)
        self._poll()

    def _poll(self):
        try:
            while True:
                kind, text = self._events.get_nowait()
                if kind == "heard" and text:
                    self.phrase.delete(0, "end")
                    self.phrase.insert(0, text.lower())
                elif kind == "heard":
                    self.error.configure(text="Didn't catch that. Press the microphone and try again.")
                elif kind == "error":
                    self.error.configure(text=text)
                elif kind == "stopped":
                    self.say_button.configure(text="🎤  Say it", state="normal")
        except queue.Empty:
            pass
        if self._listener.running or not self._events.empty():
            self.after(200, self._poll)
        else:
            self.say_button.configure(text="🎤  Say it", state="normal")

    def destroy(self):
        self._listener.stop()
        super().destroy()

    # ---- saving ---------------------------------------------------------------------------
    def _save(self):
        phrase = self.phrase.get().strip()
        try:
            steps = voice.rows_to_text([row.get() for row in self._rows])
            voice.validate_command(phrase, steps)
        except ValueError as exc:
            self.error.configure(text=str(exc))
            return
        self.on_save({"phrase": phrase, "steps": steps})
        self.destroy()


class VoicePage(BasePage):
    FOLLOW_UP_SECONDS = 8
    _armed_until = 0.0        # after the wake word (or a command) you can talk without it

    def __init__(self, master, config, save_callback, toast=None):
        super().__init__(master, toast)
        self.config_data = config
        self.save_callback = save_callback
        data = load_json(VOICE_PATH, [])
        self.commands = [c for c in data if isinstance(c, dict)
                         and c.get("phrase") and c.get("steps")] if isinstance(data, list) else []
        self._events = queue.Queue()
        self.listener = voice.VoiceListener(lambda kind, text: self._events.put((kind, text)))
        self._pulse_level = 0.0
        self._pulsing = False

        actions = self.header("Voice Control", "Say a phrase and Command Center does the rest")
        add = ctk.CTkButton(actions, text="+  New command", width=150, height=36,
                            corner_radius=10, font=font(12, True),
                            command=lambda: self._open_dialog(None))
        theme.bind(add, fg_color="main", hover_color="hover")
        add.pack(side="right")
        presets = ctk.CTkButton(actions, text="Add preset pack", width=140, height=36,
                                corner_radius=10, font=font(12, True), fg_color=theme.INPUT,
                                hover_color=theme.HOVER, text_color=theme.TEXT,
                                command=self._add_presets)
        presets.pack(side="right", padx=(0, 8))

        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self.scroll.pack(fill="both", expand=True)
        self._build_controls()
        self._build_discord()
        self.list_area = ctk.CTkFrame(self.scroll, fg_color="transparent")
        self.list_area.pack(fill="x")
        self._render_commands()
        self._build_notes()
        self.after(200, self._poll)

    # ---- controls ------------------------------------------------------------------
    def _value(self, key, default):
        return self.config_data.get(key, default)

    def _build_controls(self):
        panel = card(self.scroll)
        panel.pack(fill="x", padx=34, pady=(0, 14))

        top = ctk.CTkFrame(panel, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(18, 6))
        self.mic_button = ctk.CTkButton(top, text="🎤  Talk", width=170, height=48,
                                        corner_radius=24, font=font(14, True),
                                        command=self._mic_clicked)
        theme.bind(self.mic_button, fg_color="main", hover_color="hover")
        self.mic_button.pack(side="left")
        info = ctk.CTkFrame(top, fg_color="transparent")
        info.pack(side="left", padx=18)
        self.status = label(info, "Ready", 12, True)
        self.status.pack(anchor="w")
        self.heard = label(info, "", 10, False, theme.MUTED)
        self.heard.pack(anchor="w", pady=(2, 0))

        options = ctk.CTkFrame(panel, fg_color="transparent")
        options.pack(fill="x", padx=20, pady=(8, 4))
        self.mode_var = ctk.StringVar(value=next(
            (n for n, v in MODES.items() if v == self._value("voice_mode", "push")),
            "Push to talk"))
        self._menu(options, "Mode", list(MODES), self.mode_var, self._mode_changed)
        self.lang_var = ctk.StringVar(value=next(
            (n for n, c in voice.LANGUAGES.items() if c == self._value("voice_language", "en-US")),
            "English (US)"))
        self._menu(options, "Language", list(voice.LANGUAGES), self.lang_var, self._save_options)

        wake = ctk.CTkFrame(options, fg_color="transparent")
        wake.pack(side="left", padx=(0, 10))
        label(wake, "Wake word(s), comma separated (always-listening only)", 9, False, theme.MUTED).pack(anchor="w")
        self.wake_entry = ctk.CTkEntry(wake, width=200, height=32, corner_radius=8,
                                       fg_color=theme.INPUT, border_width=0,
                                       text_color=theme.TEXT, placeholder_text="e.g. computer")
        self.wake_entry.insert(0, self._value("voice_wake_word", ""))
        self.wake_entry.pack(anchor="w", pady=(2, 0))
        self.wake_entry.bind("<FocusOut>", lambda _e: self._save_options())
        self.wake_entry.bind("<Return>", lambda _e: self._save_options())

        consent = ctk.CTkFrame(panel, fg_color="transparent")
        consent.pack(fill="x", padx=20, pady=(10, 18))
        self.consent_var = ctk.BooleanVar(value=bool(self._value("voice_consent", False)))
        switch = ctk.CTkSwitch(consent, text="", variable=self.consent_var,
                               fg_color=theme.TRACK, command=self._save_options)
        theme.bind(switch, progress_color="main")
        switch.pack(side="left")
        label(consent, "Allow voice recognition. Short recordings of what you say are sent to "
                       "Google's speech service to turn them into text. Nothing is sent while "
                       "this is off.", 10, False, theme.TEXT_SOFT, wraplength=720,
              justify="left").pack(side="left", padx=12)

        missing = voice.missing_packages()
        if missing:
            label(panel, "Voice needs two extra packages. In your project terminal run:\n"
                         "    py -m pip install " + " ".join(missing),
                  10, True, theme.WARN, justify="left").pack(anchor="w", padx=20, pady=(0, 16))


    # ---- Discord DMs (read from Windows notifications, no bot / API / token) ------------------
    def _build_discord(self):
        panel = card(self.scroll)
        panel.pack(fill="x", padx=34, pady=(0, 14))
        label(panel, "DISCORD DMs", 10, True, theme.MUTED).pack(anchor="w", padx=20, pady=(16, 2))
        label(panel, "Reads Discord's Windows pop-ups and replies by pressing keys in the "
                     "Discord app. No bot, no Discord login details. Only direct messages "
                     "count, not servers or group chats.", 10, False, theme.TEXT_SOFT,
              wraplength=760, justify="left").pack(anchor="w", padx=20, pady=(0, 8))

        self._dc_vars = {}

        def switch_row(key, default, text, bold=False):
            var = ctk.BooleanVar(value=bool(self._value(key, default)))
            self._dc_vars[key] = var
            row = ctk.CTkFrame(panel, fg_color="transparent")
            row.pack(fill="x", padx=20, pady=3)
            switch = ctk.CTkSwitch(row, text="", variable=var, fg_color=theme.TRACK,
                                   command=self._save_discord)
            theme.bind(switch, progress_color="main")
            switch.pack(side="left")
            label(row, text, 10, bold, theme.TEXT, wraplength=700, wrap_margin=90,
                  justify="left").pack(side="left", padx=12)

        switch_row("discord_enabled", False, "Listen for new Discord DMs", True)
        switch_row("discord_auto_busy", False,
                   "Auto-Busy: reply to a DM for me when I'm busy (once per person every "
                   "5 minutes)", True)
        label(panel, "I count as busy when…", 10, True, theme.MUTED).pack(
            anchor="w", padx=20, pady=(10, 0))
        switch_row("discord_busy_in_call", True, "I'm on a Discord call")
        switch_row("discord_busy_fullscreen", False,
                   "A game or video is fullscreen")
        switch_row("discord_busy_manual", False,
                   "I switched “busy” on myself (stays on until I switch it off)")

        label(panel, "…or any of these programs is open", 10, False, theme.TEXT).pack(
            anchor="w", padx=20, pady=(8, 2))
        self._busy_apps = [str(a) for a in (self._value("discord_busy_apps", []) or [])]
        self.dc_chips = ctk.CTkFrame(panel, fg_color="transparent")
        self.dc_chips.pack(fill="x", padx=20)
        buttons = ctk.CTkFrame(panel, fg_color="transparent")
        buttons.pack(fill="x", padx=20, pady=(4, 2))
        for text, command in (("＋  Add a running program", self._pick_running_app),
                              ("Browse for a program…", self._browse_app)):
            ctk.CTkButton(buttons, text=text, height=30, corner_radius=8, fg_color=theme.INPUT,
                          hover_color=theme.HOVER, text_color=theme.TEXT,
                          command=command).pack(side="left", padx=(0, 8))
        switch_row("discord_busy_apps_active_only", False,
                   "Only count those programs while I'm using their window")
        self._render_chips()

        message = ctk.CTkFrame(panel, fg_color="transparent")
        message.pack(fill="x", padx=20, pady=(8, 4))
        label(message, "Busy message", 9, False, theme.MUTED).pack(anchor="w")
        self.dc_message = ctk.CTkEntry(message, height=34, corner_radius=8, fg_color=theme.INPUT,
                                       border_width=0, text_color=theme.TEXT)
        self.dc_message.insert(0, self._value("discord_busy_message",
                                              "Hey, this person is busy right now!"))
        self.dc_message.pack(fill="x", pady=(2, 0))
        self.dc_message.bind("<FocusOut>", lambda _e: self._save_discord())
        self.dc_message.bind("<Return>", lambda _e: self._save_discord())


        # ---- set it up, check it, try it ---------------------------------------------------
        label(panel, "Set it up and check it works", 10, True, theme.MUTED).pack(
            anchor="w", padx=20, pady=(14, 0))
        label(panel, "1. Switch on “Listen for new Discord DMs”.   2. Press “Check setup”.   "
                     "3. Press “Add the Read & Reply commands” — then say your wake word (or "
                     "press the microphone) and “reply I'll be there in five”.   4. Try it on "
                     "a friend first with “Send a test message”.", 10, False, theme.TEXT_SOFT,
              wraplength=760, justify="left").pack(anchor="w", padx=20, pady=(2, 6))
        tools = ctk.CTkFrame(panel, fg_color="transparent")
        tools.pack(fill="x", padx=20)
        for text, command in (("Check setup", self._check_discord),
                              ("Show what the app sees", self._show_seen),
                              ("Add the Read & Reply commands", self._add_discord_commands)):
            button = ctk.CTkButton(tools, text=text, height=32, corner_radius=8,
                                   font=font(11, True), command=command)
            theme.bind(button, fg_color="main", hover_color="hover")
            button.pack(side="left", padx=(0, 8))
        self.dc_check_box = label(panel, "", 10, False, theme.TEXT, wraplength=760,
                                  justify="left")
        self.dc_check_box.pack(anchor="w", padx=20, pady=(6, 0))

        test = ctk.CTkFrame(panel, fg_color="transparent")
        test.pack(fill="x", padx=20, pady=(10, 0))
        self.dc_test_name = ctk.CTkEntry(test, width=190, height=32, corner_radius=8,
                                         fg_color=theme.INPUT, border_width=0,
                                         text_color=theme.TEXT,
                                         placeholder_text="their name, as on the pop-up")
        self.dc_test_name.pack(side="left")
        self.dc_test_text = ctk.CTkEntry(test, height=32, corner_radius=8, fg_color=theme.INPUT,
                                         border_width=0, text_color=theme.TEXT,
                                         placeholder_text="message to send")
        self.dc_test_text.insert(0, "Test message from Command Center")
        self.dc_test_text.pack(side="left", fill="x", expand=True, padx=8)
        ctk.CTkButton(test, text="Send a test message", height=32, corner_radius=8,
                      fg_color=theme.INPUT, hover_color=theme.HOVER, text_color=theme.TEXT,
                      command=self._send_discord_test).pack(side="left")

        self.dc_status = label(panel, "", 10, True, theme.MUTED, wraplength=760, justify="left")
        self.dc_status.pack(anchor="w", padx=20, pady=(8, 2))
        label(panel, "While a reply is being sent (about 3 seconds) Discord comes to the front "
                     "and keys are pressed for you, so don't type. Then you're taken back to "
                     "the window you were in. Windows must allow notification access "
                     "(Settings → Privacy & security → Notifications) and Discord's own "
                     "desktop notifications must be on.", 9, False, theme.MUTED,
              wraplength=760, justify="left").pack(anchor="w", padx=20, pady=(0, 16))
        self.dc_enabled = self._dc_vars["discord_enabled"]
        self._discord_status_tick()

    def _check_discord(self):
        self.dc_check_box.configure(text="Checking…")
        result = []
        threading.Thread(target=lambda: result.append(discord_dm.diagnose()),
                         daemon=True).start()

        def show():
            if not result:
                self.after(150, show)
                return
            marks = {"ok": "✓", "bad": "✗", "info": "•"}
            self.dc_check_box.configure(text="\n".join(
                f"{marks[state]}  {text}" for state, text in result[0]))

        show()

    def _show_seen(self):
        self.dc_check_box.configure(text=discord_dm.service().describe_log())

    def _add_examples(self, names):
        """Add the named EXAMPLES as commands. Returns the phrases that were new."""
        added = []
        for name in names:
            phrase, rows = EXAMPLES[name]
            steps = voice.rows_to_text(rows)
            if any(c["steps"] == steps and c["phrase"] == phrase for c in self.commands):
                continue
            self.commands.append({"phrase": phrase, "steps": steps})
            added.append(phrase.split("|")[0].strip())
        if added:
            self._store()
            self._render_commands()
        return added

    def _add_discord_commands(self):
        added = self._add_examples(("Read my latest Discord DM", "Reply to my latest Discord DM"))
        if added:
            self.toast("Commands added",
                       "Now say: " + "  ·  ".join(f"“{a}”" for a in added)
                       + ("  (reply + what to send)" if any(a.startswith("reply") for a in added)
                          else ""), "info")
        else:
            self.toast("Already there", "Both Discord commands are in your list.", "info")

    def _add_presets(self):
        added = self._add_examples(PRESET_PACK)
        if added:
            self.toast("Preset pack added",
                       f"{len(added)} commands, like “what time is it” and "
                       "“what's the weather”.", "info")
        else:
            self.toast("Already there", "The preset commands are already in your list.", "info")

    def _send_discord_test(self):
        name, text = self.dc_test_name.get().strip(), self.dc_test_text.get().strip()
        if not name or not text:
            self.toast("Fill both boxes", "Type their name and a message first.", "info")
            return
        if not messagebox.askyesno(
                "Send a test message",
                f"Discord will come to the front and send “{text}” to {name}.\n\n"
                "Don't type until it's done (about 3 seconds). Continue?",
                parent=self.winfo_toplevel()):
            return
        outcome = []

        def work():
            try:
                discord_dm.send_discord_dm(name, text)
                outcome.append(None)
            except OSError as exc:
                outcome.append(str(exc))

        threading.Thread(target=work, daemon=True).start()

        def done():
            if not outcome:
                self.after(200, done)
            elif outcome[0] is None:
                self.toast("Sent", f"Check your chat with {name}. If it went to the wrong "
                                   "person, type their name exactly as the pop-up shows it.",
                           "info")
            else:
                self.toast("Couldn't send", outcome[0], "error")

        done()

    def _render_chips(self):
        for child in self.dc_chips.winfo_children():
            child.destroy()
        for index, name in enumerate(self._busy_apps):
            chip = ctk.CTkFrame(self.dc_chips, fg_color=theme.INPUT, corner_radius=14)
            chip.grid(row=index // 4, column=index % 4, padx=(0, 6), pady=3, sticky="w")
            label(chip, name, 10, False, theme.TEXT).pack(side="left", padx=(12, 2), pady=3)
            ctk.CTkButton(chip, text="✕", width=22, height=22, corner_radius=11,
                          fg_color="transparent", hover_color=theme.HOVER,
                          text_color=theme.MUTED,
                          command=lambda n=name: self._remove_app(n)).pack(
                side="left", padx=(0, 4))
        if not self._busy_apps:
            label(self.dc_chips, "No programs added.", 9, False, theme.MUTED).grid(
                row=0, column=0, sticky="w")

    def _add_app(self, name):
        name = discord_dm.exe_name(name)
        if name and name not in [discord_dm.exe_name(a) for a in self._busy_apps]:
            self._busy_apps.append(name)
            self._render_chips()
            self._save_discord()

    def _remove_app(self, name):
        self._busy_apps = [a for a in self._busy_apps if a != name]
        self._render_chips()
        self._save_discord()

    def _pick_running_app(self):
        names = discord_dm.running_apps()
        if not names:
            self.toast("Nothing to pick", "I can only list open programs on Windows.", "info")
            return
        menu = tk.Menu(self, tearoff=0)
        for name in names:
            menu.add_command(label=name, command=lambda n=name: self._add_app(n))
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

    def _browse_app(self):
        chosen = filedialog.askopenfilename(parent=self.winfo_toplevel(),
                                            title="Choose a program",
                                            filetypes=[("Programs", "*.exe"), ("All files", "*.*")])
        if chosen:
            self._add_app(os.path.basename(chosen))

    def _save_discord(self):
        settings = {key: bool(var.get()) for key, var in self._dc_vars.items()}
        settings["discord_busy_apps"] = list(self._busy_apps)
        settings["discord_busy_message"] = (self.dc_message.get().strip()
                                            or "Hey, this person is busy right now!")
        self.save_callback(settings)

    def _discord_status_tick(self):
        service = discord_dm.service()
        if not self.dc_enabled.get():
            text = "Off"
        else:
            text = service.status
            latest = service.latest()
            if latest and service.status.startswith("Listening"):
                text += f"   ·   latest DM: {latest[0]}"
        self.dc_status.configure(text=text)
        self.after(1000, self._discord_status_tick)

    @staticmethod
    def _menu(parent, title, values, variable, command):
        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.pack(side="left", padx=(0, 14))
        label(box, title, 9, False, theme.MUTED).pack(anchor="w")
        menu = ctk.CTkOptionMenu(box, values=values, variable=variable, width=170, height=32,
                                 fg_color=theme.INPUT, text_color=theme.TEXT,
                                 dropdown_fg_color=theme.CARD, dropdown_text_color=theme.TEXT,
                                 dropdown_hover_color=theme.HOVER,
                                 command=lambda _v: command())
        theme.bind(menu, button_color="main", button_hover_color="hover")
        menu.pack(anchor="w", pady=(2, 0))

    def _build_notes(self):
        notes = card(self.scroll)
        notes.pack(fill="x", padx=34, pady=(4, 26))
        label(notes, "GOOD TO KNOW", 10, True, theme.MUTED).pack(anchor="w", padx=20, pady=(16, 6))
        text = (
            "•  Push to talk: click the button (or press your voice shortcut from Settings), "
            "say your phrase, done. Always listening keeps the microphone on and is best "
            "used with a wake word.\n"
            "•  Spotify can't be told to play a song by name from outside. "
            "“open spotify:search:{song}” opens the search results for what you said. "
            "To play one specific song, copy its link in Spotify (Share → Copy Song Link), "
            "then use  open <link>,  wait 4,  media play_pause.\n"
            "•  Phrases don't have to be perfect: close matches still work.\n"
            "•  Windows must allow desktop apps to use the microphone "
            "(Settings → Privacy → Microphone).")
        label(notes, text, 10, False, theme.TEXT_SOFT, wraplength=900,
              justify="left").pack(anchor="w", padx=20, pady=(0, 18))

    # ---- commands list ---------------------------------------------------------------
    def _render_commands(self):
        for child in self.list_area.winfo_children():
            child.destroy()
        label(self.list_area, "YOUR COMMANDS", 10, True, theme.MUTED).pack(
            anchor="w", padx=36, pady=(4, 8))
        if not self.commands:
            label(self.list_area, "No commands yet. Click “New command” — there are ready-made "
                                  "examples to start from.", 10, False, theme.MUTED).pack(
                anchor="w", padx=36, pady=(0, 12))
            return
        for index, command in enumerate(self.commands):
            row = card(self.list_area, corner_radius=12)
            row.pack(fill="x", padx=34, pady=5)
            text = ctk.CTkFrame(row, fg_color="transparent")
            text.pack(side="left", fill="x", expand=True, padx=16, pady=12)
            label(text, f"“{command['phrase']}”", 12, True).pack(anchor="w")
            first = command["steps"].splitlines()[0] if command["steps"] else ""
            more = len([ln for ln in command["steps"].splitlines() if ln.strip()]) - 1
            label(text, shorten(first, 80) + (f"   (+{more} more)" if more > 0 else ""),
                  9, False, theme.MUTED).pack(anchor="w", pady=(3, 0))
            for symbol, action in (("✕", lambda i=index: self._remove(i)),
                                   ("✎", lambda i=index: self._open_dialog(i)),
                                   ("▶", lambda c=command: self._test(c))):
                ctk.CTkButton(row, text=symbol, width=32, height=30, fg_color="transparent",
                              hover_color=theme.HOVER, text_color=theme.TEXT_SOFT,
                              command=action).pack(side="right", padx=(0, 2))

    def _open_dialog(self, index):
        existing = self.commands[index] if index is not None else None

        def saved(command):
            if index is None:
                self.commands.append(command)
            else:
                self.commands[index] = command
            self._store()
            self._render_commands()

        CommandDialog(self, existing, saved)

    def _remove(self, index):
        removed = self.commands.pop(index)
        self._store()
        self._render_commands()
        self.toast("Removed", f"“{removed['phrase']}” was deleted.", "info")

    def _store(self):
        try:
            save_json(VOICE_PATH, self.commands)
        except OSError as exc:
            self.toast("Couldn't save", str(exc), "error")

    def _test(self, command):
        slots = {name: "test" for name in voice.placeholders(command["phrase"])}
        self._run(command, slots)

    # ---- options ---------------------------------------------------------------------
    def _mode(self):
        return MODES.get(self.mode_var.get(), "push")

    def _mode_changed(self):
        self.listener.stop()
        self._save_options()
        self._update_button()

    def _save_options(self):
        self.save_callback({
            "voice_consent": bool(self.consent_var.get()),
            "voice_mode": self._mode(),
            "voice_language": voice.LANGUAGES.get(self.lang_var.get(), "en-US"),
            "voice_wake_word": self.wake_entry.get().strip(),
        })
        if not self.consent_var.get():
            self.listener.stop()

    def on_show(self):
        self._update_button()

    # ---- listening -------------------------------------------------------------------
    def _blocker(self):
        """Why we can't listen right now, or None."""
        if not self.consent_var.get():
            return "Turn on “Allow voice recognition” first."
        missing = voice.missing_packages()
        if missing:
            return "Install " + " and ".join(missing) + " first (see the note above)."
        return None

    def _mic_clicked(self):
        if self.listener.running:
            self.listener.stop()
            return
        self.push_to_talk()

    def push_to_talk(self):
        """Start listening (also called by the global voice shortcut)."""
        reason = self._blocker()
        if reason:
            self.toast("Voice isn't ready", reason, "info")
            return
        if self.listener.running:
            return
        self.listener.start(voice.LANGUAGES.get(self.lang_var.get(), "en-US"),
                            continuous=self._mode() == "always")
        self._set_listening(True)

    def _set_listening(self, listening):
        self._update_button()
        if listening and not self._pulsing:
            self._pulsing = True
            self._pulse(1.0)

    def _update_button(self):
        if self.listener.running:
            text = "■  Stop" if self._mode() == "always" else "●  Listening…"
        else:
            text = "▶  Start listening" if self._mode() == "always" else "🎤  Talk"
        self.mic_button.configure(text=text)

    def _pulse(self, target):
        if not self.listener.running:
            self._pulsing = False
            self.mic_button.configure(fg_color=theme.accent("main"))
            return
        if not anim.is_enabled("effects"):
            self.mic_button.configure(fg_color=theme.DANGER)
            self.after(500, lambda: self._pulse(target))
            return

        def step(level):
            self._pulse_level = level
            self.mic_button.configure(fg_color=theme.lerp(
                theme.accent("main"), theme.resolve(theme.DANGER), level))

        anim.animate(self.mic_button, "pulse", self._pulse_level, target, 700, step,
                     done=lambda: self._pulse(0.0 if target > 0.5 else 1.0),
                     easing=anim.ease_in_out, kind="effects")

    # ---- events from the microphone thread (read on the Tk thread) ----------------------------
    def _poll(self):
        try:
            while True:
                kind, text = self._events.get_nowait()
                self._handle(kind, text)
        except queue.Empty:
            pass
        self.after(200, self._poll)

    def _handle(self, kind, text):
        if kind == "status":
            self.status.configure(text=text, text_color=theme.TEXT)
        elif kind == "heard":
            self._handle_heard(text)
        elif kind == "error":
            self.status.configure(text=text, text_color=theme.DANGER)
            self.toast("Voice problem", text, "error")
        elif kind == "stopped":
            self._set_listening(False)
            if self.status.cget("text").startswith(("Listening", "Getting", "Understanding", "Hearing")):
                self.status.configure(text="Ready", text_color=theme.TEXT)
        elif kind == "toast":
            self.toast("Voice command", text, "info")

    def _handle_heard(self, text):
        if not text:
            self.status.configure(text="Didn't catch that — try again", text_color=theme.MUTED)
            return
        self.heard.configure(text=f"Heard: “{text}”")
        guesses = [text] + [g for g in self.listener.alternatives if g != text]
        always = self._mode() == "always"
        armed = time.monotonic() < self._armed_until
        command, slots, wake_seen = None, {}, False
        for guess in guesses:
            phrase = guess
            if always:
                stripped = voice.strip_wake_word(guess, self.wake_entry.get())
                if stripped is not None:
                    if not stripped.strip():
                        # Only the wake word: listen for the command in the next few seconds,
                        # so you can say "hey jarvis" ... and then just the command.
                        self._armed_until = time.monotonic() + self.FOLLOW_UP_SECONDS
                        self._beep()
                        self.status.configure(
                            text=f"Yes? Say your command now ({self.FOLLOW_UP_SECONDS} s)…",
                            text_color=theme.OK)
                        return
                    phrase = stripped
                elif armed:
                    phrase = guess               # follow-up: no wake word needed
                else:
                    continue
            wake_seen = True
            command, slots = voice.match_command(phrase, self.commands)
            if command is not None:
                break
        if always and not wake_seen:
            self.status.configure(
                text="Listening…  (didn't hear the wake word. If it keeps mishearing it, "
                     "add what it heard as another wake word, separated by a comma. Or "
                     "clear the wake word box to listen for commands only.)",
                text_color=theme.MUTED)
            return
        if command is None:
            self.status.configure(text="No command matches that", text_color=theme.MUTED)
            if self._mode() == "push":
                self.toast("No matching command", f"I heard “{text}”.", "info")
            return
        suffix = "  (say the next one without the wake word)" if always else ""
        self.status.configure(text=f"Running “{command['phrase'].split('|')[0].strip()}”{suffix}",
                              text_color=theme.OK)
        if always:
            self._armed_until = time.monotonic() + self.FOLLOW_UP_SECONDS
        self._run(command, slots)

    def _beep(self):
        try:
            import winsound
            winsound.Beep(900, 70)
        except Exception:
            pass

    def _run(self, command, slots):
        try:
            steps = voice.parse_steps(command["steps"])
        except ValueError as exc:
            self.toast("Command problem", str(exc), "error")
            return

        def work():
            try:
                voice.run_steps(steps, slots, notify=lambda t: self._events.put(("toast", t)))
            except OSError as exc:
                self._events.put(("error", f"Couldn't run that: {exc}"))

        threading.Thread(target=work, daemon=True).start()

    def shutdown(self):
        self.listener.stop()
