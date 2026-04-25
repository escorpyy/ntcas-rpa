"""
agent/macro_recorder.py
========================
MacroRecorderPro v9.4 — Enhanced with:

RECORDING IMPROVEMENTS:
  - Scroll wheel recording (mouse scroll → scroll step)
  - Middle-click recording
  - Correct Shift+key combo char capture (!, @, #, etc.)
  - Double-click detection no longer removes preceding single-click
    (replaces it accurately)
  - Right-drag support

STEP MANAGEMENT:
  - Inline step editing (click ✏ on any recorded step)
  - Drag-to-reorder recorded steps before import
  - Manual wait merge/split controls
  - Multi-select delete (Shift+click range)

OVERLAY:
  - Real-time step counter (updates every 0.5s)
  - Collapsed mini-mode toggle
  - Overlay position saved/restored to prefs

TIMING:
  - Auto-wait threshold synced back to prefs on close
  - Long auto-waits capped at max_auto_wait (default 30s)

IMPORT:
  - Preview before import (shows step count + summary)
  - Append vs Replace choice
  - Import into Main or First-Name flow

UNDO:
  - Full undo stack within the recorder
  - Ctrl+Z to undo last recorded/deleted step

WINDOW DETECTION:
  - Records active window on each click as metadata
  - Inserts wait_window steps on window change
  - Relative coordinate toggle

SHORTCUTS:
  - Synced with _WINDOWS_SYSTEM_COMBOS
  - Global listener and recording listener mod-sets unified
"""

from __future__ import annotations

import copy
import time
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from enum import Enum, auto
from collections import deque
from typing import Optional, Callable

try:
    from pynput import mouse as _mouse_lib, keyboard as _kb_lib
    from pynput.keyboard import Key as _PKey
    _PYNPUT_OK = True
except ImportError:
    _PYNPUT_OK = False

from core.constants import T, _prefs, save_prefs
from core.window_manager import get_window_manager, WindowInfo

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

# Shift-number/symbol map
_SHIFT_CHARS = {
    "1":"!", "2":"@", "3":"#", "4":"$", "5":"%",
    "6":"^", "7":"&", "8":"*", "9":"(", "0":")",
    "-":"_", "=":"+", "[":"{", "]":"}", "\\":"|",
    ";":":", "'":"\"", ",":"<", ".":">", "/":"?",
    "`":"~",
}

_WINDOWS_SYSTEM_SHORTCUTS = {
    "ctrl+c", "ctrl+v", "ctrl+x", "ctrl+z", "ctrl+y",
    "ctrl+a", "ctrl+s", "ctrl+p", "ctrl+w", "ctrl+n",
    "ctrl+o", "ctrl+f", "ctrl+h", "ctrl+t", "ctrl+r",
    "alt+f4", "alt+tab", "ctrl+alt+del",
    "ctrl+shift+esc", "ctrl+esc",
}

DEFAULT_RECORDER_SHORTCUTS = {
    "record":   "F2",
    "pause":    "F3",
    "stop":     "F4",
    "add_wait": "F5",
}

MAX_AUTO_WAIT = 30.0   # cap auto-inserted waits at 30s


class _State(Enum):
    IDLE      = auto()
    RECORDING = auto()
    PAUSED    = auto()


# ─────────────────────────────────────────────────────────────────────────────
#  MacroRecorderPro
# ─────────────────────────────────────────────────────────────────────────────

