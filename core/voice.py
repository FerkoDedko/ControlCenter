"""Voice commands: say a phrase, Command Center runs the steps you attached to it.

Pieces (each can be used and tested on its own):
  * normalize / match_command   - decide which command a spoken sentence means
  * parse_steps / run_steps      - the little step language ("open ...", "wait 3")
  * Segmenter                    - finds where one spoken phrase starts and ends
  * VoiceListener                - microphone -> Segmenter -> speech-to-text

Speech-to-text uses the free Google web service through the SpeechRecognition
package, so short audio clips of what you say leave your PC. The microphone is
read with the sounddevice package. Both are optional installs.
"""
import difflib
import importlib.util
import queue
import re
import unicodedata
import threading
import time
import urllib.parse
from array import array
from collections import deque
from dataclasses import dataclass
from functools import lru_cache

from . import utils

LANGUAGES = {
    "English (US)": "en-US", "English (UK)": "en-GB", "Slovenčina": "sk-SK",
    "Čeština": "cs-CZ", "Deutsch": "de-DE", "Español": "es-ES",
    "Français": "fr-FR", "Italiano": "it-IT", "Polski": "pl-PL",
}


def missing_packages():
    needed = (("speech_recognition", "SpeechRecognition"), ("sounddevice", "sounddevice"))
    return [pkg for module, pkg in needed if importlib.util.find_spec(module) is None]


# ---- matching what was said -----------------------------------------------------
def normalize(text):
    # "Horkýže Slíže" and "horkize slize" should be the same thing, so accents go
    text = unicodedata.normalize("NFKD", (text or "").lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w\s{}]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def placeholders(phrase):
    return re.findall(r"\{(\w+)\}", phrase or "")


@lru_cache(maxsize=256)
def _phrase_regex(phrase):
    pattern = ""
    for part in re.split(r"(\{\w+\})", normalize(phrase)):
        slot = re.fullmatch(r"\{(\w+)\}", part)
        pattern += f"(?P<{slot.group(1)}>.+?)" if slot else re.escape(part)
    return re.compile(pattern)


def _wake_list(wake_word):
    """Several wake words can be given, separated by commas: "hey jarvis, hey system"."""
    return [w for w in (normalize(x) for x in (wake_word or "").split(",")) if w]


def strip_wake_word(heard, wake_word):
    """Remove a leading wake word. Returns None if it wasn't said.

    Speech services often mishear the wake word a little ("hey jarvis" -> "hey
    service"), so a close-sounding start is accepted too.
    """
    wakes = _wake_list(wake_word)
    if not wakes:
        return heard
    spoken = normalize(heard)
    words = spoken.split()
    best = None
    for wake in wakes:
        count = len(wake.split())
        if len(words) < count:
            continue
        start = " ".join(words[:count])
        score = 1.0 if start == wake else difflib.SequenceMatcher(None, start, wake).ratio()
        if score >= 0.65 and (best is None or score > best[0]):
            best = (score, " ".join(words[count:]))
    return best[1] if best else None


FILLER = re.compile(r"^(?:(?:please|can you|could you|would you|just|go ahead and|now|the)\s+)+")


def match_command(heard, commands, fuzzy=0.72):
    """Find the command for a spoken sentence.

    commands: list of dicts with "phrase". A phrase may contain {slots} such as
    "play {song} on spotify", which capture whatever was said there.
    Returns (command, {slot: text}) or (None, {}).
    """
    spoken = FILLER.sub("", normalize(heard))
    if not spoken:
        return None, {}
    # A command can have several ways to say it, separated by "|":
    #   play horkize slize | play horky slize | play horkyze slize
    for command in commands:
        for variant in command["phrase"].split("|"):
            try:
                match = _phrase_regex(variant.strip()).fullmatch(spoken)
            except re.error:
                continue
            if match:
                return command, {k: v.strip() for k, v in match.groupdict().items()}

    best, best_score = None, fuzzy
    for command in commands:
        for variant in command["phrase"].split("|"):
            if "{" in variant or not variant.strip():
                continue
            score = difflib.SequenceMatcher(None, spoken, normalize(variant)).ratio()
            if score >= best_score:
                best, best_score = command, score
    return (best, {}) if best else (None, {})


