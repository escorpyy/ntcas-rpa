"""
agent/macro_recorder.py
========================
MacroRecorderPro — records real mouse clicks and keyboard presses,
converts them to RPA steps, and lets the user import them directly
into a FlowPanel.

IMPROVEMENTS v9.3:
  ┌──────────────────────────────────────────────────────────────────────┐
  │ OVERLAY TOGGLE      A tiny always-on-top floating overlay panel      │
  │                     replaces Ctrl+Shift+* shortcuts entirely.        │
  │                     The overlay has Record / Pause / Stop / Wait     │
  │                     buttons that are clearly visible while you work. │
  │                                                                      │
  │ SELF-EXCLUSION      The recorder never records events that originate │
  │                     from its own window OR from the overlay window.  │
  │                     The overlay clicks will NOT appear in the steps. │
  │                                                                      │
  │ CONFIGURABLE KEYS   Record/Pause/Stop/Wait shortcuts are read from   │
  │                     _prefs["recorder_shortcuts"]. They default to    │
  │                     safe F-key combos (F2/F3/F4/F5) that do not     │
  │                     conflict with Windows system shortcuts.          │
  │                     These shortcuts are NEVER recorded as steps.     │
  │                                                                      │
  │ CONFLICT GUARD      When saving shortcuts in Settings, the recorder  │
  │                     validates against known Windows system combos.   │
  │                                                                      │
  │ Pause mode          Third state — listeners stay alive, events       │
  │                     ignored.                                         │
  │                                                                      │
  │ Auto-Wait tracker   Configurable idle-gap threshold injects a wait   │
  │                     step automatically.                              │
  │                                                                      │
  │ State machine       IDLE / RECORDING / PAUSED enum.                 │
  └──────────────────────────────────────────────────────────────────────┘

Dependencies:
    pip install pynput pyautogui
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

from core.constants import T, _prefs, save_prefs

# ── Constants ─────────────────────────────────────────────────────────────────

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

_MOD_NORM = {
    "ctrl_l": "ctrl", "ctrl_r": "ctrl",
    "shift_l": "shift", "shift_r": "shift",
    "alt_l": "alt",   "alt_r": "alt",
}

# Windows system shortcuts that must not be used as recorder shortcuts
_WINDOWS_SYSTEM_SHORTCUTS = {
    "ctrl+c", "ctrl+v", "ctrl+x", "ctrl+z", "ctrl+y",
    "ctrl+a", "ctrl+s", "ctrl+p", "ctrl+w", "ctrl+n",
    "ctrl+o", "ctrl+f", "ctrl+h", "ctrl+t", "ctrl+r",
    "alt+f4", "alt+tab", "win", "ctrl+alt+del",
    "ctrl+shift+esc", "ctrl+esc",
}

# Default recorder shortcuts — F-keys are safe, don't conflict with Windows
DEFAULT_RECORDER_SHORTCUTS = {
    "record":   "F2",
    "pause":    "F3",
    "stop":     "F4",
    "add_wait": "F5",
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
    Record real mouse clicks and keyboard presses → convert to RPA steps.

    A floating mini-overlay appears that stays on top of all windows.
    The overlay and this window are EXCLUDED from recording — clicks on
    them will never appear in the recorded steps.

    Shortcuts (configurable in Settings → Macro Recorder):
        F2  – Start / Resume
        F3  – Pause / Resume
        F4  – Stop
        F5  – Insert Wait step
    These shortcuts are NEVER recorded as steps.
    """

    def __init__(self, parent, on_import=None):
        super().__init__(parent)
        self.title("🎙 MacroRecorder Pro")
        self.configure(bg=T["bg"])
        self.attributes("-topmost", _prefs.get("recorder_topmost", True))
        self.geometry("740x680")
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
        self._auto_wait_var = tk.BooleanVar(value=_prefs.get("recorder_auto_wait_on", True))
        self._auto_wait_threshold = float(_prefs.get("recorder_auto_wait_threshold", 1.5))

        # Global shortcut listener
        self._global_listener = None
        self._global_mods: set = set()

        # Overlay
        self._overlay: _RecorderOverlay | None = None

        # Set of window IDs to exclude from recording
        self._excluded_hwnds: set = set()

        self._build_ui()
        self._bind_global_shortcuts()
        self._open_overlay()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # Register self after build
        self.after(200, self._register_own_window)

    def _register_own_window(self):
        """Store this window's tk id so we can exclude it from recording."""
        try:
            self._excluded_hwnds.add(str(self.winfo_id()))
        except Exception:
            pass

    # ── Overlay ───────────────────────────────────────────────────────────────

    def _open_overlay(self):
        if self._overlay and self._overlay.winfo_exists():
            return
        self._overlay = _RecorderOverlay(self)
        try:
            self._excluded_hwnds.add(str(self._overlay.winfo_id()))
        except Exception:
            pass

    def _close_overlay(self):
        if self._overlay:
            try:
                self._overlay.destroy()
            except Exception:
                pass
            self._overlay = None

    def _sync_overlay_state(self):
        """Push current state to the overlay so its buttons stay in sync."""
        if self._overlay and self._overlay.winfo_exists():
            try:
                self._overlay.update_state(self._state)
            except Exception:
                pass

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

        # Shortcut hint (from prefs)
        sc = self._get_shortcuts()
        hint = f"Shortcuts:  {sc['record']}=Record  {sc['pause']}=Pause  {sc['stop']}=Stop  {sc['add_wait']}=Wait"
        tk.Label(hdr, text=hint,
                 bg=T["bg2"], fg=T["fg3"], font=T["font_s"]
                 ).pack(side="right", padx=16)

        # Toggle overlay button
        tk.Button(hdr, text="◉ Overlay",
                  bg=T["bg3"], fg=T["cyan"],
                  font=T["font_s"], relief="flat", cursor="hand2",
                  padx=8, pady=4,
                  command=self._toggle_overlay).pack(side="right", padx=8)

        # Control bar
        ctrl = tk.Frame(self, bg=T["bg"], pady=10)
        ctrl.pack(fill="x", padx=16)

        self._rec_btn = tk.Button(
            ctrl, text="⏺  Start Recording",
            bg=T["red"], fg="white",
            font=("Segoe UI Semibold", 10), relief="flat",
            padx=12, pady=8, command=self._cmd_record)
        self._rec_btn.pack(side="left")

        self._pause_btn = tk.Button(
            ctrl, text="⏸  Pause",
            bg=T["bg3"], fg=T["fg3"],
            font=T["font_b"], relief="flat",
            padx=12, pady=8, state="disabled", command=self._cmd_pause)
        self._pause_btn.pack(side="left", padx=6)

        self._stop_btn = tk.Button(
            ctrl, text="⏹  Stop",
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
            ctrl, text="＋ Wait",
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

        self._thresh_var = tk.StringVar(
            value=str(_prefs.get("recorder_auto_wait_threshold", 1.5)))
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
            self, text="Idle — press Start Recording or use the overlay",
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
        sc = self._get_shortcuts()
        tip = (
            f"Tips:  Use the floating overlay to control recording without leaving your app.  "
            f"Double-clicks are detected automatically.  "
            f"Consecutive typed chars are merged into one Type step.  "
            f"Overlay clicks are NEVER recorded.  "
            f"Configured shortcuts ({sc['record']}/{sc['pause']}/{sc['stop']}) are NEVER recorded."
        )
        tk.Label(self, text=tip, bg=T["bg"], fg=T["fg3"],
                 font=T["font_s"], justify="left", wraplength=700, anchor="w"
                 ).pack(fill="x", padx=20, pady=(0, 10))

    # ── State machine ─────────────────────────────────────────────────────────

    def _transition(self, new_state: _State):
        self._state = new_state

        if new_state == _State.IDLE:
            self._state_badge.config(text="● IDLE",    fg=T["fg3"])
            self._status.config(     text="Idle — press Start Recording or use the overlay",
                                     fg=T["fg2"])
            self._rec_btn.config(    text="⏺  Start Recording",
                                     bg=T["red"], fg="white", state="normal")
            self._pause_btn.config(  text="⏸  Pause",
                                     bg=T["bg3"], fg=T["fg3"], state="disabled")
            self._stop_btn.config(   bg=T["bg3"], fg=T["fg3"], state="disabled")

        elif new_state == _State.RECORDING:
            self._state_badge.config(text="● REC",     fg=T["red"])
            self._status.config(     text="Recording…  ESC or Stop to finish", fg=T["red"])
            self._rec_btn.config(    text="⏺  Recording…",
                                     bg=T["bg4"], fg=T["red"], state="disabled")
            self._pause_btn.config(  text="⏸  Pause",
                                     bg=T["yellow"], fg=T["bg"], state="normal")
            self._stop_btn.config(   bg=T["bg3"], fg=T["fg2"], state="normal")

        elif new_state == _State.PAUSED:
            self._state_badge.config(text="⏸ PAUSED",  fg=T["yellow"])
            self._status.config(     text="Paused — press Resume to continue", fg=T["yellow"])
            self._rec_btn.config(    text="▶  Resume",
                                     bg=T["green"], fg="white", state="normal")
            self._pause_btn.config(  text="▶  Resume",
                                     bg=T["green"], fg="white", state="normal")
            self._stop_btn.config(   bg=T["bg3"], fg=T["fg2"], state="normal")

        has_steps = bool(self._steps)
        self._import_btn.config(state="normal" if has_steps else "disabled")

        # Always sync overlay
        self._sync_overlay_state()

    # ── Overlay toggle ────────────────────────────────────────────────────────

    def _toggle_overlay(self):
        if self._overlay and self._overlay.winfo_exists():
            self._close_overlay()
        else:
            self._open_overlay()

    # ── Command handlers ──────────────────────────────────────────────────────

    def _cmd_record(self):
        if self._state == _State.IDLE:
            self._start_listeners()
            self._last_action_t = time.time()
            self._transition(_State.RECORDING)
        elif self._state == _State.PAUSED:
            self._last_action_t = time.time()
            self._transition(_State.RECORDING)

    def _cmd_pause(self):
        if self._state == _State.RECORDING:
            self._flush_typed()
            self._transition(_State.PAUSED)
        elif self._state == _State.PAUSED:
            self._last_action_t = time.time()
            self._transition(_State.RECORDING)

    def _cmd_stop(self):
        if self._state in (_State.RECORDING, _State.PAUSED):
            self._flush_typed()
            self._stop_listeners()
            self._transition(_State.IDLE)
            n = len(self._steps)
            self._status.config(
                text=f"Stopped — {n} step(s) recorded.",
                fg=T["green"])

    def _cmd_add_wait(self):
        secs = float(_prefs.get("recorder_wait_default", 1.0))
        self._push({"type": "wait", "seconds": secs, "note": "", "enabled": True})

    # ── Shortcut helpers ──────────────────────────────────────────────────────

    def _get_shortcuts(self) -> dict:
        stored = _prefs.get("recorder_shortcuts", {})
        return {k: stored.get(k, v) for k, v in DEFAULT_RECORDER_SHORTCUTS.items()}

    def _shortcut_to_pynput_check(self, shortcut_str: str, key, held_mods: set) -> bool:
        """
        Return True if the current key event matches the given shortcut string.
        Shortcut string format examples: "F2", "Ctrl+F2", "Alt+F3"
        """
        sc = shortcut_str.strip()
        parts = [p.strip().lower() for p in sc.split("+")]
        if not parts:
            return False

        key_part  = parts[-1]
        mod_parts = set(parts[:-1])

        # Normalise held mods
        held_norm = {_MOD_NORM.get(m, m) for m in held_mods}

        # Check modifiers match
        if mod_parts != held_norm:
            return False

        # Check key
        key_name = _key_name(key)
        if key_name is None:
            return False

        return key_name.lower() == key_part.lower()

    def _is_recorder_shortcut(self, key) -> bool:
        """True if this key event is one of the configured recorder shortcuts."""
        sc = self._get_shortcuts()
        for action, shortcut_str in sc.items():
            if self._shortcut_to_pynput_check(shortcut_str, key, self._held_mods):
                return True
        return False

    # ── Global shortcut listener ──────────────────────────────────────────────

    def _bind_global_shortcuts(self):
        if not _PYNPUT_OK:
            return
        self._global_mods = set()

        def on_press(key):
            key_name_str = _key_name(key)
            if key_name_str in _MODIFIER_KEYS:
                self._global_mods.add(_MOD_NORM.get(key_name_str, key_name_str))
                return

            sc = self._get_shortcuts()
            for action, shortcut_str in sc.items():
                if self._shortcut_to_pynput_check(shortcut_str, key, self._global_mods):
                    if action == "record":
                        self.after(0, self._cmd_record)
                    elif action == "pause":
                        self.after(0, self._cmd_pause)
                    elif action == "stop":
                        self.after(0, self._cmd_stop)
                    elif action == "add_wait":
                        self.after(0, self._cmd_add_wait)
                    return

        def on_release(key):
            key_str = _key_name(key)
            norm    = _MOD_NORM.get(key_str or "", key_str or "")
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

    # ── Self-exclusion helper ─────────────────────────────────────────────────

    def _event_is_from_own_window(self, x: int, y: int) -> bool:
        """
        Returns True if the click (x, y) in screen coords falls within
        our own recorder window or the overlay window.
        We check bounding boxes of both windows.
        """
        for win in [self, self._overlay]:
            if win is None: continue
            try:
                if not win.winfo_exists(): continue
                wx = win.winfo_rootx()
                wy = win.winfo_rooty()
                ww = win.winfo_width()
                wh = win.winfo_height()
                if wx <= x <= wx + ww and wy <= y <= wy + wh:
                    return True
            except Exception:
                pass
        return False

    # ── pynput callbacks ──────────────────────────────────────────────────────

    def _on_click(self, x, y, button, pressed):
        if not pressed or self._state != _State.RECORDING:
            return

        # SELF-EXCLUSION: ignore clicks on our own windows
        if self._event_is_from_own_window(x, y):
            return

        from pynput.mouse import Button as _Btn

        now    = time.time()
        is_dbl = (
            now - self._last_click_t < float(_prefs.get("recorder_dbl_click_window", 0.35))
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

        # SHORTCUT EXCLUSION: if this key matches any recorder shortcut, skip it
        if self._is_recorder_shortcut(key):
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
        if not self._auto_wait_var.get():
            return
        if self._last_action_t == 0.0:
            return
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
        if not self._typed_buf:
            return
        text = "".join(self._typed_buf)
        self._typed_buf.clear()
        self._push({"type": "clip_type", "text": text, "note": "", "enabled": True})

    def _push(self, step: dict):
        with self._lock:
            self._steps.append(step)
        self.after(0, self._redraw_list)

    def _redraw_list(self):
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
        self._close_overlay()
        self.destroy()

    # ── Window close ─────────────────────────────────────────────────────────

    def _on_close(self):
        self._stop_listeners()
        if self._global_listener:
            try:
                self._global_listener.stop()
            except Exception:
                pass
        self._close_overlay()
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
#  _RecorderOverlay  — tiny always-on-top floating control panel
# ─────────────────────────────────────────────────────────────────────────────

class _RecorderOverlay(tk.Toplevel):
    """
    A compact floating overlay that stays on top of all windows.
    Shows Record / Pause / Stop / +Wait buttons and current state.
    Clicks on this window are NEVER recorded.
    """

    _BG = "#1a1f2b"
    _W  = 320
    _H  = 52

    def __init__(self, recorder: MacroRecorderPro):
        super().__init__(recorder)
        self._recorder = recorder

        self.overrideredirect(True)          # no title bar
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.93)
        self.configure(bg=self._BG)
        self.resizable(False, False)

        # Position: top-right corner of screen
        sw = self.winfo_screenwidth()
        self.geometry(f"{self._W}x{self._H}+{sw - self._W - 16}+16")

        self._build()
        self._make_draggable()

    def _build(self):
        # Thin colored top border (state indicator)
        self._top_bar = tk.Frame(self, bg=T["fg3"], height=3)
        self._top_bar.pack(fill="x")

        row = tk.Frame(self, bg=self._BG)
        row.pack(fill="both", expand=True, padx=6, pady=4)

        # State label
        self._state_lbl = tk.Label(
            row, text="⬤", bg=self._BG, fg=T["fg3"],
            font=("Segoe UI", 9))
        self._state_lbl.pack(side="left", padx=(2, 0))

        self._name_lbl = tk.Label(
            row, text="IDLE", bg=self._BG, fg=T["fg3"],
            font=("Segoe UI Semibold", 8), width=7, anchor="w")
        self._name_lbl.pack(side="left", padx=(2, 4))

        # Buttons
        def _btn(text, fg, tip, cmd, bg=None):
            b = tk.Button(row, text=text,
                          bg=bg or self._BG, fg=fg,
                          font=("Segoe UI Semibold", 9),
                          relief="flat", cursor="hand2",
                          padx=8, pady=2,
                          activebackground="#2a3040",
                          command=cmd)
            b.pack(side="left", padx=1)
            _add_tooltip(b, tip)
            return b

        self._rec_btn   = _btn("⏺ REC",   T["red"],    "Start / Resume recording",
                               self._recorder._cmd_record)
        self._pause_btn = _btn("⏸",       T["yellow"], "Pause / Resume",
                               self._recorder._cmd_pause)
        self._stop_btn  = _btn("⏹",       T["fg2"],    "Stop recording",
                               self._recorder._cmd_stop)
        self._wait_btn  = _btn("+Wait",    T["cyan"],   "Insert a Wait step",
                               self._recorder._cmd_add_wait)

        # Close overlay (not close recorder)
        tk.Button(row, text="✕", bg=self._BG, fg=T["fg3"],
                  font=("Segoe UI", 8), relief="flat", cursor="hand2",
                  padx=4, pady=2,
                  activebackground="#2a3040",
                  command=self._recorder._toggle_overlay
                  ).pack(side="right", padx=2)

        # Step counter
        self._count_lbl = tk.Label(
            row, text="0", bg=self._BG, fg=T["fg3"],
            font=("Consolas", 8))
        self._count_lbl.pack(side="right", padx=4)

        self.update_state(_State.IDLE)

    def update_state(self, state: _State):
        """Called by the recorder whenever state changes."""
        try:
            if state == _State.IDLE:
                self._top_bar.config(bg=T["fg3"])
                self._state_lbl.config(fg=T["fg3"])
                self._name_lbl.config(text="IDLE", fg=T["fg3"])
                self._rec_btn.config(state="normal", bg=self._BG)
                self._pause_btn.config(state="disabled")
                self._stop_btn.config(state="disabled")
            elif state == _State.RECORDING:
                self._top_bar.config(bg=T["red"])
                self._state_lbl.config(fg=T["red"])
                self._name_lbl.config(text="REC", fg=T["red"])
                self._rec_btn.config(state="disabled", bg=self._BG)
                self._pause_btn.config(state="normal")
                self._stop_btn.config(state="normal")
            elif state == _State.PAUSED:
                self._top_bar.config(bg=T["yellow"])
                self._state_lbl.config(fg=T["yellow"])
                self._name_lbl.config(text="PAUSED", fg=T["yellow"])
                self._rec_btn.config(state="normal", bg=self._BG)
                self._pause_btn.config(state="normal")
                self._stop_btn.config(state="normal")

            # Update step count from recorder
            n = len(self._recorder._steps)
            self._count_lbl.config(text=f"{n} steps" if n else "")
        except Exception:
            pass

    def _make_draggable(self):
        """Allow dragging the overlay by its body."""
        self._drag_x = 0
        self._drag_y = 0

        def _start(e):
            self._drag_x = e.x_root - self.winfo_x()
            self._drag_y = e.y_root - self.winfo_y()

        def _drag(e):
            x = e.x_root - self._drag_x
            y = e.y_root - self._drag_y
            self.geometry(f"+{x}+{y}")

        for w in [self] + list(self.winfo_children()):
            try:
                w.bind("<ButtonPress-1>", _start, add="+")
                w.bind("<B1-Motion>",     _drag,  add="+")
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
#  Settings section helpers (called from settings_panel.py)
# ─────────────────────────────────────────────────────────────────────────────

def validate_recorder_shortcut(shortcut_str: str) -> tuple[bool, str]:
    """
    Returns (is_valid, error_message).
    Rejects known Windows system shortcuts.
    """
    sc = shortcut_str.strip().lower()
    # Normalise: "Control+F2" → "ctrl+f2"
    sc = sc.replace("control", "ctrl").replace("control_l", "ctrl").replace("control_r", "ctrl")
    if sc in _WINDOWS_SYSTEM_SHORTCUTS:
        return False, f"'{shortcut_str}' conflicts with a Windows system shortcut."
    # Reject pure modifier-only combos
    parts = [p.strip() for p in sc.split("+")]
    if all(p in {"ctrl", "shift", "alt", "win", "super"} for p in parts):
        return False, "Shortcut must include a non-modifier key (e.g. F2, A, 1)."
    return True, ""


def get_recorder_shortcut_defaults() -> dict:
    return dict(DEFAULT_RECORDER_SHORTCUTS)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _key_name(key) -> str | None:
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