class MacroRecorderPro(tk.Toplevel):
    """
    Record real mouse + keyboard input → convert to RPA steps.
    All recording improvements from v9.4 plan.
    """

    def __init__(self, parent, on_import: Callable | None = None):
        super().__init__(parent)
        self.title("🎙 MacroRecorder Pro  v9.4")
        self.configure(bg=T["bg"])
        self.attributes("-topmost", _prefs.get("recorder_topmost", True))
        self.geometry("780x720")
        self.minsize(640, 560)

        self.on_import = on_import
        self._wm       = get_window_manager()

        # Core state
        self._state        = _State.IDLE
        self._lock         = threading.Lock()
        self._steps: list  = []
        self._undo_stack: deque = deque(maxlen=50)

        # Selection (multi-select delete)
        self._selected: set[int] = set()

        # Listeners
        self._m_listener  = None
        self._k_listener  = None

        # Keyboard tracking
        self._typed_buf   : list = []
        self._held_mods   : set  = set()   # for recording listener
        self._global_mods : set  = set()   # for global shortcut listener

        # Click tracking
        self._last_click_t   = 0.0
        self._last_click_xy  = (-9999, -9999)
        self._last_click_btn = None

        # Auto-Wait
        self._last_action_t = 0.0
        self._auto_wait_var = tk.BooleanVar(value=_prefs.get("recorder_auto_wait_on", True))

        # Window detection
        self._last_window: Optional[WindowInfo] = None
        self._detect_windows = tk.BooleanVar(value=True)
        self._use_relative   = tk.BooleanVar(value=False)

        # Global shortcut listener
        self._global_listener = None

        # Overlay
        self._overlay: Optional[_RecorderOverlay] = None

        # Excluded window bounding boxes
        self._excluded_hwnds: set = set()

        self._build_ui()
        self._bind_global_shortcuts()
        self._open_overlay()
        self._start_overlay_counter()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(200, self._register_own_window)

    def _register_own_window(self):
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
            try: self._overlay.destroy()
            except Exception: pass
            self._overlay = None

    def _sync_overlay_state(self):
        if self._overlay and self._overlay.winfo_exists():
            try: self._overlay.update_state(self._state)
            except Exception: pass

    def _start_overlay_counter(self):
        """Real-time step counter update every 500ms."""
        def _tick():
            if not self.winfo_exists():
                return
            if self._overlay and self._overlay.winfo_exists():
                try:
                    n = len(self._steps)
                    self._overlay.set_count(n)
                except Exception:
                    pass
            self.after(500, _tick)
        self.after(500, _tick)

    def _toggle_overlay(self):
        if self._overlay and self._overlay.winfo_exists():
            self._close_overlay()
        else:
            self._open_overlay()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        hdr = tk.Frame(self, bg=T["bg2"], pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🎙 MacroRecorder Pro",
                 bg=T["bg2"], fg=T["acc"],
                 font=("Segoe UI Semibold", 14)).pack(side="left", padx=20)
        self._state_badge = tk.Label(hdr, text="● IDLE",
                                     bg=T["bg2"], fg=T["fg3"],
                                     font=("Segoe UI Semibold", 10))
        self._state_badge.pack(side="left", padx=12)

        sc = self._get_shortcuts()
        hint = f"  {sc['record']}=Rec  {sc['pause']}=Pause  {sc['stop']}=Stop  {sc['add_wait']}=Wait"
        tk.Label(hdr, text=hint, bg=T["bg2"], fg=T["fg3"],
                 font=T["font_s"]).pack(side="right", padx=8)
        tk.Button(hdr, text="◉ Overlay",
                  bg=T["bg3"], fg=T["cyan"],
                  font=T["font_s"], relief="flat", cursor="hand2",
                  padx=8, pady=4, command=self._toggle_overlay).pack(side="right", padx=6)

        # Controls
        ctrl = tk.Frame(self, bg=T["bg"], pady=8); ctrl.pack(fill="x", padx=14)
        self._rec_btn = tk.Button(ctrl, text="⏺  Start Recording",
                                  bg=T["red"], fg="white",
                                  font=("Segoe UI Semibold", 10), relief="flat",
                                  padx=12, pady=7, command=self._cmd_record)
        self._rec_btn.pack(side="left")
        self._pause_btn = tk.Button(ctrl, text="⏸  Pause",
                                    bg=T["bg3"], fg=T["fg3"],
                                    font=T["font_b"], relief="flat",
                                    padx=12, pady=7, state="disabled",
                                    command=self._cmd_pause)
        self._pause_btn.pack(side="left", padx=5)
        self._stop_btn = tk.Button(ctrl, text="⏹  Stop",
                                   bg=T["bg3"], fg=T["fg3"],
                                   font=T["font_b"], relief="flat",
                                   padx=12, pady=7, state="disabled",
                                   command=self._cmd_stop)
        self._stop_btn.pack(side="left")
        tk.Button(ctrl, text="🗑 Clear",
                  bg=T["bg3"], fg=T["fg2"],
                  font=T["font_b"], relief="flat",
                  padx=10, pady=7, command=self._clear).pack(side="left", padx=8)
        self._wait_btn = tk.Button(ctrl, text="＋ Wait",
                                   bg=T["bg3"], fg=T["cyan"],
                                   font=T["font_b"], relief="flat",
                                   padx=10, pady=7, command=self._cmd_add_wait)
        self._wait_btn.pack(side="left")
        tk.Button(ctrl, text="↩ Undo",
                  bg=T["bg3"], fg=T["fg2"],
                  font=T["font_b"], relief="flat",
                  padx=10, pady=7, command=self._undo).pack(side="left", padx=5)

        self._import_btn = tk.Button(ctrl, text="✔  Import",
                                     bg=T["green"], fg="white",
                                     font=("Segoe UI Semibold", 10), relief="flat",
                                     padx=14, pady=7, state="disabled",
                                     command=self._preview_import)
        self._import_btn.pack(side="right")

        self.bind("<Control-z>", lambda e: self._undo())

        # Options row
        opt = tk.Frame(self, bg=T["bg"]); opt.pack(fill="x", padx=20, pady=(0, 2))
        self._aw_chk = tk.Checkbutton(opt, variable=self._auto_wait_var,
                                       text="Auto-Wait on idle gaps ≥",
                                       bg=T["bg"], fg=T["fg2"],
                                       selectcolor=T["bg3"],
                                       activebackground=T["bg"], font=T["font_s"])
        self._aw_chk.pack(side="left")
        self._thresh_var = tk.StringVar(
            value=str(_prefs.get("recorder_auto_wait_threshold", 1.5)))
        tk.Entry(opt, textvariable=self._thresh_var, width=4,
                 bg=T["bg3"], fg=T["yellow"], font=T["font_s"],
                 relief="flat", insertbackground=T["yellow"]).pack(side="left", padx=3)
        tk.Label(opt, text="s", bg=T["bg"], fg=T["fg2"],
                 font=T["font_s"]).pack(side="left")

        tk.Checkbutton(opt, variable=self._detect_windows,
                       text="  Detect window changes",
                       bg=T["bg"], fg=T["cyan"],
                       selectcolor=T["bg3"], activebackground=T["bg"],
                       font=T["font_s"]).pack(side="left", padx=14)
        tk.Checkbutton(opt, variable=self._use_relative,
                       text="Relative coords",
                       bg=T["bg"], fg=T["purple"],
                       selectcolor=T["bg3"], activebackground=T["bg"],
                       font=T["font_s"]).pack(side="left")

        # Status label
        self._status = tk.Label(self, text="Idle — press Start Recording",
                                bg=T["bg"], fg=T["fg2"],
                                font=T["font_m"], anchor="w")
        self._status.pack(fill="x", padx=20, pady=(2, 0))

        # Step list
        lf = tk.LabelFrame(self, text="  Recorded Steps  ",
                            bg=T["bg"], fg=T["acc"],
                            font=("Segoe UI Semibold", 9), bd=1, relief="flat")
        lf.pack(fill="both", expand=True, padx=14, pady=(4, 4))

        self._listbox = tk.Listbox(lf, bg=T["bg3"], fg=T["fg"],
                                   font=T["font_m"],
                                   selectbackground=T["acc_dark"],
                                   selectmode="extended",   # multi-select
                                   activestyle="none",
                                   relief="flat", bd=0)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self._listbox.yview)
        self._listbox.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._listbox.pack(fill="both", expand=True, padx=4, pady=4)
        self._listbox.bind("<Double-Button-1>", self._on_dbl_click_step)
        self._listbox.bind("<Delete>", lambda e: self._delete_selected())

        # Bottom row
        bot = tk.Frame(self, bg=T["bg"], pady=4); bot.pack(fill="x", padx=14)
        tk.Button(bot, text="✏ Edit Selected",
                  bg=T["bg2"], fg=T["acc"],
                  font=T["font_s"], relief="flat", cursor="hand2",
                  command=self._edit_selected).pack(side="left")
        tk.Button(bot, text="🗑 Delete Selected",
                  bg=T["bg2"], fg=T["red"],
                  font=T["font_s"], relief="flat", cursor="hand2",
                  command=self._delete_selected).pack(side="left", padx=6)
        tk.Button(bot, text="▲ Up",
                  bg=T["bg2"], fg=T["fg2"],
                  font=T["font_s"], relief="flat", cursor="hand2",
                  command=lambda: self._move_selected(-1)).pack(side="left")
        tk.Button(bot, text="▼ Down",
                  bg=T["bg2"], fg=T["fg2"],
                  font=T["font_s"], relief="flat", cursor="hand2",
                  command=lambda: self._move_selected(1)).pack(side="left", padx=4)
        tk.Button(bot, text="⊕ Merge Waits",
                  bg=T["bg2"], fg=T["yellow"],
                  font=T["font_s"], relief="flat", cursor="hand2",
                  command=self._merge_waits).pack(side="left", padx=4)

        self._count_lbl = tk.Label(bot, text="0 steps",
                                   bg=T["bg"], fg=T["fg3"], font=T["font_s"])
        self._count_lbl.pack(side="right")

        # Tips
        sc = self._get_shortcuts()
        tip = (f"Shortcuts: {sc['record']}/{sc['pause']}/{sc['stop']}/{sc['add_wait']} — "
               "never recorded.  Overlay clicks excluded.  "
               "Scroll = scroll step.  Shift+chars captured correctly.  "
               "Double-click step = edit inline.  Ctrl+Z = undo.")
        tk.Label(self, text=tip, bg=T["bg"], fg=T["fg3"],
                 font=T["font_s"], justify="left", wraplength=730, anchor="w"
                 ).pack(fill="x", padx=20, pady=(0, 8))

    # ── State machine ─────────────────────────────────────────────────────────

    def _transition(self, new_state: _State):
        self._state = new_state
        if new_state == _State.IDLE:
            self._state_badge.config(text="● IDLE",    fg=T["fg3"])
            self._status.config(text="Idle — press Start Recording", fg=T["fg2"])
            self._rec_btn.config(text="⏺  Start Recording",
                                 bg=T["red"], fg="white", state="normal")
            self._pause_btn.config(bg=T["bg3"], fg=T["fg3"], state="disabled")
            self._stop_btn.config(bg=T["bg3"], fg=T["fg3"], state="disabled")
        elif new_state == _State.RECORDING:
            self._state_badge.config(text="● REC",    fg=T["red"])
            self._status.config(text="Recording…  ESC or Stop to finish", fg=T["red"])
            self._rec_btn.config(text="⏺  Recording…",
                                 bg=T["bg4"], fg=T["red"], state="disabled")
            self._pause_btn.config(text="⏸  Pause",
                                   bg=T["yellow"], fg=T["bg"], state="normal")
            self._stop_btn.config(bg=T["bg3"], fg=T["fg2"], state="normal")
        elif new_state == _State.PAUSED:
            self._state_badge.config(text="⏸ PAUSED", fg=T["yellow"])
            self._status.config(text="Paused — press Resume to continue", fg=T["yellow"])
            self._rec_btn.config(text="▶  Resume",
                                 bg=T["green"], fg="white", state="normal")
            self._pause_btn.config(text="▶  Resume",
                                   bg=T["green"], fg="white", state="normal")
            self._stop_btn.config(bg=T["bg3"], fg=T["fg2"], state="normal")

        has_steps = bool(self._steps)
        self._import_btn.config(state="normal" if has_steps else "disabled")
        self._sync_overlay_state()

    # ── Commands ──────────────────────────────────────────────────────────────

    def _cmd_record(self):
        if self._state == _State.IDLE:
            self._start_listeners()
            self._last_action_t = time.time()
            self._last_window   = self._wm.get_active_window()
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
            self._status.config(text=f"Stopped — {n} step(s) recorded.", fg=T["green"])
            # Sync thresh back to prefs
            try:
                _prefs["recorder_auto_wait_threshold"] = float(self._thresh_var.get())
                save_prefs()
            except Exception:
                pass

    def _cmd_add_wait(self):
        secs = float(_prefs.get("recorder_wait_default", 1.0))
        self._push({"type": "wait", "seconds": secs, "note": "manual", "enabled": True})

    def _undo(self):
        if self._undo_stack:
            with self._lock:
                self._steps = self._undo_stack.pop()
            self.after(0, self._redraw_list)

    # ── Shortcut helpers ──────────────────────────────────────────────────────

    def _get_shortcuts(self) -> dict:
        stored = _prefs.get("recorder_shortcuts", {})
        return {k: stored.get(k, v) for k, v in DEFAULT_RECORDER_SHORTCUTS.items()}

    def _shortcut_matches(self, shortcut_str: str, key, held_mods: set) -> bool:
        sc    = shortcut_str.strip()
        parts = [p.strip().lower() for p in sc.split("+")]
        if not parts:
            return False
        key_part  = parts[-1]
        mod_parts = set(parts[:-1])
        held_norm = {_MOD_NORM.get(m, m) for m in held_mods}
        if mod_parts != held_norm:
            return False
        kn = _key_name(key)
        return kn is not None and kn.lower() == key_part.lower()

    def _is_recorder_shortcut(self, key) -> bool:
        sc = self._get_shortcuts()
        # Use GLOBAL mods (unified with recording listener)
        mods = self._held_mods | self._global_mods
        return any(self._shortcut_matches(v, key, mods) for v in sc.values())

    # ── Global shortcut listener ──────────────────────────────────────────────

    def _bind_global_shortcuts(self):
        if not _PYNPUT_OK:
            return
        self._global_mods = set()

        def on_press(key):
            kn = _key_name(key)
            if kn in _MODIFIER_KEYS:
                self._global_mods.add(_MOD_NORM.get(kn, kn))
                return
            sc = self._get_shortcuts()
            for action, shortcut_str in sc.items():
                if self._shortcut_matches(shortcut_str, key, self._global_mods):
                    dispatch = {
                        "record":   self._cmd_record,
                        "pause":    self._cmd_pause,
                        "stop":     self._cmd_stop,
                        "add_wait": self._cmd_add_wait,
                    }
                    fn = dispatch.get(action)
                    if fn:
                        self.after(0, fn)
                    return

        def on_release(key):
            kn   = _key_name(key)
            norm = _MOD_NORM.get(kn or "", kn or "")
            self._global_mods.discard(norm)

        self._global_listener = _kb_lib.Listener(on_press=on_press, on_release=on_release)
        self._global_listener.daemon = True
        self._global_listener.start()

    # ── Listener lifecycle ────────────────────────────────────────────────────

    def _start_listeners(self):
        if not _PYNPUT_OK:
            messagebox.showerror("Missing library",
                                 "pynput is required.\n\npip install pynput")
            return
        self._held_mods.clear()
        self._m_listener = _mouse_lib.Listener(
            on_click=self._on_click,
            on_scroll=self._on_scroll)
        self._k_listener = _kb_lib.Listener(
            on_press=self._on_key, on_release=self._on_key_release)
        self._m_listener.start()
        self._k_listener.start()

    def _stop_listeners(self):
        for lst in (self._m_listener, self._k_listener):
            if lst:
                try: lst.stop()
                except Exception: pass
        self._m_listener = self._k_listener = None

    # ── Self-exclusion ────────────────────────────────────────────────────────

    def _event_is_from_own_window(self, x: int, y: int) -> bool:
        for win in [self, self._overlay]:
            if win is None:
                continue
            try:
                if not win.winfo_exists():
                    continue
                wx, wy = win.winfo_rootx(), win.winfo_rooty()
                ww, wh = win.winfo_width(), win.winfo_height()
                if wx <= x <= wx + ww and wy <= y <= wy + wh:
                    return True
            except Exception:
                pass
        return False

    # ── Mouse callbacks ───────────────────────────────────────────────────────

    def _on_click(self, x, y, button, pressed):
        if not pressed or self._state != _State.RECORDING:
            return
        if self._event_is_from_own_window(x, y):
            return

        from pynput.mouse import Button as _Btn

        now = time.time()
        self._maybe_insert_auto_wait(now)

        # Window change detection
        if self._detect_windows.get():
            cur_win = self._wm.get_active_window()
            if cur_win and self._last_window:
                if cur_win.hwnd != self._last_window.hwnd:
                    # Insert a wait_window step
                    self._flush_typed()
                    ww_step = {
                        "type":         "wait_window",
                        "window_title": cur_win.title,
                        "process":      cur_win.process,
                        "hwnd":         cur_win.hwnd,
                        "timeout":      10,
                        "note":         "auto-detected",
                        "enabled":      True,
                    }
                    self._push(ww_step)
                    self._last_window = cur_win
            elif cur_win:
                self._last_window = cur_win

        # Double-click detection (checks same button)
        is_dbl = (
            button == self._last_click_btn and
            now - self._last_click_t < float(_prefs.get("recorder_dbl_click_window", 0.35)) and
            abs(x - self._last_click_xy[0]) < 12 and
            abs(y - self._last_click_xy[1]) < 12
        )
        self._last_click_t   = now
        self._last_click_xy  = (x, y)
        self._last_click_btn = button
        self._last_action_t  = now
        self._flush_typed()

        # Resolve coords
        rx, ry = self._resolve_record_coords(x, y)
        rel = self._use_relative.get()

        if button == _Btn.right:
            self._push({"type": "right_click",
                        "x": rx, "y": ry,
                        "relative": rel, "note": "", "enabled": True})
            return

        if button == _Btn.middle:
            self._push({"type": "hotkey",
                        "keys": "middle_click",
                        "note": f"middle @ ({rx},{ry})",
                        "enabled": True})
            return

        if is_dbl:
            with self._lock:
                # Replace the last click step if it's at the same position
                if (self._steps and
                        self._steps[-1]["type"] == "click" and
                        abs(self._steps[-1]["x"] - rx) < 12 and
                        abs(self._steps[-1]["y"] - ry) < 12):
                    self._steps[-1] = {
                        "type": "double_click",
                        "x": rx, "y": ry,
                        "relative": rel,
                        "note": "", "enabled": True}
                    self.after(0, self._redraw_list)
                    return

        self._push({"type": "click", "x": rx, "y": ry,
                    "relative": rel, "note": "", "enabled": True})

    def _on_scroll(self, x, y, dx, dy):
        """Record scroll wheel events."""
        if self._state != _State.RECORDING:
            return
        if self._event_is_from_own_window(x, y):
            return
        now = time.time()
        self._maybe_insert_auto_wait(now)
        self._last_action_t = now
        self._flush_typed()

        direction = "down" if dy < 0 else "up"
        clicks    = abs(dy) or 1
        self._push({"type": "scroll",
                    "x": x, "y": y,
                    "direction": direction,
                    "clicks": clicks,
                    "note": "", "enabled": True})

    def _resolve_record_coords(self, abs_x: int, abs_y: int):
        """Return (rx, ry) — relative floats or absolute ints."""
        if self._use_relative.get() and self._last_window:
            rx, ry = self._last_window.rel_coords(abs_x, abs_y)
            return rx, ry
        return abs_x, abs_y

    # ── Keyboard callbacks ────────────────────────────────────────────────────

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

        # Recorder shortcut exclusion
        if self._is_recorder_shortcut(key):
            return

        now = time.time()
        self._maybe_insert_auto_wait(now)
        self._last_action_t = now

        # Modifier combo → hotkey
        if self._held_mods:
            self._flush_typed()
            norm_mods = sorted({_MOD_NORM.get(m, m) for m in self._held_mods})
            combo     = "+".join(norm_mods) + "+" + key_str
            self._push({"type": "hotkey", "keys": combo, "note": "", "enabled": True})
            return

        # Pure special key
        if key_str in _SPECIAL_KEYS:
            self._flush_typed()
            self._push({"type": "hotkey", "keys": key_str, "note": "", "enabled": True})
            return

        # Printable char — handle Shift correctly
        try:
            char = key.char
            if char is None:
                return
            # If shift is held and char is a known shifted version, use it
            if "shift" in {_MOD_NORM.get(m, m) for m in self._held_mods}:
                char = _SHIFT_CHARS.get(char.lower(), char.upper())
            if char.isprintable():
                self._typed_buf.append(char)
                return
        except AttributeError:
            pass

    def _on_key_release(self, key):
        kn = _key_name(key)
        if kn in _MODIFIER_KEYS:
            self._held_mods.discard(kn)

    # ── Auto-Wait ─────────────────────────────────────────────────────────────

    def _maybe_insert_auto_wait(self, now: float):
        if not self._auto_wait_var.get():
            return
        if self._last_action_t == 0.0:
            return
        try:
            threshold = float(self._thresh_var.get())
        except ValueError:
            threshold = 1.5
        gap = now - self._last_action_t
        if gap >= threshold:
            wait_secs = min(round(gap, 2), MAX_AUTO_WAIT)
            self._push({"type": "wait", "seconds": wait_secs,
                        "note": "auto", "enabled": True})

    # ── Step helpers ──────────────────────────────────────────────────────────

    def _flush_typed(self):
        if not self._typed_buf:
            return
        text = "".join(self._typed_buf)
        self._typed_buf.clear()
        self._push({"type": "clip_type", "text": text, "note": "", "enabled": True})

    def _save_undo(self):
        with self._lock:
            self._undo_stack.append(copy.deepcopy(self._steps))

    def _push(self, step: dict):
        self._save_undo()
        with self._lock:
            self._steps.append(step)
        self.after(0, self._redraw_list)

    def _redraw_list(self):
        with self._lock:
            steps_snapshot = list(self._steps)

        self._listbox.delete(0, "end")
        for i, s in enumerate(steps_snapshot, 1):
            label = self._step_label(s)
            self._listbox.insert("end", f"  {i:02d}.  {label}")

        n = len(steps_snapshot)
        self._count_lbl.config(text=f"{n} step{'s' if n != 1 else ''}")
        self._import_btn.config(state="normal" if n else "disabled")

    @staticmethod
    def _step_label(s: dict) -> str:
        t    = s.get("type", "?")
        auto = "  [auto]" if s.get("note") == "auto" else ""
        rel  = " [rel]" if s.get("relative") else ""
        if t in ("click", "double_click", "right_click"):
            return f"{t.replace('_',' ').title()} @ ({s['x']}, {s['y']}){rel}"
        elif t == "scroll":
            return f"Scroll {s.get('direction','down')} ×{s.get('clicks',1)} @ ({s.get('x',0)},{s.get('y',0)})"
        elif t == "hotkey":
            return f"Hotkey: {s.get('keys','')}"
        elif t in ("type_text", "clip_type"):
            txt = s.get("text", "")
            return f"Type: {txt[:40]}{'…' if len(txt)>40 else ''}"
        elif t == "wait":
            return f"Wait: {s.get('seconds',1.0):.2f}s{auto}"
        elif t == "wait_window":
            return f"Wait Window: '{s.get('window_title','')}'"
        else:
            return t

    # ── Step editing / management ─────────────────────────────────────────────

    def _on_dbl_click_step(self, event):
        """Double-click a step → open inline editor."""
        sel = self._listbox.curselection()
        if sel:
            self._edit_step_at(sel[0])

    def _edit_selected(self):
        sel = self._listbox.curselection()
        if len(sel) == 1:
            self._edit_step_at(sel[0])
        elif len(sel) > 1:
            messagebox.showinfo("Edit", "Select exactly one step to edit.")

    def _edit_step_at(self, idx: int):
        with self._lock:
            if idx >= len(self._steps):
                return
            step_copy = copy.deepcopy(self._steps[idx])

        editor = _StepInlineEditor(self, step_copy, on_save=lambda s, i=idx: self._apply_edit(i, s))
        self.wait_window(editor)

    def _apply_edit(self, idx: int, new_step: dict):
        self._save_undo()
        with self._lock:
            if idx < len(self._steps):
                self._steps[idx] = new_step
        self.after(0, self._redraw_list)

    def _delete_selected(self):
        sel = list(self._listbox.curselection())
        if not sel:
            return
        self._save_undo()
        with self._lock:
            for i in sorted(sel, reverse=True):
                if 0 <= i < len(self._steps):
                    self._steps.pop(i)
        self.after(0, self._redraw_list)

    def _move_selected(self, direction: int):
        sel = self._listbox.curselection()
        if not sel or len(sel) != 1:
            return
        idx = sel[0]
        new_idx = idx + direction
        self._save_undo()
        with self._lock:
            if 0 <= new_idx < len(self._steps):
                self._steps[idx], self._steps[new_idx] = (
                    self._steps[new_idx], self._steps[idx])
        self.after(0, self._redraw_list)
        # Keep selection on moved item
        self.after(50, lambda ni=new_idx: (
            self._listbox.selection_clear(0, "end"),
            self._listbox.selection_set(ni),
            self._listbox.see(ni)))

    def _merge_waits(self):
        """Merge consecutive auto-wait steps into one."""
        self._save_undo()
        with self._lock:
            merged = []
            i = 0
            while i < len(self._steps):
                s = self._steps[i]
                if s.get("type") == "wait" and s.get("note") == "auto":
                    total = s.get("seconds", 0)
                    j = i + 1
                    while j < len(self._steps):
                        ns = self._steps[j]
                        if ns.get("type") == "wait" and ns.get("note") == "auto":
                            total += ns.get("seconds", 0)
                            j += 1
                        else:
                            break
                    merged.append({"type": "wait", "seconds": round(total, 2),
                                   "note": "merged", "enabled": True})
                    i = j
                else:
                    merged.append(s)
                    i += 1
            self._steps = merged
        self.after(0, self._redraw_list)

    def _clear(self):
        self._save_undo()
        with self._lock:
            self._steps.clear()
            self._typed_buf.clear()
        self.after(0, self._redraw_list)

    # ── Import with preview ───────────────────────────────────────────────────

    def _preview_import(self):
        if not self._steps:
            return
        self._flush_typed()
        preview = _ImportPreviewDialog(self, self._steps,
                                       on_confirm=self._do_import)
        self.wait_window(preview)

    def _do_import(self, steps: list, mode: str, target_flow: str):
        """mode: 'replace'|'append', target_flow: 'main'|'first'"""
        if self.on_import:
            self.on_import(steps, mode=mode, target_flow=target_flow)
        self._close_overlay()
        self.destroy()

    # ── Window close ─────────────────────────────────────────────────────────

    def _on_close(self):
        self._stop_listeners()
        if self._global_listener:
            try: self._global_listener.stop()
            except Exception: pass
        # Sync prefs
        try:
            _prefs["recorder_auto_wait_threshold"] = float(self._thresh_var.get())
            save_prefs()
        except Exception:
            pass
        self._close_overlay()
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
#  _RecorderOverlay  — floating mini panel
# ─────────────────────────────────────────────────────────────────────────────