# ---- steps ------------------------------------------------------------------------
@dataclass
class Step:
    kind: str     # open | wait | media | toast | discord_read | discord_reply
    arg: str


MEDIA_KEYS = {"play_pause": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2,
              "volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD}

STEP_HELP = ("open <app, file, website or link>   e.g.  open spotify:\n"
             "wait <seconds>                       e.g.  wait 3\n"
             "media play_pause | next | previous | stop | volume_up | volume_down | mute\n"
             "toast <message to show>\n"
             "discord_read                         reads your latest Discord DM out loud\n"
             "discord_reply <text>                 replies to it, e.g.  discord_reply {message}")


def parse_steps(text):
    """Turn the steps text into a list of Step. Raises ValueError with a friendly message."""
    steps = []
    for number, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        kind, _space, arg = line.partition(" ")
        kind, arg = kind.lower(), arg.strip()
        if kind in ("discord_read", "lock"):
            arg = ""                                   # nothing to fill in
        elif kind in ("open", "toast", "discord_reply", "speak"):
            if not arg:
                raise ValueError(f"Line {number}: “{kind}” needs something after it.")
        elif kind == "wait":
            try:
                seconds = float(arg)
            except ValueError:
                raise ValueError(f"Line {number}: “wait” needs a number of seconds.") from None
            if not 0 <= seconds <= 60:
                raise ValueError(f"Line {number}: wait between 0 and 60 seconds.")
        elif kind == "media":
            arg = arg.lower().replace(" ", "_")
            if arg not in MEDIA_KEYS:
                raise ValueError(f"Line {number}: media can be {', '.join(MEDIA_KEYS)}.")
        else:
            raise ValueError(f"Line {number}: I don't know “{kind}”. "
                             "Use open, wait, media, toast, speak, lock, discord_read or discord_reply.")
        steps.append(Step(kind, arg))
    if not steps:
        raise ValueError("Add at least one step.")
    return steps


# ---- the friendly step builder works with (kind, value) rows -------------------------------
# kinds: program, website, spotify_search, spotify_play, wait, media, toast
MEDIA_LABELS = {"Play / pause": "play_pause", "Next track": "next",
                "Previous track": "previous", "Stop": "stop",
                "Volume up": "volume_up", "Volume down": "volume_down", "Mute": "mute"}

_SPOTIFY_SEARCH = "spotify:search:"


def _quote_keep_slots(text):
    """URL-encode text but leave {slots} alone (they're filled in when spoken)."""
    parts = re.split(r"(\{\w+\})", text)
    return "".join(p if re.fullmatch(r"\{\w+\}", p) else urllib.parse.quote(p, safe="")
                   for p in parts)


def _unquote_keep_slots(text):
    parts = re.split(r"(\{\w+\})", text)
    return "".join(p if re.fullmatch(r"\{\w+\}", p) else urllib.parse.unquote(p)
                   for p in parts)


def rows_to_text(rows):
    """Turn builder rows into the step text. Raises ValueError for an empty row."""
    lines = []
    for number, (kind, value) in enumerate(rows, start=1):
        value = (value or "").strip()
        if kind in ("discord_read", "lock"):            # has nothing to fill in
            lines.append(kind)
            continue
        if not value:
            raise ValueError(f"Step {number} is empty. Fill it in or remove it.")
        if kind == "program":
            lines.append(f"open {value}")
        elif kind == "website":
            if not re.match(r"^[a-z][a-z0-9+.\-]*://", value, re.I):
                value = "https://" + value
            lines.append(f"open {value}")
        elif kind == "spotify_search":
            lines.append(f"open {_SPOTIFY_SEARCH}{_quote_keep_slots(value)}")
        elif kind == "spotify_play":
            lines += [f"open {value}", "wait 4", "media play_pause"]
        elif kind in ("wait", "media", "toast", "speak", "discord_reply"):
            lines.append(f"{kind} {value}")
        else:
            raise ValueError(f"Step {number}: unknown action.")
    if not lines:
        raise ValueError("Add at least one step.")
    return "\n".join(lines)


def text_to_rows(text):
    """The reverse of rows_to_text, for editing an existing command."""
    steps = parse_steps(text)
    rows, i = [], 0
    while i < len(steps):
        step = steps[i]
        if step.kind != "open":
            rows.append((step.kind, step.arg))
            i += 1
            continue
        arg, lowered = step.arg, step.arg.lower()
        follow = steps[i + 1:i + 3]
        is_song_link = (lowered.startswith("spotify:") and not lowered.startswith(_SPOTIFY_SEARCH)) \
            or "open.spotify.com" in lowered
        if is_song_link and len(follow) == 2 and follow[0].kind == "wait" \
                and follow[1].kind == "media" and follow[1].arg == "play_pause":
            rows.append(("spotify_play", arg))
            i += 3
            continue
        if lowered.startswith(_SPOTIFY_SEARCH):
            rows.append(("spotify_search", _unquote_keep_slots(arg[len(_SPOTIFY_SEARCH):])))
        elif re.match(r"^https?://", arg, re.I):
            rows.append(("website", arg))
        else:
            rows.append(("program", arg))
        i += 1
    return rows


def validate_command(phrase, steps_text):
    """Returns the parsed steps, or raises ValueError explaining what's wrong."""
    if not normalize(re.sub(r"\{\w+\}", "", phrase or "")):
        raise ValueError("Type the phrase you'll say.")
    try:
        _phrase_regex(phrase)
    except re.error:
        raise ValueError("Each {slot} name can only be used once in the phrase.") from None
    steps = parse_steps(steps_text)
    unknown = {name for step in steps for name in placeholders(step.arg)} \
        - set(placeholders(phrase)) - set(BUILTINS)
    if unknown:
        raise ValueError("The steps use {" + sorted(unknown)[0]
                         + "} but the phrase doesn't have it.")
    return steps


def _percent(value):
    return f"{round(value)} percent"


def _builtin_time():
    return time.strftime("%H:%M")


def _builtin_date():
    now = time.localtime()
    return f"{time.strftime('%A', now)}, {now.tm_mday} {time.strftime('%B', now)}"


def _builtin_cpu():
    import psutil
    return _percent(psutil.cpu_percent(interval=0.4))


def _builtin_memory():
    import psutil
    return _percent(psutil.virtual_memory().percent)


def _builtin_disk():
    import psutil
    return _percent(psutil.disk_usage(os_anchor()).percent)


def os_anchor():
    return "C:\\" if utils.IS_WINDOWS else "/"


def _builtin_battery():
    import psutil
    battery = getattr(psutil, "sensors_battery", lambda: None)()
    if battery is None:
        return "no battery found"
    state = "charging" if battery.power_plugged else "not charging"
    return f"{round(battery.percent)} percent, {state}"


def _builtin_weather():
    """One small request to wttr.in (location from your IP address)."""
    import urllib.request
    try:
        request = urllib.request.Request("https://wttr.in/?format=%l:+%C,+%t&m",
                                         headers={"User-Agent": "curl/8"})
        with urllib.request.urlopen(request, timeout=6) as reply:
            text = reply.read().decode("utf-8", "replace").strip()
        if not text or "Unknown" in text or len(text) > 160:
            raise ValueError(text)
        return text.replace("°C", " degrees").replace("+", "")
    except Exception:
        return "I couldn't reach the weather service."


NEWS_FEED = "https://feeds.bbci.co.uk/news/rss.xml"


def headlines(count=4, fetch=None):
    """The top headlines as a list of strings (BBC News RSS). Raises on failure."""
    import urllib.request
    import xml.etree.ElementTree as ET
    if fetch is None:
        def fetch(url):
            request = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
            with urllib.request.urlopen(request, timeout=6) as reply:
                return reply.read()
    root = ET.fromstring(fetch(NEWS_FEED))
    titles = [(item.findtext("title") or "").strip() for item in root.iter("item")]
    titles = [t for t in titles if t][:count]
    if not titles:
        raise ValueError("no headlines")
    return titles


def news_text(count=4, fetch=None):
    try:
        return "Top news. " + " ... ".join(headlines(count, fetch))
    except Exception:
        return "I couldn't reach the news service."


# {name} values the app fills in by itself. A word you say with the same name wins.
BUILTINS = {"time": _builtin_time, "date": _builtin_date, "weekday": lambda: time.strftime("%A"),
            "cpu": _builtin_cpu, "memory": _builtin_memory, "disk": _builtin_disk,
            "battery": _builtin_battery, "weather": _builtin_weather,
            "news": news_text}


_SPOTIFY_WEB = re.compile(r"^https?://open\.spotify\.com/(?:intl-[a-z]+/)?"
                          r"(track|album|playlist|artist|episode|show)/([A-Za-z0-9]+)", re.I)


def spotify_app_link(link):
    """https://open.spotify.com/track/ID?si=... -> spotify:track:ID, which Windows hands
    straight to the Spotify app instead of opening a browser tab. Other text is unchanged."""
    match = _SPOTIFY_WEB.match((link or "").strip())
    return f"spotify:{match.group(1).lower()}:{match.group(2)}" if match else link


def fill(arg, captures, quote=None):
    """Put spoken words into {slots}. Links get the words URL-encoded; plain text
    (quote=False) never does."""
    is_link = bool(re.match(r"^[a-z][a-z0-9+.\-]+:", arg, re.I)) if quote is None else quote

    def replace(match):
        name = match.group(1)
        if name in captures:
            value = captures[name]
        elif name in BUILTINS:
            try:
                value = str(BUILTINS[name]())
            except Exception:
                value = "unavailable"
        else:
            value = ""
        return urllib.parse.quote(value) if is_link else value

    return re.sub(r"\{(\w+)\}", replace, arg)


def lock_pc():
    if not utils.IS_WINDOWS:
        raise OSError("Locking is only available on Windows.")
    import ctypes
    ctypes.windll.user32.LockWorkStation()


def press_media_key(code):
    if not utils.IS_WINDOWS:
        raise OSError("Media keys are only available on Windows.")
    import ctypes
    user32 = ctypes.windll.user32
    user32.keybd_event(code, 0, 0, 0)
    user32.keybd_event(code, 0, 2, 0)        # key up


def run_steps(steps, captures=None, *, launch=utils.launch, press=press_media_key,
              notify=None, sleep=time.sleep, cancelled=lambda: False, discord=None,
              speak=None, lock=None, refocus=None):
    """Run the steps in order. Meant for a background thread."""
    captures = captures or {}
    if refocus is None:
        refocus = _refocus_after
    wants_music = any(st.kind == "open" and st.arg.lower().startswith(
        ("spotify:", "https://open.spotify.com")) for st in steps)
    if wants_music:
        remember = _remember_window()
        try:
            _run_steps(steps, captures, launch, press, notify, sleep, cancelled, discord,
                       speak, lock)
        finally:
            refocus(remember)                          # give your game / editor the focus back
        return
    _run_steps(steps, captures, launch, press, notify, sleep, cancelled, discord, speak, lock)


def _remember_window():
    if not utils.IS_WINDOWS:
        return None
    try:
        import ctypes
        return ctypes.windll.user32.GetForegroundWindow()
    except Exception:
        return None


def _refocus_after(hwnd):
    """Bring the window you were using back (Spotify likes to grab the focus)."""
    if not hwnd or not utils.IS_WINDOWS:
        return
    try:
        import ctypes
        from . import discord_dm
        time.sleep(0.4)
        if ctypes.windll.user32.IsWindow(hwnd) and ctypes.windll.user32.GetForegroundWindow() != hwnd:
            discord_dm._bring_to_front(hwnd)
    except Exception:
        pass


def _run_steps(steps, captures, launch, press, notify, sleep, cancelled, discord, speak, lock):
    for step in steps:
        if cancelled():
            return
        if step.kind == "open":
            launch(spotify_app_link(fill(step.arg, captures)))
        elif step.kind == "wait":
            remaining = float(step.arg)
            while remaining > 0 and not cancelled():
                slice_ = min(0.1, remaining)
                sleep(slice_)
                remaining -= slice_
        elif step.kind == "media":
            press(MEDIA_KEYS[step.arg])
        elif step.kind == "toast" and notify:
            notify(fill(step.arg, captures, quote=False))
        elif step.kind == "speak":
            if speak is None:
                from . import discord_dm
                speak = discord_dm.speak
            said = fill(step.arg, captures, quote=False)
            if notify:
                notify(said)                          # also show it, in case sound is off
            speak(said)
        elif step.kind == "lock":
            (lock or lock_pc)()
        elif step.kind in ("discord_read", "discord_reply"):
            if discord is None:
                from . import discord_dm
                discord = discord_dm.service()
            if step.kind == "discord_read":
                discord.read_latest_aloud()
            else:
                discord.reply_to_latest(fill(step.arg, captures, quote=False))


# ---- finding phrases in a stream of audio ------------------------------------------------
class Segmenter:
    """Cuts a stream of 16-bit mono audio into spoken phrases.

    It learns the background noise level first, treats anything clearly louder
    as speech, and ends a phrase after a short silence.
    """

    def __init__(self, rate=16000, frame_ms=30, silence_ms=700, min_ms=250,
                 max_ms=10000, preroll_ms=400, floor=180):
        self.frame_bytes = rate * frame_ms // 1000 * 2
        self.frame_ms = frame_ms
        self.silence_frames = silence_ms // frame_ms
        self.min_frames = min_ms // frame_ms
        self.max_frames = max_ms // frame_ms
        self.floor = floor
        self._preroll = deque(maxlen=max(1, preroll_ms // frame_ms))
        self._pending = b""
        self._noise = None
        self._calibration = []
        self.reset()

    def reset(self):
        self._pending = b""
        self._frames = []
        self._speaking = False
        self._silent = 0
        self._speech_frames = 0
        self._preroll.clear()

    @property
    def calibrated(self):
        return self._noise is not None

    @property
    def speaking(self):
        return self._speaking

    @staticmethod
    def rms(frame):
        samples = array("h")
        samples.frombytes(frame)
        if not samples:
            return 0.0
        return (sum(s * s for s in samples) / len(samples)) ** 0.5

    def feed(self, data):
        """Give it audio bytes; returns a list of finished phrases (bytes)."""
        self._pending += data
        done = []
        while len(self._pending) >= self.frame_bytes:
            frame, self._pending = (self._pending[:self.frame_bytes],
                                    self._pending[self.frame_bytes:])
            phrase = self._frame(frame)
            if phrase:
                done.append(phrase)
        return done

    def _frame(self, frame):
        level = self.rms(frame)
        if self._noise is None:                      # first ~0.5 s: measure the room
            self._calibration.append(level)
            if len(self._calibration) >= 15:
                # Use the quiet end of the sample, so speaking right away (or a cough)
                # during these first moments doesn't make the room look loud.
                quiet = sorted(self._calibration)[:8]
                self._noise = sum(quiet) / len(quiet)
            return None
        # Starting needs a clear jump; once talking, a lower bar keeps the phrase going
        # through quiet syllables, and a clearly lower one ends it.
        start_level = max(self.floor, self._noise * 2.2)
        keep_level = max(self.floor * 0.7, self._noise * 1.5)
        loud = level > (keep_level if self._speaking else start_level)

        if not self._speaking:
            if loud:
                self._speaking = True
                self._frames = list(self._preroll) + [frame]
                self._silent, self._speech_frames = 0, 1
            else:
                self._noise = 0.97 * self._noise + 0.03 * level    # follow the room
                self._preroll.append(frame)
            return None

        self._frames.append(frame)
        if loud:
            self._silent = 0
            self._speech_frames += 1
        else:
            self._silent += 1
        if self._silent >= self.silence_frames or len(self._frames) >= self.max_frames:
            long_enough = self._speech_frames >= self.min_frames
            audio = b"".join(self._frames)
            self._frames, self._speaking = [], False
            self._silent = self._speech_frames = 0
            self._preroll.clear()
            return audio if long_enough else None
        return None


class VoiceListener:
    """Listens on the microphone and reports what it hears.

    on_event(kind, text) is called from a background thread with:
      "status" - e.g. "Listening…"     "heard" - recognised text ("" if unclear)
      "error"  - something went wrong  "stopped" - listening has ended
    """
    RATE = 16000

    def __init__(self, on_event):
        self.on_event = on_event
        self._stop = threading.Event()
        self._thread = None
        self.alternatives = []     # other guesses for the last thing heard

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def start(self, language="en-US", continuous=False, timeout=10.0):
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, args=(language, continuous, timeout), daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self, language, continuous, timeout):
        try:
            import sounddevice
            import speech_recognition
        except ImportError as exc:
            self.on_event("error", f"Missing package: {exc.name}")
            self.on_event("stopped", "")
            return

        frames = queue.Queue()
        segmenter = Segmenter()
        recognizer = speech_recognition.Recognizer()
        try:
            stream = sounddevice.RawInputStream(
                samplerate=self.RATE, channels=1, dtype="int16", blocksize=480,
                callback=lambda data, _n, _t, _s: frames.put(bytes(data)))
            stream.start()
        except Exception as exc:
            self.on_event("error", f"Couldn't open the microphone: {exc}")
            self.on_event("stopped", "")
            return

        started = time.monotonic()
        ready = False
        self.on_event("status", "Getting ready…")
        try:
            while not self._stop.is_set():
                if not continuous and time.monotonic() - started > timeout:
                    self.on_event("heard", "")
                    break
                try:
                    chunk = frames.get(timeout=0.2)
                except queue.Empty:
                    continue
                was_speaking = segmenter.speaking
                phrases = segmenter.feed(chunk)
                if segmenter.speaking and not was_speaking:
                    self.on_event("status", "Hearing you…")
                for phrase in phrases:
                    self.on_event("status", "Understanding…")
                    self._recognize(speech_recognition, recognizer, phrase, language)
                    with frames.mutex:
                        frames.queue.clear()      # drop audio that piled up meanwhile
                    segmenter.reset()
                    self.on_event("status", "Listening…")
                    if not continuous:
                        self._stop.set()
                if not ready and segmenter.calibrated:
                    ready = True
                    self.on_event("status", "Listening…  say your phrase")
        finally:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            self.on_event("stopped", "")

    def _recognize(self, module, recognizer, phrase, language):
        audio = module.AudioData(phrase, self.RATE, 2)
        self.alternatives = []
        try:
            result = recognizer.recognize_google(audio, language=language, show_all=True)
            guesses = [a.get("transcript", "") for a in
                       (result.get("alternative", []) if isinstance(result, dict) else [])]
            guesses = [g for g in guesses if g]
            if not guesses:
                raise module.UnknownValueError()
            text = guesses[0]
            self.alternatives = guesses
        except module.UnknownValueError:
            self.on_event("heard", "")
        except module.RequestError as exc:
            self.on_event("error", f"Couldn't reach the speech service: {exc}")
        else:
            self.on_event("heard", text)
