import json
import os
import sys
from pathlib import Path


def _data_dir():
    """Next to the program when run from source; in %APPDATA% when packaged as an .exe
    (the install folder is often read-only, and updates must not wipe your settings)."""
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("APPDATA") or Path.home()) / "CommandCenter"
        base.mkdir(parents=True, exist_ok=True)
        return base
    return Path(__file__).resolve().parent.parent


DATA_DIR = _data_dir()
CONFIG_PATH = DATA_DIR / "config.json"
LAUNCHER_PATH = DATA_DIR / "launcher.json"

THEMES = ("dark", "light", "system")
ACCENTS = ("blue", "green", "purple", "orange", "pink")

DEFAULT_CONFIG = {
    "animations": True,
    "tutorial_seen": False,
    "setup_done": False,
    "news_on_start": False,
    "weather_on_start": False,
    "anim_pages": True,
    "anim_sidebar": True,
    "anim_scenes": True,
    "anim_meters": True,
    "anim_toasts": True,
    "anim_effects": True,
    "alerts_enabled": True,
    "alert_delivery": "both",
    "alert_sound": True,
    "alert_delay_seconds": 5,
    "cpu_threshold": 85,
    "ram_threshold": 90,
    "disk_free_threshold": 10,
    "refresh_interval_ms": 1000,
    "power_saver": True,
    "theme": "dark",
    "accent_color": "blue",
    # System tray, shortcuts and Windows start-up
    "tray_icon": False,
    "close_to_tray": False,
    "start_with_windows": False,
    "start_minimized": False,
    "hotkey_toggle": "ctrl+alt+c",
    "hotkey_voice": "ctrl+alt+v",
    # Voice control (nothing is recorded or sent until voice_consent is switched on)
    "voice_consent": False,
    "voice_mode": "push",
    "voice_language": "en-US",
    "voice_wake_word": "",
    # Discord DMs read from Windows notifications (local only, no bot / API / token)
    "discord_enabled": False,
    "discord_auto_busy": False,
    "discord_busy_message": "Hey, this person is busy right now!",
    "discord_busy_manual": False,          # "I'm busy right now"
    "discord_busy_in_call": True,          # busy while on a Discord call
    "discord_busy_fullscreen": False,      # busy while a game / video is fullscreen
    "discord_busy_apps": [],               # busy while any of these programs is open
    "discord_busy_apps_active_only": False,
}


def load_json(path, default):
    try:
        path = Path(path)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return default


def save_json(path, data):
    """Write atomically so a crash can't leave a half-written file."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=4), encoding="utf-8")
    os.replace(tmp, path)


def load_config():
    data = DEFAULT_CONFIG.copy()
    saved = load_json(CONFIG_PATH, {})
    if isinstance(saved, dict):
        data.update(saved)
    if data.get("theme") not in THEMES:
        data["theme"] = DEFAULT_CONFIG["theme"]
    if data.get("accent_color") not in ACCENTS:
        data["accent_color"] = DEFAULT_CONFIG["accent_color"]
    return data


def save_config(data):
    save_json(CONFIG_PATH, data)
