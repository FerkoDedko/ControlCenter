"""Small time-based animation helpers for Tk widgets.

Animations are driven by the clock, not by frame counts, so they take the same
time on a slow or a fast PC. Starting a new animation with the same key on the
same widget cancels the old one and carries on from wherever the value is now.
"""
import time
import tkinter as tk

FRAME_MS = 15
_enabled = True

# Each kind of animation can be switched off on its own (Settings -> Appearance).
KINDS = ("pages", "sidebar", "scenes", "meters", "toasts", "effects")
_kinds = {}


def set_enabled(value):
    global _enabled
    _enabled = bool(value)


def set_kinds(values):
    _kinds.clear()
    _kinds.update({k: bool(v) for k, v in values.items() if k in KINDS})


def is_enabled(kind=None):
    """True if animations are on in general and (when given) this kind is on too."""
    return _enabled and (kind is None or _kinds.get(kind, True))


# ---- easing functions (t goes 0 -> 1) -------------------------------------
def linear(t):
    return t


def ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def ease_in_cubic(t):
    return t ** 3


def ease_in_out(t):
    return 4 * t ** 3 if t < 0.5 else 1 - ((-2 * t + 2) ** 3) / 2


def ease_out_back(t, overshoot=1.2):
    t -= 1
    return 1 + (overshoot + 1) * t ** 3 + overshoot * t ** 2


# ---- engine ---------------------------------------------------------------
def cancel(widget, key):
    jobs = widget.__dict__.get("_cc_anim_jobs")
    if jobs and key in jobs:
        try:
            widget.after_cancel(jobs.pop(key))
        except (tk.TclError, ValueError):
            jobs.pop(key, None)


def animate(widget, key, start, end, duration_ms, step,
            done=None, easing=ease_out_cubic, kind=None):
    """Tween a number from start to end, calling step(value) every frame.

    With animations turned off (or nothing to animate) step(end) is called
    once straight away and the widget simply snaps to its final state.
    """
    cancel(widget, key)
    if not is_enabled(kind) or duration_ms <= 0 or start == end:
        step(end)
        if done:
            done()
        return

    jobs = widget.__dict__.setdefault("_cc_anim_jobs", {})
    started = time.perf_counter()

    def tick():
        try:
            if not widget.winfo_exists():
                jobs.pop(key, None)
                return
        except tk.TclError:
            jobs.pop(key, None)
            return
        progress = min(1.0, (time.perf_counter() - started) * 1000.0 / duration_ms)
        step(start + (end - start) * easing(progress))
        if progress >= 1.0:
            jobs.pop(key, None)
            if done:
                done()
        else:
            jobs[key] = widget.after(FRAME_MS, tick)

    tick()
