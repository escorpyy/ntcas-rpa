"""
agent/macro_recorder.py
========================
MacroRecorderPro — records real mouse clicks and keyboard presses,
converts them to RPA steps, and lets the user import them directly
into a FlowPanel.

Features:
  ┌──────────────────────────────────────────────────────────────────────┐
  │ Global shortcuts   Ctrl+Shift+R  → Start / Resume recording          │
  │                    Ctrl+Shift+P  → Pause (keeps listeners alive)     │
  │                    Ctrl+Shift+S  → Stop recording                    │
  │                    Ctrl+Shift+W  → Insert manual Wait step           │
  │                                                                       │
  │ Pause mode         A third state between recording and stopped.       │
  │                    Listeners stay active; events are ignored.         │
  │                    Pressing Pause again resumes.                      │
  │                                                                       │
  │ Auto-Wait tracker  When idle for > N seconds between actions, an     │
  │                    automatic "wait" step is injected. Toggled by a   │
  │                    UI checkbox. Threshold configurable (default 1.5s) │
  │                                                                       │
  │ State machine      Explicit enum: IDLE / RECORDING / PAUSED          │
  │                    All UI labels, button colours and guard clauses    │
  │                    key off this single source of truth.              │
  │                                                                       │
  │ Thread-safe        Every _push() call is threadsafe; the listbox     │
  │                    redraw is always scheduled via self.after(0, …).  │
  └──────────────────────────────────────────────────────────────────────┘

Dependencies:
    pip install pynput pyautogui

Usage:
    MacroRecorderPro(root, on_import=flow_panel.load)
"""

from __future__ import annotations

import time
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from enum import Enum, auto

# ── optional pynput ────────────────────────────────────────────────────────────
try:
    from pynput import mouse as _mouse_lib, keyboard as _kb_lib
    from pynput.keyboard import Key as _PKey
    _PYNPUT_OK = True
except ImportError:
    _PYNPUT_OK = False

from core.constants import T

# ── Constants ─────────────────────────────────────────────────────────────────

# Keys that become hotkey steps rather than type_text
_SPECIAL_KEYS = {
    "enter", "tab", "escape", "delete", "backspace",
    "up", "down", "left", "right", "space",
    "page_up", "page_down", "home", "end",
    "f1","f2","f3","f4","f5","f6","f7","f8","f9","f10","f11","f12",
    "insert", "num_lock", "caps_lock", "print_screen",
}

_MODIFIER_KEYS = {
    "ctrl_l", "ctrl_r", "shift", "shift_l", "shift_r",
    "alt_l", "alt_r", "cmd", "super_l", "super_r",
}

# Normalise modifier names that appear in combinations
_MOD_NORM = {
    "ctrl_l": "ctrl", "ctrl_r": "ctrl",
    "shift_l": "shift", "shift_r": "shift",
    "alt_l": "alt",   "alt_r": "alt",
}


class _State(Enum):
    IDLE      = auto()
    RECORDING = auto()
    PAUSED    = auto()


# ─────────────────────────────────────────────────────────────────────────────
#  MacroRecorderPro
# ─────────────────────────────────────────────────────────────────────────────