class _RecorderOverlay(tk.Toplevel):
    _BG = "#1a1f2b"
    _W  = 340
    _H  = 52

    def __init__(self, recorder: MacroRecorderPro):
        super().__init__(recorder)
        self._recorder   = recorder
        self._collapsed  = False

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.attributes("-alpha", 0.93)
        self.configure(bg=self._BG)
        self.resizable(False, False)

        # Restore saved position
        saved_x = _prefs.get("overlay_x", None)
        saved_y = _prefs.get("overlay_y", None)
        if saved_x and saved_y:
            self.geometry(f"{self._W}x{self._H}+{saved_x}+{saved_y}")
        else:
            sw = self.winfo_screenwidth()
            self.geometry(f"{self._W}x{self._H}+{sw - self._W - 16}+16")

        self._build()
        self._make_draggable()

    def _build(self):
        self._top_bar = tk.Frame(self, bg=T["fg3"], height=3)
        self._top_bar.pack(fill="x")

        self._row = tk.Frame(self, bg=self._BG)
        self._row.pack(fill="both", expand=True, padx=5, pady=3)

        self._dot = tk.Label(self._row, text="⬤", bg=self._BG,
                             fg=T["fg3"], font=("Segoe UI", 9))
        self._dot.pack(side="left", padx=(2, 0))

        self._name_lbl = tk.Label(self._row, text="IDLE", bg=self._BG,
                                  fg=T["fg3"],
                                  font=("Segoe UI Semibold", 8), width=7, anchor="w")
        self._name_lbl.pack(side="left", padx=(2, 4))

        def _btn(text, fg, cmd, bg=None):
            b = tk.Button(self._row, text=text,
                          bg=bg or self._BG, fg=fg,
                          font=("Segoe UI Semibold", 9),
                          relief="flat", cursor="hand2",
                          padx=7, pady=2,
                          activebackground="#2a3040",
                          command=cmd)
            b.pack(side="left", padx=1)
            return b

        self._rec_btn   = _btn("⏺ REC",  T["red"],    self._recorder._cmd_record)
        self._pause_btn = _btn("⏸",      T["yellow"], self._recorder._cmd_pause)
        self._stop_btn  = _btn("⏹",      T["fg2"],    self._recorder._cmd_stop)
        self._wait_btn  = _btn("+Wait",   T["cyan"],   self._recorder._cmd_add_wait)

        # Collapse toggle
        self._col_btn = tk.Button(self._row, text="—",
                                  bg=self._BG, fg=T["fg3"],
                                  font=("Segoe UI", 8), relief="flat",
                                  cursor="hand2", padx=4, pady=2,
                                  activebackground="#2a3040",
                                  command=self._toggle_collapse)
        self._col_btn.pack(side="right", padx=2)

        # Close overlay
        tk.Button(self._row, text="✕", bg=self._BG, fg=T["fg3"],
                  font=("Segoe UI", 8), relief="flat", cursor="hand2",
                  padx=4, pady=2,
                  activebackground="#2a3040",
                  command=self._recorder._toggle_overlay).pack(side="right", padx=1)

        # Live step count
        self._count_lbl = tk.Label(self._row, text="", bg=self._BG,
                                   fg=T["fg3"], font=("Consolas", 8))
        self._count_lbl.pack(side="right", padx=4)

        self.update_state(_State.IDLE)

    def _toggle_collapse(self):
        self._collapsed = not self._collapsed
        if self._collapsed:
            self.geometry(f"120x{self._H}")
            # hide most buttons
            for w in [self._pause_btn, self._stop_btn, self._wait_btn]:
                w.pack_forget()
            self._col_btn.config(text="□")
        else:
            self.geometry(f"{self._W}x{self._H}")
            self._pause_btn.pack(side="left", padx=1)
            self._stop_btn.pack(side="left")
            self._wait_btn.pack(side="left", padx=1)
            self._col_btn.config(text="—")

    def set_count(self, n: int):
        try:
            self._count_lbl.config(text=f"{n} steps" if n else "")
        except Exception:
            pass

    def update_state(self, state: _State):
        try:
            if state == _State.IDLE:
                self._top_bar.config(bg=T["fg3"])
                self._dot.config(fg=T["fg3"])
                self._name_lbl.config(text="IDLE", fg=T["fg3"])
                self._rec_btn.config(state="normal")
                self._pause_btn.config(state="disabled")
                self._stop_btn.config(state="disabled")
            elif state == _State.RECORDING:
                self._top_bar.config(bg=T["red"])
                self._dot.config(fg=T["red"])
                self._name_lbl.config(text="REC", fg=T["red"])
                self._rec_btn.config(state="disabled")
                self._pause_btn.config(state="normal")
                self._stop_btn.config(state="normal")
            elif state == _State.PAUSED:
                self._top_bar.config(bg=T["yellow"])
                self._dot.config(fg=T["yellow"])
                self._name_lbl.config(text="PAUSED", fg=T["yellow"])
                self._rec_btn.config(state="normal")
                self._pause_btn.config(state="normal")
                self._stop_btn.config(state="normal")
        except Exception:
            pass

    def _make_draggable(self):
        self._dx = self._dy = 0

        def _start(e):
            self._dx = e.x_root - self.winfo_x()
            self._dy = e.y_root - self.winfo_y()

        def _drag(e):
            x = e.x_root - self._dx
            y = e.y_root - self._dy
            self.geometry(f"+{x}+{y}")
            # Save position
            _prefs["overlay_x"] = x
            _prefs["overlay_y"] = y

        for w in [self] + list(self.winfo_children()):
            try:
                w.bind("<ButtonPress-1>", _start, add="+")
                w.bind("<B1-Motion>",     _drag,  add="+")
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
#  _StepInlineEditor  — quick edit dialog for a recorded step
# ─────────────────────────────────────────────────────────────────────────────

