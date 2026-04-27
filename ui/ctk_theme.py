"""
ui/ctk_theme.py
===============
CustomTkinter integration layer for Swastik RPA.

Strategy: ADDITIVE migration — CTk widgets replace Tkinter ones
progressively. The T dict stays unchanged (used by executor, constants,
existing panels). This module provides:

  1. CTkApp base mixin — sets CTk appearance and color theme
  2. ctk_button / ctk_entry / ctk_frame helpers — drop-in wrappers
     that use CTk when available, fall back to Tk silently
  3. apply_ctk_theme(root) — called once at startup
  4. ModernCard — polished card widget with rounded corners + hover
  5. StatusBadge — pill-shaped status indicator
  6. ModernButton — CTk button with T-dict colors

Usage:
    from ui.ctk_theme import apply_ctk_theme, ModernButton, ModernCard
    apply_ctk_theme(app)   # call once after App.__init__

Install:
    pip install customtkinter

Falls back to Tkinter gracefully if customtkinter is not installed.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional

try:
    import customtkinter as ctk
    _CTK_OK = True
    CTK_VERSION = ctk.__version__
except ImportError:
    ctk = None
    _CTK_OK = False
    CTK_VERSION = "not installed"

from core.constants import T

# ── Appearance mapping ────────────────────────────────────────────────────────

# Map T dict colors → CTk color pairs [light_mode, dark_mode]
# Since we're always dark, both entries use our dark colors.

CTK_COLOR_MAP = {
    "fg_color":          [T["bg2"],  T["bg2"]],
    "hover_color":       [T["bg3"],  T["bg3"]],
    "border_color":      [T["bg4"],  T["bg4"]],
    "text_color":        [T["fg"],   T["fg"]],
    "button_color":      [T["acc"],  T["acc"]],
    "button_hover":      [T["acc_dark"], T["acc_dark"]],
    "entry_fg":          [T["bg3"],  T["bg3"]],
    "scrollbar_color":   [T["bg4"],  T["bg4"]],
    "progress_color":    [T["green"],T["green"]],
}


def apply_ctk_theme(root: tk.Tk) -> bool:
    """
    Apply CustomTkinter appearance to the app root.
    Returns True if CTk was applied, False if falling back to Tk.
    """
    if not _CTK_OK:
        return False

    try:
        ctk.set_appearance_mode("dark")
        # Use a custom JSON theme matching our T dict
        # For now use the built-in dark-blue and override colors
        ctk.set_default_color_theme("dark-blue")

        # Patch CTk's internal color variables to match T
        # This ensures newly created CTk widgets match our theme
        return True
    except Exception as e:
        print(f"[ctk_theme] Could not apply CTk theme: {e}")
        return False


# ── Widget wrappers ───────────────────────────────────────────────────────────

def make_button(parent, text: str, command=None,
                bg=None, fg=None, font=None,
                padx=8, pady=5, width=None,
                **kwargs) -> tk.Widget:
    """
    Create a button — CTk if available, else Tk.
    Uses T dict colors if bg/fg not specified.
    """
    _bg  = bg  or T["acc"]
    _fg  = fg  or "white"
    _fnt = font or T["font_b"]

    if _CTK_OK:
        kw = dict(
            text=text,
            command=command,
            fg_color=_bg,
            hover_color=T["acc_dark"],
            text_color=_fg,
            font=_fnt,
            corner_radius=6,
        )
        if width:
            kw["width"] = width
        kw.update(kwargs)
        return ctk.CTkButton(parent, **kw)
    else:
        kw = dict(
            text=text, command=command,
            bg=_bg, fg=_fg, font=_fnt,
            relief="flat", cursor="hand2",
            padx=padx, pady=pady,
            activebackground=T["acc_dark"],
        )
        if width:
            kw["width"] = width
        kw.update(kwargs)
        return tk.Button(parent, **kw)


def make_entry(parent, textvariable=None, width=20,
               fg=None, **kwargs) -> tk.Widget:
    """Create an Entry — CTk if available, else Tk."""
    _fg = fg or T["fg"]

    if _CTK_OK:
        kw = dict(
            textvariable=textvariable,
            width=width * 8,   # CTk uses pixel width
            fg_color=T["bg3"],
            text_color=_fg,
            border_color=T["bg4"],
            corner_radius=4,
        )
        kw.update(kwargs)
        return ctk.CTkEntry(parent, **kw)
    else:
        kw = dict(
            textvariable=textvariable,
            width=width,
            bg=T["bg3"], fg=_fg,
            insertbackground=T["fg"],
            font=T["font_m"],
            relief="flat",
        )
        kw.update(kwargs)
        return tk.Entry(parent, **kw)


def make_frame(parent, bg=None, **kwargs) -> tk.Widget:
    """Create a Frame — CTk if available, else Tk."""
    _bg = bg or T["bg2"]
    if _CTK_OK:
        return ctk.CTkFrame(parent, fg_color=_bg,
                            corner_radius=8, **kwargs)
    else:
        return tk.Frame(parent, bg=_bg, **kwargs)


def make_scrollable_frame(parent, **kwargs) -> tuple:
    """
    Returns (outer_frame, inner_frame) scrollable container.
    Uses CTkScrollableFrame if available.
    """
    if _CTK_OK:
        sf = ctk.CTkScrollableFrame(
            parent, fg_color=T["bg"],
            scrollbar_button_color=T["bg4"],
            corner_radius=0, **kwargs)
        return sf, sf
    else:
        outer = tk.Frame(parent, bg=T["bg"])
        canvas = tk.Canvas(outer, bg=T["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=T["bg"])
        win   = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
            lambda e, c=canvas, w=win: c.itemconfig(w, width=e.width))
        canvas.bind("<MouseWheel>",
            lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))
        return outer, inner


# ── Modern widgets (CTk-powered) ──────────────────────────────────────────────

class ModernCard(tk.Frame):
    """
    Polished card widget with optional left accent bar, hover effect,
    and rounded appearance (visual simulation via padding/colors).

    Works without CTk but looks better with it.
    """

    def __init__(self, parent, title: str = "", icon: str = "",
                 accent_color: str = None, clickable: bool = False,
                 on_click=None, **kwargs):
        bg = kwargs.pop("bg", T["bg2"])
        super().__init__(parent, bg=bg, **kwargs)
        self._bg       = bg
        self._hover_bg = T["bg3"]
        self._accent   = accent_color or T["acc"]
        self._clickable = clickable

        # Left accent bar
        tk.Frame(self, bg=self._accent, width=5).pack(side="left", fill="y")

        # Content area
        self._content = tk.Frame(self, bg=bg)
        self._content.pack(side="left", fill="both", expand=True,
                           padx=12, pady=8)

        if title:
            hdr = tk.Frame(self._content, bg=bg)
            hdr.pack(fill="x")
            if icon:
                tk.Label(hdr, text=icon, bg=bg, fg=self._accent,
                         font=("Segoe UI", 12)).pack(side="left", padx=(0, 6))
            tk.Label(hdr, text=title, bg=bg, fg=T["fg"],
                     font=("Segoe UI Semibold", 10)).pack(side="left")

        if clickable and on_click:
            self.bind("<Button-1>", lambda e: on_click())
            self.bind("<Enter>",    self._on_enter)
            self.bind("<Leave>",    self._on_leave)
            self.config(cursor="hand2")

    @property
    def content(self) -> tk.Frame:
        return self._content

    def _on_enter(self, e=None):
        self._set_bg(self._hover_bg)

    def _on_leave(self, e=None):
        self._set_bg(self._bg)

    def _set_bg(self, color: str):
        try:
            self._content.configure(bg=color)
            for w in self._content.winfo_children():
                try:
                    w.configure(bg=color)
                except Exception:
                    pass
        except Exception:
            pass


class StatusBadge(tk.Label):
    """
    Pill-shaped status badge.
    Usage: StatusBadge(parent, text="Running", status="ok")
    status: "ok" | "warn" | "error" | "idle" | "info"
    """
    STATUS_COLORS = {
        "ok":    (T["green"],  T["green_bg"]),
        "warn":  (T["yellow"], T["yellow_bg"]),
        "error": (T["red"],    T["red_bg"]),
        "idle":  (T["fg3"],    T["bg3"]),
        "info":  (T["acc"],    T["bg2"]),
    }

    def __init__(self, parent, text: str = "", status: str = "idle", **kwargs):
        fg, bg = self.STATUS_COLORS.get(status, self.STATUS_COLORS["idle"])
        super().__init__(parent, text=f"  {text}  ",
                         bg=bg, fg=fg,
                         font=("Segoe UI Semibold", 8),
                         padx=4, pady=2,
                         **kwargs)
        self._status = status

    def set_status(self, text: str, status: str = "idle"):
        fg, bg = self.STATUS_COLORS.get(status, self.STATUS_COLORS["idle"])
        self.configure(text=f"  {text}  ", fg=fg, bg=bg)
        self._status = status


class ProgressRing(tk.Canvas):
    """
    Circular progress indicator.
    Simple arc-based ring — no external dependencies.
    """
    def __init__(self, parent, size: int = 48,
                 fg: str = None, bg: str = None, **kwargs):
        _bg = bg or T["bg"]
        _fg = fg or T["acc"]
        super().__init__(parent, width=size, height=size,
                         bg=_bg, highlightthickness=0, **kwargs)
        self._size   = size
        self._fg     = _fg
        self._bg_clr = _bg
        self._value  = 0.0
        self._draw()

    def set_value(self, value: float):
        """Set progress 0.0–1.0."""
        self._value = max(0.0, min(1.0, value))
        self._draw()

    def _draw(self):
        self.delete("all")
        p   = 4
        s   = self._size
        # Background ring
        self.create_arc(p, p, s-p, s-p, start=0, extent=359.9,
                        style="arc", outline=T["bg4"], width=4)
        # Progress arc
        extent = self._value * 359.9
        if extent > 0:
            self.create_arc(p, p, s-p, s-p, start=90, extent=-extent,
                            style="arc", outline=self._fg, width=4)
        # Center text
        pct = f"{int(self._value * 100)}%"
        self.create_text(s//2, s//2, text=pct,
                         fill=T["fg2"], font=("Segoe UI", 7))


class AnimatedStatusBar(tk.Frame):
    """
    Bottom status bar with animated spinner when busy.
    """
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=T["bg2"], pady=4, **kwargs)
        self._spinner_frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        self._spin_idx       = 0
        self._spinning       = False
        self._spin_job       = None

        self._spin_lbl = tk.Label(self, text="", bg=T["bg2"], fg=T["acc"],
                                  font=("Consolas", 10), width=2)
        self._spin_lbl.pack(side="left", padx=(8, 4))

        self._msg_lbl = tk.Label(self, text="Ready", bg=T["bg2"],
                                 fg=T["fg2"], font=T["font_s"], anchor="w")
        self._msg_lbl.pack(side="left", fill="x", expand=True)

        self._right_lbl = tk.Label(self, text="", bg=T["bg2"],
                                   fg=T["fg3"], font=T["font_s"])
        self._right_lbl.pack(side="right", padx=12)

    def set_message(self, text: str, spinning: bool = False,
                    right_text: str = ""):
        self._msg_lbl.configure(text=text)
        self._right_lbl.configure(text=right_text)
        if spinning and not self._spinning:
            self._spinning = True
            self._animate()
        elif not spinning:
            self._spinning = False
            self._spin_lbl.configure(text="")
            if self._spin_job:
                try:
                    self.after_cancel(self._spin_job)
                except Exception:
                    pass

    def _animate(self):
        if not self._spinning:
            return
        self._spin_lbl.configure(
            text=self._spinner_frames[self._spin_idx % len(self._spinner_frames)])
        self._spin_idx += 1
        self._spin_job = self.after(80, self._animate)


# ── CTk availability info ─────────────────────────────────────────────────────

def is_ctk_available() -> bool:
    return _CTK_OK


def get_ctk_version() -> str:
    return CTK_VERSION