class MacroRecorderPro(tk.Toplevel):
    """
    Record real mouse clicks and keyboard presses → convert to RPA steps
    → import directly into a FlowPanel.

    Global shortcuts (active while this window exists):
        Ctrl+Shift+R  – Start / Resume
        Ctrl+Shift+P  – Pause / Resume
        Ctrl+Shift+S  – Stop
        Ctrl+Shift+W  – Insert Wait step
    """

    def __init__(self, parent, on_import=None):
        super().__init__(parent)
        self.title("🎙 MacroRecorder Pro")
        self.configure(bg=T["bg"])
        self.attributes("-topmost", True)
        self.geometry("720x660")
        self.minsize(620, 540)

        self.on_import = on_import

        # Core state
        self._state        = _State.IDLE
        self._lock         = threading.Lock()
        self._steps: list  = []

        # Listener handles
        self._m_listener  = None
        self._k_listener  = None

        # Keyboard tracking
        self._typed_buf   : list = []
        self._held_mods   : set  = set()

        # Double-click tracking
        self._last_click_t  = 0.0
        self._last_click_xy = (-9999, -9999)

        # Auto-Wait tracking
        self._last_action_t = 0.0
        self._auto_wait_var = tk.BooleanVar(value=True)
        self._auto_wait_threshold = 1.5

        # Global shortcut listener (always active while window is open)
        self._global_listener = None
        self._global_mods: set = set()

        self._build_ui()
        self._bind_global_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=T["bg2"], pady=14)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🎙 MacroRecorder Pro",
                 bg=T["bg2"], fg=T["acc"],
                 font=("Segoe UI Semibold", 14)).pack(side="left", padx=20)
        self._state_badge = tk.Label(
            hdr, text="● IDLE",
            bg=T["bg2"], fg=T["fg3"],
            font=("Segoe UI Semibold", 10))
        self._state_badge.pack(side="left", padx=12)
        tk.Label(hdr, text="Ctrl+Shift:  R=Record  P=Pause  S=Stop  W=Wait",
                 bg=T["bg2"], fg=T["fg3"], font=T["font_s"]
                 ).pack(side="right", padx=16)

        # Control bar
        ctrl = tk.Frame(self, bg=T["bg"], pady=10)
        ctrl.pack(fill="x", padx=16)

        self._rec_btn = tk.Button(
            ctrl, text="⏺  Start  [Ctrl+Shift+R]",
            bg=T["red"], fg="white",
            font=("Segoe UI Semibold", 10), relief="flat",
            padx=12, pady=8, command=self._cmd_record)
        self._rec_btn.pack(side="left")

        self._pause_btn = tk.Button(
            ctrl, text="⏸  Pause  [Ctrl+Shift+P]",
            bg=T["bg3"], fg=T["fg3"],
            font=T["font_b"], relief="flat",
            padx=12, pady=8, state="disabled", command=self._cmd_pause)
        self._pause_btn.pack(side="left", padx=6)

        self._stop_btn = tk.Button(
            ctrl, text="⏹  Stop  [Ctrl+Shift+S]",
            bg=T["bg3"], fg=T["fg3"],
            font=T["font_b"], relief="flat",
            padx=12, pady=8, state="disabled", command=self._cmd_stop)
        self._stop_btn.pack(side="left")

        tk.Button(ctrl, text="🗑  Clear",
                  bg=T["bg3"], fg=T["fg2"],
                  font=T["font_b"], relief="flat",
                  padx=10, pady=8, command=self._clear
                  ).pack(side="left", padx=10)

        self._wait_btn = tk.Button(
            ctrl, text="＋ Wait  [Ctrl+Shift+W]",
            bg=T["bg3"], fg=T["cyan"],
            font=T["font_b"], relief="flat",
            padx=10, pady=8, command=self._cmd_add_wait)
        self._wait_btn.pack(side="left")

        self._import_btn = tk.Button(
            ctrl, text="✔  Import to Flow",
            bg=T["green"], fg="white",
            font=("Segoe UI Semibold", 10), relief="flat",
            padx=14, pady=8, state="disabled", command=self._import_steps)
        self._import_btn.pack(side="right")

        # Auto-Wait option row
        aw_row = tk.Frame(self, bg=T["bg"])
        aw_row.pack(fill="x", padx=20, pady=(0, 4))

        self._aw_chk = tk.Checkbutton(
            aw_row, variable=self._auto_wait_var,
            text="Auto-insert Wait on idle gaps  (threshold:",
            bg=T["bg"], fg=T["fg2"],
            selectcolor=T["bg3"], activebackground=T["bg"],
            activeforeground=T["fg"], font=T["font_s"],
            relief="flat", bd=0)
        self._aw_chk.pack(side="left")
        _add_tooltip(self._aw_chk,
            "When enabled, if no action is recorded for longer than the threshold,\n"
            "a Wait step is automatically inserted to preserve timing.")

        self._thresh_var = tk.StringVar(value="1.5")
        thresh_entry = tk.Entry(
            aw_row, textvariable=self._thresh_var,
            width=4, bg=T["bg3"], fg=T["yellow"],
            font=T["font_s"], relief="flat", insertbackground=T["yellow"])
        thresh_entry.pack(side="left", padx=4)
        _add_tooltip(thresh_entry, "Idle seconds before a Wait step is injected.")
        tk.Label(aw_row, text="s)", bg=T["bg"], fg=T["fg2"],
                 font=T["font_s"]).pack(side="left")

        # Status label
        self._status = tk.Label(
            self, text="Idle — press Start Recording or Ctrl+Shift+R",
            bg=T["bg"], fg=T["fg2"], font=T["font_m"], anchor="w")
        self._status.pack(fill="x", padx=20, pady=(4, 2))

        # Step list
        lf = tk.LabelFrame(
            self, text="  Recorded Steps  ",
            bg=T["bg"], fg=T["acc"],
            font=("Segoe UI Semibold", 9), bd=1, relief="flat")
        lf.pack(fill="both", expand=True, padx=16, pady=(0, 6))

        self._listbox = tk.Listbox(
            lf, bg=T["bg3"], fg=T["fg"], font=T["font_m"],
            selectbackground=T["acc_dark"], activestyle="none",
            relief="flat", bd=0)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self._listbox.yview)
        self._listbox.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._listbox.pack(fill="both", expand=True, padx=4, pady=4)

        # Bottom row
        bot = tk.Frame(self, bg=T["bg"], pady=4)
        bot.pack(fill="x", padx=16)

        tk.Button(bot, text="🗑 Delete Selected",
                  bg=T["bg2"], fg=T["red"], font=T["font_s"],
                  relief="flat", command=self._delete_selected
                  ).pack(side="left")

        self._count_lbl = tk.Label(
            bot, text="0 steps",
            bg=T["bg"], fg=T["fg3"], font=T["font_s"])
        self._count_lbl.pack(side="right")

        # Tips
        tip = (
            "Tips:  Minimise this window before recording — it stays on top.  "
            "Double-clicks are detected automatically.  "
            "Consecutive typed chars are merged into one Type step.  "
            "Press Pause to freeze capture without stopping listeners."
        )
        tk.Label(self, text=tip, bg=T["bg"], fg=T["fg3"],
                 font=T["font_s"], justify="left", wraplength=680, anchor="w"
                 ).pack(fill="x", padx=20, pady=(0, 10))

    # ── State machine ─────────────────────────────────────────────────────────

    def _transition(self, new_state: _State):
        """Apply a state transition and update all UI elements atomically."""
        self._state = new_state

        if new_state == _State.IDLE:
            self._state_badge.config(text="● IDLE",    fg=T["fg3"])
            self._status.config(     text="Idle — press Start or Ctrl+Shift+R", fg=T["fg2"])
            self._rec_btn.config(    text="⏺  Start  [Ctrl+Shift+R]",
                                     bg=T["red"], fg="white", state="normal")
            self._pause_btn.config(  text="⏸  Pause  [Ctrl+Shift+P]",
                                     bg=T["bg3"], fg=T["fg3"], state="disabled")
            self._stop_btn.config(   bg=T["bg3"], fg=T["fg3"], state="disabled")

        elif new_state == _State.RECORDING:
            self._state_badge.config(text="● REC",     fg=T["red"])
            self._status.config(     text="Recording…  ESC or Ctrl+Shift+S to stop", fg=T["red"])
            self._rec_btn.config(    text="⏺  Recording…",
                                     bg=T["bg4"], fg=T["red"], state="disabled")
            self._pause_btn.config(  text="⏸  Pause  [Ctrl+Shift+P]",
                                     bg=T["yellow"], fg=T["bg"], state="normal")
            self._stop_btn.config(   bg=T["bg3"], fg=T["fg2"], state="normal")

        elif new_state == _State.PAUSED:
            self._state_badge.config(text="⏸ PAUSED",  fg=T["yellow"])
            self._status.config(     text="Paused — Ctrl+Shift+R or P to resume", fg=T["yellow"])
            self._rec_btn.config(    text="▶  Resume  [Ctrl+Shift+R]",
                                     bg=T["green"], fg="white", state="normal")
            self._pause_btn.config(  text="▶  Resume  [Ctrl+Shift+P]",
                                     bg=T["green"], fg="white", state="normal")
            self._stop_btn.config(   bg=T["bg3"], fg=T["fg2"], state="normal")

        has_steps = bool(self._steps)
        self._import_btn.config(state="normal" if has_steps else "disabled")

    # ── Command handlers (from buttons OR global shortcuts) ───────────────────

    def _cmd_record(self):
        """Start (if IDLE) or Resume (if PAUSED)."""
        if self._state == _State.IDLE:
            self._start_listeners()
            self._last_action_t = time.time()
            self._transition(_State.RECORDING)
        elif self._state == _State.PAUSED:
            self._last_action_t = time.time()
            self._transition(_State.RECORDING)

    def _cmd_pause(self):
        """Toggle between RECORDING and PAUSED (listeners stay alive)."""
        if self._state == _State.RECORDING:
            self._flush_typed()
            self._transition(_State.PAUSED)
        elif self._state == _State.PAUSED:
            self._last_action_t = time.time()
            self._transition(_State.RECORDING)

    def _cmd_stop(self):
        """Stop recording completely; tear down listeners."""
        if self._state in (_State.RECORDING, _State.PAUSED):
            self._flush_typed()
            self._stop_listeners()
            self._transition(_State.IDLE)
            n = len(self._steps)
            self._status.config(
                text=f"Stopped — {n} step(s) recorded.",
                fg=T["green"])

    def _cmd_add_wait(self):
        self._push({"type": "wait", "seconds": 1.0, "note": "", "enabled": True})

    # ── Global shortcut listener ──────────────────────────────────────────────

    def _bind_global_shortcuts(self):
        if not _PYNPUT_OK:
            return
        self._global_mods = set()

        def on_press(key):
            name = _key_name(key)
            if name in _MODIFIER_KEYS:
                self._global_mods.add(_MOD_NORM.get(name, name))
                return
            mods = self._global_mods
            if {"ctrl", "shift"} <= mods:
                if name == "r":   self.after(0, self._cmd_record)
                elif name == "p": self.after(0, self._cmd_pause)
                elif name == "s": self.after(0, self._cmd_stop)
                elif name == "w": self.after(0, self._cmd_add_wait)

        def on_release(key):
            name = _key_name(key)
            norm = _MOD_NORM.get(name, name)
            self._global_mods.discard(norm)

        self._global_listener = _kb_lib.Listener(
            on_press=on_press, on_release=on_release)
        self._global_listener.daemon = True
        self._global_listener.start()

    # ── pynput listener lifecycle ─────────────────────────────────────────────

    def _start_listeners(self):
        if not _PYNPUT_OK:
            messagebox.showerror(
                "Missing library",
                "pynput is required for recording.\n\npip install pynput")
            return
        self._held_mods.clear()
        self._m_listener = _mouse_lib.Listener(on_click=self._on_click)
        self._k_listener = _kb_lib.Listener(
            on_press=self._on_key, on_release=self._on_key_release)
        self._m_listener.start()
        self._k_listener.start()

    def _stop_listeners(self):
        for lst in (self._m_listener, self._k_listener):
            if lst:
                try:
                    lst.stop()
                except Exception:
                    pass
        self._m_listener = self._k_listener = None

    # ── pynput callbacks ──────────────────────────────────────────────────────

    def _on_click(self, x, y, button, pressed):
        if not pressed or self._state != _State.RECORDING:
            return

        from pynput.mouse import Button as _Btn

        now    = time.time()
        is_dbl = (
            now - self._last_click_t < 0.35
            and abs(x - self._last_click_xy[0]) < 12
            and abs(y - self._last_click_xy[1]) < 12
        )
        self._maybe_insert_auto_wait(now)
        self._last_click_t  = now
        self._last_click_xy = (x, y)
        self._last_action_t = now
        self._flush_typed()

        if button == _Btn.right:
            self._push({"type": "right_click", "x": x, "y": y,
                        "note": "", "enabled": True})
            return

        if is_dbl:
            with self._lock:
                if self._steps and self._steps[-1]["type"] == "click":
                    self._steps[-1] = {
                        "type": "double_click", "x": x, "y": y,
                        "note": "", "enabled": True}
                    self.after(0, self._redraw_list)
                    return

        self._push({"type": "click", "x": x, "y": y, "note": "", "enabled": True})

    def _on_key(self, key):
        if self._state != _State.RECORDING:
            return

        key_str = _key_name(key)

        # ESC → stop
        try:
            if key == _PKey.esc:
                self.after(0, self._cmd_stop)
                return
        except Exception:
            pass

        if key_str is None:
            return

        if key_str in _MODIFIER_KEYS:
            self._held_mods.add(key_str)
            return

        now = time.time()
        self._maybe_insert_auto_wait(now)
        self._last_action_t = now

        # Modifier + key → hotkey step
        if self._held_mods:
            self._flush_typed()
            norm_mods = sorted({_MOD_NORM.get(m, m) for m in self._held_mods})
            combo     = "+".join(norm_mods) + "+" + key_str
            self._push({"type": "hotkey", "keys": combo, "note": "", "enabled": True})
            return

        # Pure special key → hotkey step
        if key_str in _SPECIAL_KEYS:
            self._flush_typed()
            self._push({"type": "hotkey", "keys": key_str, "note": "", "enabled": True})
            return

        # Printable character → buffer
        try:
            char = key.char
            if char and char.isprintable():
                self._typed_buf.append(char)
                return
        except AttributeError:
            pass

    def _on_key_release(self, key):
        key_str = _key_name(key)
        if key_str in _MODIFIER_KEYS:
            self._held_mods.discard(key_str)

    # ── Auto-Wait logic ───────────────────────────────────────────────────────

    def _maybe_insert_auto_wait(self, now: float):
        """
        If auto-wait is enabled and the gap since the last recorded action
        exceeds the threshold, inject a Wait step before the current action.
        """
        if not self._auto_wait_var.get():
            return
        if self._last_action_t == 0.0:
            return  # first action ever
        try:
            threshold = float(self._thresh_var.get())
        except ValueError:
            threshold = self._auto_wait_threshold

        gap = now - self._last_action_t
        if gap >= threshold:
            wait_seconds = round(gap, 2)
            self._push({"type": "wait", "seconds": wait_seconds,
                        "note": "auto", "enabled": True})

    # ── Step helpers ──────────────────────────────────────────────────────────

    def _flush_typed(self):
        """Merge buffered chars into a clip_type step."""
        if not self._typed_buf:
            return
        text = "".join(self._typed_buf)
        self._typed_buf.clear()
        self._push({"type": "clip_type", "text": text, "note": "", "enabled": True})

    def _push(self, step: dict):
        """Thread-safe step append + scheduled UI refresh."""
        with self._lock:
            self._steps.append(step)
        self.after(0, self._redraw_list)

    def _redraw_list(self):
        """Rebuild the listbox from _steps. Must be called on the main thread."""
        with self._lock:
            steps_snapshot = list(self._steps)

        self._listbox.delete(0, "end")
        for i, s in enumerate(steps_snapshot, 1):
            t    = s.get("type", "?")
            auto = "  [auto]" if s.get("note") == "auto" else ""

            if t in ("click", "double_click", "right_click"):
                label = f"{t.replace('_', ' ').title()} @ ({s['x']}, {s['y']})"
            elif t == "hotkey":
                label = f"Hotkey: {s.get('keys', '')}"
            elif t in ("type_text", "clip_type"):
                txt   = s.get("text", "")
                label = f"Type: {txt[:40]}{'…' if len(txt) > 40 else ''}"
            elif t == "wait":
                label = f"Wait: {s.get('seconds', 1.0):.2f}s{auto}"
            else:
                label = t

            self._listbox.insert("end", f"  {i:02d}.  {label}")

        n = len(steps_snapshot)
        self._count_lbl.config(text=f"{n} step{'s' if n != 1 else ''}")
        self._import_btn.config(state="normal" if n else "disabled")

    def _delete_selected(self):
        sel = self._listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        with self._lock:
            if 0 <= idx < len(self._steps):
                self._steps.pop(idx)
        self._redraw_list()

    def _clear(self):
        with self._lock:
            self._steps.clear()
            self._typed_buf.clear()
        self._redraw_list()

    # ── Import ────────────────────────────────────────────────────────────────

    def _import_steps(self):
        if not self._steps:
            return
        self._flush_typed()
        if self.on_import:
            with self._lock:
                steps_copy = list(self._steps)
            self.on_import(steps_copy)
        self.destroy()

    # ── Window close ─────────────────────────────────────────────────────────

    def _on_close(self):
        self._stop_listeners()
        if self._global_listener:
            try:
                self._global_listener.stop()
            except Exception:
                pass
        self.destroy()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _key_name(key) -> str | None:
    """Return a normalised lowercase key name, or None for unknowns."""
    try:
        name = getattr(key, "name", None)
        if name:
            return name.lower()
        char = getattr(key, "char", None)
        if char:
            return char.lower()
    except Exception:
        pass
    return None


def _add_tooltip(widget: tk.Widget, text: str):
    """Attach a hover tooltip to any widget."""
    tip: list = [None]

    def _show(event):
        if tip[0]:
            return
        tw = tk.Toplevel(widget)
        tw.wm_overrideredirect(True)
        tw.configure(bg="#ffffcc")
        tk.Label(tw, text=text, bg="#ffffcc", fg="#333333",
                 font=("Segoe UI", 8), relief="solid",
                 bd=1, padx=6, pady=4, justify="left").pack()
        x = widget.winfo_rootx() + 20
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        tw.wm_geometry(f"+{x}+{y}")
        tip[0] = tw

    def _hide(event):
        if tip[0]:
            tip[0].destroy()
            tip[0] = None

    widget.bind("<Enter>", _show, add="+")
    widget.bind("<Leave>", _hide, add="+")
