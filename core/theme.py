"""Colours, light/dark switching and accent colours.

Every colour below is a (light, dark) pair. customtkinter picks the right half
automatically and re-colours its widgets the moment the appearance mode
changes, which is what makes the Theme setting work live.

Plain tkinter things (canvases, the ttk process tables) don't understand pairs,
so they call resolve() and listen for theme changes with on_change().
"""
import tkinter as tk
from tkinter import ttk

import customtkinter as ctk

from . import anim

# ---- surfaces and text ----------------------------------------------------
BG = ("#f2f5fa", "#0c1018")
SIDEBAR = ("#ffffff", "#111722")
CARD = ("#ffffff", "#151e2b")
CARD_ALT = ("#eef2f8", "#182231")
BORDER = ("#dde4ee", "#202d40")
DIVIDER = ("#dbe2ed", "#263448")
HOVER = ("#e3e9f3", "#202b3b")
TRACK = ("#dbe2ed", "#273345")
INPUT = ("#e8edf6", "#1c2738")

TEXT = ("#0f1a2b", "#f3f6fb")
TEXT_SOFT = ("#3a4a62", "#aab6c8")
MUTED = ("#66768d", "#8290a5")

OK = ("#168a62", "#4bd6a0")
OK_BG = ("#dcf5ec", "#142b29")
WARN = ("#c07a10", "#f4b44f")
DANGER = ("#d03a4d", "#ef6575")

TOAST_BG = ("#ffffff", "#1b2636")
TOAST_BORDER = ("#cfd8e6", "#34445c")

# ---- metric colours used on charts and bars -------------------------------
METRIC = {
    "cpu": ("#2f6df2", "#579bff"),
    "ram": ("#7c5cf0", "#a78bfa"),
    "disk": ("#169c70", "#42d6a0"),
    "down": ("#c9821a", "#f2b75c"),
    "up": ("#169c70", "#42d6a0"),
}

# ---- accent colours (the user's choice in Settings) -----------------------
ACCENT_BASE = {
    "blue": "#2f6df2",
    "green": "#1f9d6b",
    "purple": "#7c5cf0",
    "orange": "#e07b1a",
    "pink": "#dc4a86",
}


# ---- colour maths ---------------------------------------------------------
def hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(c))) for c in rgb)


def lerp(first, second, t):
    """Blend two #rrggbb colours. t=0 gives first, t=1 gives second."""
    a, b = hex_to_rgb(first), hex_to_rgb(second)
    return rgb_to_hex([a[i] + (b[i] - a[i]) * t for i in range(3)])


def is_dark():
    return ctk.get_appearance_mode() == "Dark"


def resolve(color):
    """Turn a (light, dark) pair into the single colour for the current mode."""
    if isinstance(color, (tuple, list)):
        return color[1] if is_dark() else color[0]
    return color


# ---- state ----------------------------------------------------------------
_state = {"accent": "blue", "mode": None}
_bindings = []
_listeners = []


def accent(role="main"):
    base = ACCENT_BASE.get(_state["accent"], ACCENT_BASE["blue"])
    if role == "hover":
        return lerp(base, "#000000", 0.15)
    if role == "soft":      # tinted background for the active nav item
        return (lerp(base, "#ffffff", 0.86), lerp(base, resolve(BG[1]), 0.72))
    if role == "text":      # readable accent-coloured text
        return (base, lerp(base, "#ffffff", 0.35))
    return base


def bind(widget, **options):
    """Keep widget options in sync with the accent colour.

    Example: theme.bind(button, fg_color="main", hover_color="hover")
    """
    _bindings.append((widget, options))
    _apply_binding(widget, options)
    return widget


def _apply_binding(widget, options):
    widget.configure(**{name: accent(role) for name, role in options.items()})


def on_change(callback):
    _listeners.append(callback)


def _notify():
    for callback in list(_listeners):
        try:
            callback()
        except tk.TclError:
            pass


def _refresh_bindings():
    alive = []
    for widget, options in _bindings:
        try:
            if widget.winfo_exists():
                _apply_binding(widget, options)
                alive.append((widget, options))
        except tk.TclError:
            pass
    _bindings[:] = alive


def _restyle_ttk():
    try:
        style = ttk.Style()
    except tk.TclError:
        return
    try:
        if style.theme_use() != "clam":
            style.theme_use("clam")
    except tk.TclError:
        pass

    card = resolve(CARD)
    head = resolve(CARD_ALT)
    text = resolve(TEXT)
    muted = resolve(MUTED)
    track = resolve(TRACK)

    style.layout("CC.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.configure("CC.Treeview", background=card, fieldbackground=card,
                    foreground=text, borderwidth=0, relief="flat",
                    rowheight=30, font=("Segoe UI", 10))
    style.map("CC.Treeview",
              background=[("selected", accent("main"))],
              foreground=[("selected", "#ffffff")])
    style.configure("CC.Treeview.Heading", background=head, foreground=muted,
                    relief="flat", borderwidth=0, padding=(8, 7),
                    font=("Segoe UI", 9, "bold"))
    style.map("CC.Treeview.Heading", background=[("active", resolve(HOVER))])
    style.configure("CC.Vertical.TScrollbar", background=track,
                    troughcolor=card, bordercolor=card, lightcolor=track,
                    darkcolor=track, arrowcolor=muted, relief="flat",
                    gripcount=0, arrowsize=12)
    style.map("CC.Vertical.TScrollbar", background=[("active", muted)])


def apply(config):
    """Apply theme, accent and animation settings from the config."""
    ctk.set_appearance_mode(config.get("theme", "dark"))
    _state["accent"] = config.get("accent_color", "blue")
    _state["mode"] = ctk.get_appearance_mode()
    anim.set_enabled(config.get("animations", True))
    anim.set_kinds({kind: config.get(f"anim_{kind}", True) for kind in anim.KINDS})
    _restyle_ttk()
    _refresh_bindings()
    _notify()


def poll_system_mode():
    """Call now and then: catches Windows switching light/dark while we run."""
    mode = ctk.get_appearance_mode()
    if mode != _state["mode"]:
        _state["mode"] = mode
        _restyle_ttk()
        _notify()
