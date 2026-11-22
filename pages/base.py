import customtkinter as ctk

from core import theme
from core.widgets import label


class BasePage(ctk.CTkFrame):
    """Every page is one of these. The app calls on_show/on_hide so a page
    only does background work while you are actually looking at it."""

    def __init__(self, master, toast=None):
        super().__init__(master, fg_color=theme.BG, corner_radius=0)
        self.toast = toast or (lambda *args, **kwargs: None)

    def header(self, title, subtitle):
        """Standard page header. Returns a frame on the right for buttons."""
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=34, pady=(30, 18))
        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.pack(side="left")
        label(left, title, 27, True).pack(anchor="w")
        label(left, subtitle, 11, False, theme.MUTED).pack(anchor="w", pady=(4, 0))
        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.pack(side="right")
        return right

    def on_show(self):
        pass

    def on_hide(self):
        pass
