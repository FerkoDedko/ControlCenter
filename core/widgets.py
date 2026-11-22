"""Small reusable widgets and helpers shared by every page."""
import tkinter as tk
from collections import deque

import customtkinter as ctk

from . import anim, theme

FONT = "Segoe UI"


def font(size=11, bold=False):
    return (FONT, size, "bold") if bold else (FONT, size)


def label(master, text="", size=11, bold=False, color=theme.TEXT, wrap_margin=56, **kwargs):
    """A text label. A wraplength is treated as a maximum: the text wraps sooner when its
    container is narrower, so nothing gets cut off (wrap_margin = space the container
    keeps for padding and neighbours)."""
    made = ctk.CTkLabel(master, text=text, font=font(size, bold),
                        text_color=color, **kwargs)
    if kwargs.get("wraplength"):
        _fit_wrap(made, master, kwargs["wraplength"], wrap_margin)
    return made


def _fit_wrap(made, master, limit, margin):
    last = {"value": None}

    def fit(_event=None):
        try:
            width = master.winfo_width()
            if width < 80:
                return
            scale = made._get_widget_scaling() if hasattr(made, "_get_widget_scaling") else 1
            target = int(min(limit, max(120, (width - margin) / scale)))
            if target != last["value"]:
                last["value"] = target
                made.configure(wraplength=target)
        except Exception:
            pass

    try:
        master.bind("<Configure>", fit, add="+")
    except Exception:
        pass


def card(master, **kwargs):
    options = dict(fg_color=theme.CARD, corner_radius=16,
                   border_width=1, border_color=theme.BORDER)
    options.update(kwargs)
    return ctk.CTkFrame(master, **options)


def bind_tree(widget, sequence, callback):
    """Bind an event on a widget and everything inside it."""
    widget.bind(sequence, callback, add="+")
    for child in widget.winfo_children():
        bind_tree(child, sequence, callback)


def hover_fade(frame, base, hover, duration=140):
    """Smoothly fade a frame's background while the mouse is over it."""
    state = {"on": False, "t": 0.0}

    def step(t):
        state["t"] = t
        frame.configure(fg_color=theme.lerp(theme.resolve(base),
                                            theme.resolve(hover), t))

    def settle():
        frame.configure(fg_color=base)

    def go(on):
        if state["on"] == on:
            return
        state["on"] = on
        anim.animate(frame, "hover", state["t"], 1.0 if on else 0.0, duration,
                     step, done=None if on else settle, kind="effects")

    def pointer_inside():
        try:
            x, y = frame.winfo_pointerxy()
            left, top = frame.winfo_rootx(), frame.winfo_rooty()
            return (left <= x < left + frame.winfo_width()
                    and top <= y < top + frame.winfo_height())
        except tk.TclError:
            return False

    bind_tree(frame, "<Enter>", lambda _e: go(True))
    bind_tree(frame, "<Leave>",
              lambda _e: frame.after(20, lambda: go(pointer_inside())))


class Sparkline(tk.Canvas):
    """A small live line chart (last N samples) with a soft filled area."""

    def __init__(self, master, color, bg=theme.CARD, height=34, length=60,
                 fixed_max=None, floor=1.0):
        super().__init__(master, height=height, width=10,
                         highlightthickness=0, bd=0)
        self.color = color
        self.bg_color = bg
        self.fixed_max = fixed_max
        self.floor = floor
        self.values = deque([0.0] * length, maxlen=length)
        self.bind("<Configure>", lambda _e: self.redraw())
        theme.on_change(self.redraw)

    def push(self, value):
        self.values.append(float(value))
        self.redraw()

    def redraw(self):
        try:
            width, height = self.winfo_width(), self.winfo_height()
        except tk.TclError:
            return
        if width < 12 or height < 8:
            return
        background = theme.resolve(self.bg_color)
        line = theme.resolve(self.color)
        self.configure(bg=background)
        self.delete("all")

        top = self.fixed_max or max(max(self.values) * 1.15, self.floor)
        step = width / (len(self.values) - 1)
        points = []
        for index, value in enumerate(self.values):
            y = height - 2 - (min(value, top) / top) * (height - 6)
            points += [index * step, y]

        self.create_polygon(points + [width, height, 0, height],
                            fill=theme.lerp(line, background, 0.82), outline="")
        self.create_line(points, fill=line, width=2, smooth=True)