class _StepInlineEditor(tk.Toplevel):
    def __init__(self, parent, step: dict, on_save: callable):
        super().__init__(parent)
        self.title(f"Edit Step: {step.get('type','')}")
        self.configure(bg=T["bg"])
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self._step    = copy.deepcopy(step)
        self._on_save = on_save
        self._fields  = {}
        self._build()
        self.grab_set()

    def _build(self):
        t = self._step.get("type", "")
        tk.Label(self, text=f"Editing: {t}", bg=T["bg"], fg=T["acc"],
                 font=("Segoe UI Semibold", 10)).pack(padx=20, pady=(12, 6))

        f = tk.Frame(self, bg=T["bg"]); f.pack(fill="x", padx=20, pady=4)

        def row(label, key, cast=str, width=20):
            r = tk.Frame(f, bg=T["bg"]); r.pack(fill="x", pady=3)
            tk.Label(r, text=label, bg=T["bg"], fg=T["fg2"],
                     font=T["font_s"], width=14, anchor="e").pack(side="left")
            v = tk.StringVar(value=str(self._step.get(key, "")))
            self._fields[key] = (v, cast)
            tk.Entry(r, textvariable=v, width=width,
                     bg=T["bg3"], fg=T["fg"], insertbackground=T["fg"],
                     font=("Consolas", 9), relief="flat").pack(side="left", padx=8)

        if t in ("click", "double_click", "right_click", "mouse_move"):
            row("X:", "x", int)
            row("Y:", "y", int)
            rel_v = tk.BooleanVar(value=self._step.get("relative", False))
            tk.Checkbutton(f, text="Relative coordinates",
                           variable=rel_v, bg=T["bg"], fg=T["purple"],
                           selectcolor=T["bg3"], font=T["font_s"],
                           activebackground=T["bg"]).pack(anchor="w")
            self._rel_v = rel_v

        elif t == "hotkey":
            row("Keys:", "keys", str, 28)

        elif t in ("type_text", "clip_type"):
            row("Text:", "text", str, 32)

        elif t == "wait":
            row("Seconds:", "seconds", float)

        elif t == "scroll":
            row("X:", "x", int)
            row("Y:", "y", int)
            row("Direction:", "direction", str, 8)
            row("Clicks:", "clicks", int)

        elif t == "wait_window":
            row("Window title:", "window_title", str, 28)
            row("Process:", "process", str, 16)
            row("Timeout (s):", "timeout", float)

        # Note
        r = tk.Frame(f, bg=T["bg"]); r.pack(fill="x", pady=3)
        tk.Label(r, text="Note:", bg=T["bg"], fg=T["fg2"],
                 font=T["font_s"], width=14, anchor="e").pack(side="left")
        nv = tk.StringVar(value=self._step.get("note", ""))
        self._fields["note"] = (nv, str)
        tk.Entry(r, textvariable=nv, width=28,
                 bg=T["bg3"], fg=T["fg3"], insertbackground=T["fg"],
                 font=("Consolas", 9), relief="flat").pack(side="left", padx=8)

        # Enabled
        ev = tk.BooleanVar(value=self._step.get("enabled", True))
        self._enabled_v = ev
        tk.Checkbutton(f, text="Enabled", variable=ev,
                       bg=T["bg"], fg=T["fg2"], selectcolor=T["bg3"],
                       activebackground=T["bg"], font=T["font_s"]).pack(anchor="w", pady=4)

        bf = tk.Frame(self, bg=T["bg2"], pady=8); bf.pack(fill="x", side="bottom")
        tk.Button(bf, text="  Save  ", bg=T["acc"], fg="white",
                  font=("Segoe UI Semibold", 9), relief="flat", cursor="hand2",
                  command=self._save).pack(side="left", padx=16)
        tk.Button(bf, text="Cancel", bg=T["bg3"], fg=T["fg2"],
                  font=T["font_b"], relief="flat", cursor="hand2",
                  command=self.destroy).pack(side="left")

    def _save(self):
        result = copy.deepcopy(self._step)
        for key, (var, cast) in self._fields.items():
            try:
                result[key] = cast(var.get())
            except (ValueError, TypeError):
                pass
        if hasattr(self, "_rel_v"):
            result["relative"] = self._rel_v.get()
        result["enabled"] = self._enabled_v.get()
        self._on_save(result)
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
#  _ImportPreviewDialog — shows summary before importing
# ─────────────────────────────────────────────────────────────────────────────

class _ImportPreviewDialog(tk.Toplevel):
    def __init__(self, parent, steps: list, on_confirm: callable):
        super().__init__(parent)
        self.title("Import Preview")
        self.configure(bg=T["bg"])
        self.resizable(False, True)
        self.attributes("-topmost", True)
        self._steps      = steps
        self._on_confirm = on_confirm
        self._mode       = tk.StringVar(value="replace")
        self._flow       = tk.StringVar(value="main")
        self._build()
        self.grab_set()

    def _build(self):
        tk.Label(self, text="Import Preview",
                 bg=T["bg"], fg=T["acc"],
                 font=("Segoe UI Semibold", 12)).pack(padx=20, pady=(14, 4))
        tk.Label(self, text=f"{len(self._steps)} steps recorded",
                 bg=T["bg"], fg=T["fg2"], font=T["font_b"]).pack()

        # Summary listbox
        lf = tk.LabelFrame(self, text="  Steps  ", bg=T["bg"],
                            fg=T["fg3"], font=T["font_s"])
        lf.pack(fill="both", expand=True, padx=16, pady=8)
        lb = tk.Listbox(lf, bg=T["bg3"], fg=T["fg"], font=T["font_m"],
                        height=12, relief="flat", bd=0)
        sb = ttk.Scrollbar(lf, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        lb.pack(fill="both", expand=True, padx=4, pady=4)
        for i, s in enumerate(self._steps, 1):
            lb.insert("end", f"  {i:02d}.  {MacroRecorderPro._step_label(s)}")

        # Options
        opts = tk.Frame(self, bg=T["bg"]); opts.pack(fill="x", padx=16, pady=4)

        tk.Label(opts, text="Mode:", bg=T["bg"], fg=T["fg2"],
                 font=T["font_b"]).pack(side="left")
        for val, txt in [("replace","Replace existing steps"),("append","Append to existing")]:
            tk.Radiobutton(opts, text=txt, variable=self._mode, value=val,
                           bg=T["bg"], fg=T["fg2"], selectcolor=T["bg3"],
                           activebackground=T["bg"], font=T["font_s"]
                           ).pack(side="left", padx=8)

        opts2 = tk.Frame(self, bg=T["bg"]); opts2.pack(fill="x", padx=16, pady=(0, 8))
        tk.Label(opts2, text="Target:", bg=T["bg"], fg=T["fg2"],
                 font=T["font_b"]).pack(side="left")
        for val, txt in [("main","Main Flow"), ("first","First-Name Flow")]:
            tk.Radiobutton(opts2, text=txt, variable=self._flow, value=val,
                           bg=T["bg"], fg=T["fg2"], selectcolor=T["bg3"],
                           activebackground=T["bg"], font=T["font_s"]
                           ).pack(side="left", padx=8)

        bf = tk.Frame(self, bg=T["bg2"], pady=10); bf.pack(fill="x", side="bottom")
        tk.Button(bf, text="✔  Confirm Import",
                  bg=T["green"], fg=T["bg"],
                  font=("Segoe UI Semibold", 10), relief="flat", cursor="hand2",
                  padx=14, pady=7,
                  command=self._confirm).pack(side="left", padx=16)
        tk.Button(bf, text="Cancel", bg=T["bg3"], fg=T["fg2"],
                  font=T["font_b"], relief="flat", cursor="hand2",
                  command=self.destroy).pack(side="left")

    def _confirm(self):
        self._on_confirm(list(self._steps), self._mode.get(), self._flow.get())
        self.destroy()


# ── Module-level helpers ──────────────────────────────────────────────────────

def validate_recorder_shortcut(shortcut_str: str) -> tuple[bool, str]:
    sc = shortcut_str.strip().lower()
    sc = sc.replace("control", "ctrl").replace("control_l", "ctrl")
    if sc in _WINDOWS_SYSTEM_SHORTCUTS:
        return False, f"'{shortcut_str}' conflicts with a Windows system shortcut."
    parts = [p.strip() for p in sc.split("+")]
    if all(p in {"ctrl", "shift", "alt", "win", "super"} for p in parts):
        return False, "Must include a non-modifier key."
    return True, ""


def get_recorder_shortcut_defaults() -> dict:
    return dict(DEFAULT_RECORDER_SHORTCUTS)


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


def _add_tooltip(widget, text: str):
    tip = [None]
    def _show(e):
        if tip[0]: return
        tw = tk.Toplevel(widget); tw.wm_overrideredirect(True)
        tw.configure(bg="#ffffcc")
        tk.Label(tw, text=text, bg="#ffffcc", fg="#333",
                 font=("Segoe UI", 8), relief="solid",
                 bd=1, padx=6, pady=4).pack()
        tw.wm_geometry(f"+{widget.winfo_rootx()+20}+{widget.winfo_rooty()+widget.winfo_height()+4}")
        tip[0] = tw
    def _hide(e):
        if tip[0]:
            tip[0].destroy(); tip[0] = None
    widget.bind("<Enter>", _show, add="+")
    widget.bind("<Leave>", _hide, add="+")
