"""
agent/flow_debugger.py
======================
FlowDebugger — step-through debugger for RPA flows.

Features:
  - Step-by-step execution (Next, Continue, Stop)
  - Breakpoints per step index
  - Variable inspection panel
  - Live window detection before each step
  - Step result log (pass / fail / skipped)
  - Dry-run mode toggle
  - Inline step edit from debugger
  - Call stack for nested loops
  - Current step highlight
"""

from __future__ import annotations

import copy
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

import pyautogui

from core.constants import T, STEP_COLORS, STEP_FRIENDLY, _prefs
from core.helpers import step_summary, step_human_label, apply_variables, parse_hotkey
from core.window_manager import get_window_manager, WindowInfo


# ─────────────────────────────────────────────────────────────────────────────
#  FlowDebugger
# ─────────────────────────────────────────────────────────────────────────────

class FlowDebugger(tk.Toplevel):
    """
    Interactive step-by-step flow debugger.

    Usage:
        FlowDebugger(parent, steps=flow, names=["Alice"], variables={})
    """

    # Execution signals
    _SIG_STEP  = "step"     # advance one step
    _SIG_RUN   = "run"      # run until breakpoint / end
    _SIG_STOP  = "stop"     # abort

    def __init__(self, parent,
                 steps: list,
                 names: list = None,
                 variables: dict = None,
                 on_close: Callable | None = None):
        super().__init__(parent)
        self.title("🐛 Flow Debugger")
        self.configure(bg=T["bg"])
        self.geometry("1100x780")
        self.minsize(860, 600)

        self._steps      = copy.deepcopy(steps)
        self._names      = list(names or ["[test]"])
        self._variables  = dict(variables or {})
        self._on_close   = on_close
        self._wm         = get_window_manager()

        # Execution state
        self._current_idx  = 0
        self._current_name = self._names[0] if self._names else ""
        self._name_idx     = 0
        self._breakpoints: set[int] = set()
        self._results: list[dict]   = []   # {idx, step, ok, msg, elapsed}
        self._call_stack: list       = []   # for nested loops
        self._dry_run    = tk.BooleanVar(value=True)
        self._validate_window = tk.BooleanVar(value=False)

        # Thread-safe signal
        self._signal: Optional[str] = None
        self._signal_lock = threading.Lock()
        self._exec_thread: Optional[threading.Thread] = None
        self._running = False
        self._paused  = True   # starts paused (manual step)
        self._stop_event = threading.Event()

        # Live window
        self._active_window: Optional[WindowInfo] = None

        self._build_ui()
        self._refresh_step_list()
        self._highlight_current()
        self._start_window_poll()
        self.protocol("WM_DELETE_WINDOW", self._on_close_btn)

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header bar ────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=T["bg2"], pady=10)
        hdr.pack(fill="x")
        tk.Label(hdr, text="🐛 Flow Debugger",
                 bg=T["bg2"], fg=T["acc"],
                 font=("Segoe UI Semibold", 13)).pack(side="left", padx=16)

        self._status_lbl = tk.Label(hdr, text="⏸ Paused at step 1",
                                    bg=T["bg2"], fg=T["yellow"],
                                    font=("Segoe UI Semibold", 9))
        self._status_lbl.pack(side="left", padx=12)

        # Name selector
        tk.Label(hdr, text="Name:", bg=T["bg2"], fg=T["fg3"],
                 font=T["font_s"]).pack(side="left", padx=(20, 4))
        self._name_var = tk.StringVar(value=self._current_name)
        name_cb = ttk.Combobox(hdr, textvariable=self._name_var,
                               values=self._names, state="readonly", width=18)
        name_cb.pack(side="left")
        name_cb.bind("<<ComboboxSelected>>", self._on_name_change)

        # Dry run toggle
        tk.Checkbutton(hdr, text="Dry Run (no clicks)",
                       variable=self._dry_run,
                       bg=T["bg2"], fg=T["yellow"],
                       selectcolor=T["bg3"],
                       activebackground=T["bg2"],
                       font=T["font_s"]).pack(side="left", padx=12)

        # Window validation toggle
        tk.Checkbutton(hdr, text="Validate Window",
                       variable=self._validate_window,
                       bg=T["bg2"], fg=T["cyan"],
                       selectcolor=T["bg3"],
                       activebackground=T["bg2"],
                       font=T["font_s"]).pack(side="left", padx=4)

        # ── Control bar ───────────────────────────────────────────────────────
        ctrl = tk.Frame(self, bg=T["bg"], pady=8)
        ctrl.pack(fill="x", padx=12)

        def cbtn(text, bg, fg, cmd, tip="", width=None):
            kw = dict(bg=bg, fg=fg, font=("Segoe UI Semibold", 9),
                      relief="flat", cursor="hand2", padx=10, pady=6,
                      command=cmd)
            if width:
                kw["width"] = width
            b = tk.Button(ctrl, text=text, **kw)
            b.pack(side="left", padx=3)
            return b

        self._step_btn = cbtn("⏭ Step (F10)", T["acc"],    "white",   self._cmd_step)
        self._run_btn  = cbtn("▶ Run (F5)",   T["green"],  T["bg"],   self._cmd_run)
        self._stop_btn = cbtn("⏹ Stop",       T["red"],    "white",   self._cmd_stop)
        cbtn("↺ Reset",                       T["bg3"],    T["fg2"],  self._cmd_reset)
        cbtn("🔴 Toggle Breakpoint (F9)",     T["bg3"],    T["red"],  self._cmd_toggle_bp)

        # Keyboard shortcuts
        self.bind("<F10>",  lambda e: self._cmd_step())
        self.bind("<F5>",   lambda e: self._cmd_run())
        self.bind("<F9>",   lambda e: self._cmd_toggle_bp())
        self.bind("<Escape>", lambda e: self._cmd_stop())

        # Speed slider (for run-mode delay)
        tk.Label(ctrl, text="  Speed:", bg=T["bg"], fg=T["fg3"],
                 font=T["font_s"]).pack(side="left", padx=(16, 4))
        self._speed_var = tk.DoubleVar(value=0.5)
        spd = ttk.Scale(ctrl, variable=self._speed_var,
                        from_=0.0, to=2.0, orient="horizontal", length=100)
        spd.pack(side="left")
        tk.Label(ctrl, text="s/step", bg=T["bg"], fg=T["fg3"],
                 font=T["font_s"]).pack(side="left")

        # ── Main paned area ───────────────────────────────────────────────────
        pane = tk.PanedWindow(self, orient="horizontal",
                              bg=T["bg4"], sashwidth=5, sashrelief="flat")
        pane.pack(fill="both", expand=True, padx=8, pady=4)

        # Left: step list
        left = tk.Frame(pane, bg=T["bg"])
        pane.add(left, stretch="always", width=420)
        self._build_step_list(left)

        # Right: inspection panels
        right = tk.Frame(pane, bg=T["bg"])
        pane.add(right, stretch="always", width=660)
        self._build_right_panel(right)

    def _build_step_list(self, parent):
        tk.Label(parent, text="Steps", bg=T["bg"], fg=T["fg2"],
                 font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=8, pady=(4, 2))

        outer = tk.Frame(parent, bg=T["bg"])
        outer.pack(fill="both", expand=True, padx=4)
        self._step_canvas = tk.Canvas(outer, bg=T["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=self._step_canvas.yview)
        self._step_canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._step_canvas.pack(side="left", fill="both", expand=True)
        self._step_frame = tk.Frame(self._step_canvas, bg=T["bg"])
        self._step_win   = self._step_canvas.create_window(
            (0, 0), window=self._step_frame, anchor="nw")
        self._step_frame.bind("<Configure>",
            lambda e: self._step_canvas.configure(
                scrollregion=self._step_canvas.bbox("all")))
        self._step_canvas.bind("<Configure>",
            lambda e, c=self._step_canvas, w=self._step_win: c.itemconfig(w, width=e.width))
        self._step_canvas.bind("<MouseWheel>",
            lambda e: self._step_canvas.yview_scroll(-1*(e.delta//120), "units"))

    def _build_right_panel(self, parent):
        right_nb = ttk.Notebook(parent)
        right_nb.pack(fill="both", expand=True)

        # Tab 1 — Current step detail
        t1 = tk.Frame(right_nb, bg=T["bg"])
        right_nb.add(t1, text="  Current Step  ")
        self._build_step_detail(t1)

        # Tab 2 — Variables
        t2 = tk.Frame(right_nb, bg=T["bg"])
        right_nb.add(t2, text="  Variables  ")
        self._build_var_panel(t2)

        # Tab 3 — Active Window
        t3 = tk.Frame(right_nb, bg=T["bg"])
        right_nb.add(t3, text="  Window  ")
        self._build_window_panel(t3)

        # Tab 4 — Results log
        t4 = tk.Frame(right_nb, bg=T["bg"])
        right_nb.add(t4, text="  Results  ")
        self._build_results_panel(t4)

        # Tab 5 — Call Stack
        t5 = tk.Frame(right_nb, bg=T["bg"])
        right_nb.add(t5, text="  Call Stack  ")
        self._build_callstack_panel(t5)

    def _build_step_detail(self, parent):
        self._detail_frame = tk.Frame(parent, bg=T["bg2"])
        self._detail_frame.pack(fill="both", expand=True, padx=8, pady=8)
        tk.Label(self._detail_frame, text="Select a step to inspect",
                 bg=T["bg2"], fg=T["fg3"], font=T["font_s"]).pack(pady=30)

    def _build_var_panel(self, parent):
        tk.Label(parent, text="  Runtime Variables",
                 bg=T["bg"], fg=T["fg2"],
                 font=("Segoe UI Semibold", 9)).pack(anchor="w", pady=(8, 4))
        outer = tk.Frame(parent, bg=T["bg"]); outer.pack(fill="both", expand=True, padx=8)
        self._var_canvas = tk.Canvas(outer, bg=T["bg"], highlightthickness=0)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=self._var_canvas.yview)
        self._var_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._var_canvas.pack(side="left", fill="both", expand=True)
        self._var_frame = tk.Frame(self._var_canvas, bg=T["bg"])
        vw = self._var_canvas.create_window((0, 0), window=self._var_frame, anchor="nw")
        self._var_frame.bind("<Configure>",
            lambda e: self._var_canvas.configure(scrollregion=self._var_canvas.bbox("all")))
        self._var_canvas.bind("<Configure>",
            lambda e, c=self._var_canvas, w=vw: c.itemconfig(w, width=e.width))

    def _build_window_panel(self, parent):
        tk.Label(parent, text="  Active Window Detection",
                 bg=T["bg"], fg=T["fg2"],
                 font=("Segoe UI Semibold", 9)).pack(anchor="w", pady=(8, 4))
        self._win_frame = tk.Frame(parent, bg=T["bg"])
        self._win_frame.pack(fill="both", expand=True, padx=8)

        # Snapshot button
        bf = tk.Frame(parent, bg=T["bg"]); bf.pack(fill="x", padx=8, pady=4)
        tk.Button(bf, text="📷 Capture Current Window as Target",
                  bg=T["acc"], fg="white", font=T["font_s"],
                  relief="flat", cursor="hand2", padx=8, pady=4,
                  command=self._capture_window_target).pack(side="left")
        tk.Button(bf, text="🔍 Test Match",
                  bg=T["bg3"], fg=T["fg2"], font=T["font_s"],
                  relief="flat", cursor="hand2", padx=8, pady=4,
                  command=self._test_window_match).pack(side="left", padx=6)

        self._window_target: Optional[WindowInfo] = None

    def _build_results_panel(self, parent):
        tk.Label(parent, text="  Step Results",
                 bg=T["bg"], fg=T["fg2"],
                 font=("Segoe UI Semibold", 9)).pack(anchor="w", pady=(8, 2))
        self._results_text = tk.Text(parent, bg=T["bg3"], fg=T["fg"],
                                     font=("Consolas", 8),
                                     state="disabled", relief="flat",
                                     padx=8, pady=6)
        self._results_text.tag_config("ok",   foreground=T["green"])
        self._results_text.tag_config("err",  foreground=T["red"])
        self._results_text.tag_config("skip", foreground=T["fg3"])
        self._results_text.tag_config("bp",   foreground=T["yellow"])
        sb = ttk.Scrollbar(parent, orient="vertical", command=self._results_text.yview)
        self._results_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._results_text.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def _build_callstack_panel(self, parent):
        tk.Label(parent, text="  Call Stack (Loops)",
                 bg=T["bg"], fg=T["fg2"],
                 font=("Segoe UI Semibold", 9)).pack(anchor="w", pady=(8, 2))
        self._stack_listbox = tk.Listbox(parent, bg=T["bg3"], fg=T["fg"],
                                         font=("Consolas", 8),
                                         relief="flat", selectbackground=T["acc_dark"])
        self._stack_listbox.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    # ── Step list rendering ───────────────────────────────────────────────────

    def _refresh_step_list(self):
        for w in self._step_frame.winfo_children():
            try: w.destroy()
            except: pass

        for i, step in enumerate(self._steps):
            self._render_step_row(i, step)

    def _render_step_row(self, i: int, step: dict):
        t       = step.get("type", "comment")
        enabled = step.get("enabled", True)
        color   = STEP_COLORS.get(t, T["fg2"]) if enabled else T["fg3"]
        ico, lbl, _, _ = step_human_label(step)
        summary = step_summary(step)
        is_bp   = i in self._breakpoints
        is_cur  = i == self._current_idx

        bg = T["bg3"] if is_cur else (T["bg2"] if i % 2 == 0 else T["bg"])

        row = tk.Frame(self._step_frame, bg=bg, cursor="hand2")
        row.pack(fill="x", pady=1)
        row._step_index = i

        # Breakpoint indicator
        bp_lbl = tk.Label(row, text="🔴" if is_bp else "  ",
                          bg=bg, fg=T["red"], font=T["font_s"], width=3)
        bp_lbl.pack(side="left")

        # Current arrow
        cur_lbl = tk.Label(row,
                           text="▶" if is_cur else "  ",
                           bg=bg, fg=T["green"],
                           font=("Segoe UI Semibold", 9), width=2)
        cur_lbl.pack(side="left")

        # Step number
        tk.Label(row, text=f"{i+1:02d}.", bg=bg, fg=T["fg3"],
                 font=("Consolas", 8), width=4).pack(side="left")

        # Color bar
        tk.Frame(row, bg=color, width=4).pack(side="left", fill="y")

        # Label
        txt = f"{ico} {lbl}"
        if not enabled:
            txt = f"⊘ {lbl}"
        tk.Label(row, text=txt, bg=bg, fg=color,
                 font=("Segoe UI Semibold", 8)).pack(side="left", padx=6)

        if summary:
            s = summary[:35] + "…" if len(summary) > 35 else summary
            tk.Label(row, text=s, bg=bg, fg=T["fg3"],
                     font=("Consolas", 8)).pack(side="left")

        # Result badge if already run
        result = next((r for r in self._results if r["idx"] == i), None)
        if result:
            badge_txt = "✔" if result["ok"] else "✘"
            badge_fg  = T["green"] if result["ok"] else T["red"]
            tk.Label(row, text=badge_txt, bg=bg, fg=badge_fg,
                     font=("Segoe UI Semibold", 9)).pack(side="right", padx=8)

        # Click to select/inspect
        row.bind("<Button-1>", lambda e, idx=i: self._on_step_click(idx))
        for ch in row.winfo_children():
            ch.bind("<Button-1>", lambda e, idx=i: self._on_step_click(idx))

        # Double-click to toggle breakpoint
        row.bind("<Double-Button-1>", lambda e, idx=i: self._toggle_bp(idx))

    def _on_step_click(self, idx: int):
        self._show_step_detail(idx)

    def _highlight_current(self):
        self._refresh_step_list()
        # Scroll to current
        children = [w for w in self._step_frame.winfo_children()
                    if hasattr(w, "_step_index") and w._step_index == self._current_idx]
        if children:
            self._step_frame.update_idletasks()
            y = children[0].winfo_y()
            total_h = self._step_frame.winfo_height()
            if total_h > 0:
                frac = y / max(total_h, 1)
                self._step_canvas.yview_moveto(max(0, frac - 0.2))

    # ── Step detail panel ─────────────────────────────────────────────────────

    def _show_step_detail(self, idx: int):
        step = self._steps[idx]
        for w in self._detail_frame.winfo_children():
            try: w.destroy()
            except: pass

        t       = step.get("type", "comment")
        color   = STEP_COLORS.get(t, T["acc"])
        ico, lbl, desc, _ = step_human_label(step)

        hdr = tk.Frame(self._detail_frame, bg=color)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"  Step {idx+1}  {ico}  {lbl}",
                 bg=color, fg="white",
                 font=("Segoe UI Semibold", 10), pady=8).pack(anchor="w", padx=12)

        body = tk.Frame(self._detail_frame, bg=T["bg2"])
        body.pack(fill="both", expand=True, padx=0, pady=0)

        def row(key, val, val_fg=None):
            r = tk.Frame(body, bg=T["bg2"]); r.pack(fill="x", padx=12, pady=3)
            tk.Label(r, text=f"{key}:", bg=T["bg2"], fg=T["fg3"],
                     font=T["font_s"], width=14, anchor="e").pack(side="left")
            tk.Label(r, text=str(val), bg=T["bg2"], fg=val_fg or T["fg"],
                     font=("Consolas", 9)).pack(side="left", padx=8)

        vmap = {**self._variables, "name": self._current_name}
        summary = apply_variables(step_summary(step), vmap)

        row("Type",    t,                  color)
        row("Summary", summary)
        row("Enabled", step.get("enabled", True))
        row("Note",    step.get("note", "") or "—", T["fg3"])

        if t in ("click", "double_click", "right_click"):
            rel = step.get("relative", False)
            row("Coordinates", f"({step.get('x')}, {step.get('y')})")
            row("Relative", rel, T["cyan"] if rel else T["fg3"])
            if rel and self._active_window:
                ax, ay = self._active_window.abs_coords(step["x"], step["y"])
                row("Resolved →", f"({ax}, {ay})", T["yellow"])

        if t == "hotkey":
            row("Keys", step.get("keys", ""))

        if t in ("type_text", "clip_type"):
            resolved = apply_variables(step.get("text", ""), vmap)
            row("Raw text",      step.get("text", ""))
            row("Resolved text", resolved, T["yellow"])

        if t == "wait":
            row("Duration", f"{step.get('seconds', 1.0)}s")

        if t in ("wait_window", "focus_window", "assert_window"):
            row("Window title",   step.get("window_title", ""))
            row("Process",        step.get("process", ""))
            row("hwnd",           step.get("hwnd", 0))
            row("Timeout",        f"{step.get('timeout', 10)}s")

        # Result if available
        result = next((r for r in self._results if r["idx"] == idx), None)
        if result:
            tk.Frame(body, bg=T["bg4"], height=1).pack(fill="x", padx=8, pady=6)
            ok_lbl = "✔ Passed" if result["ok"] else "✘ Failed"
            ok_fg  = T["green"] if result["ok"] else T["red"]
            row("Last result", ok_lbl, ok_fg)
            row("Message",     result.get("msg", ""), T["fg3"])
            row("Elapsed",     f"{result.get('elapsed', 0):.3f}s")

        # Run this step button
        tf = tk.Frame(body, bg=T["bg2"]); tf.pack(fill="x", padx=12, pady=10)
        tk.Button(tf, text="▶ Run This Step",
                  bg=T["acc"], fg="white", font=T["font_s"],
                  relief="flat", cursor="hand2", padx=8, pady=4,
                  command=lambda i=idx: self._run_single_step(i)).pack(side="left")
        tk.Button(tf, text="🔴 Breakpoint",
                  bg=T["bg3"], fg=T["red"], font=T["font_s"],
                  relief="flat", cursor="hand2", padx=8, pady=4,
                  command=lambda i=idx: self._toggle_bp(i)).pack(side="left", padx=6)

    # ── Variable panel ────────────────────────────────────────────────────────

    def _refresh_var_panel(self):
        for w in self._var_frame.winfo_children():
            try: w.destroy()
            except: pass

        vmap = {**self._variables, "name": self._current_name}
        for key, val in vmap.items():
            r = tk.Frame(self._var_frame, bg=T["bg"]); r.pack(fill="x", pady=2)
            tk.Label(r, text=f"  {{{key}}}",
                     bg=T["bg"], fg=T["cyan"], font=("Consolas", 9),
                     width=18, anchor="w").pack(side="left")
            tk.Label(r, text="=", bg=T["bg"], fg=T["fg3"],
                     font=T["font_s"]).pack(side="left")
            tk.Label(r, text=f"  {val}",
                     bg=T["bg"], fg=T["yellow"], font=("Consolas", 9)
                     ).pack(side="left", padx=4)

    # ── Window panel ──────────────────────────────────────────────────────────

    def _refresh_window_panel(self):
        for w in self._win_frame.winfo_children():
            try: w.destroy()
            except: pass

        win = self._active_window
        if not win:
            tk.Label(self._win_frame, text="No window detected",
                     bg=T["bg"], fg=T["fg3"], font=T["font_s"]).pack(pady=20)
            return

        def row(key, val, val_fg=None):
            r = tk.Frame(self._win_frame, bg=T["bg"]); r.pack(fill="x", pady=2)
            tk.Label(r, text=f"{key}:", bg=T["bg"], fg=T["fg3"],
                     font=T["font_s"], width=14, anchor="e").pack(side="left")
            tk.Label(r, text=str(val), bg=T["bg"], fg=val_fg or T["fg"],
                     font=("Consolas", 8)).pack(side="left", padx=6)

        row("Title",     win.title,                 T["fg"])
        row("Process",   win.process or "—",        T["cyan"])
        row("Class",     win.cls or "—",            T["fg3"])
        row("HWND",      win.hwnd or "—",           T["yellow"])
        row("Position",  f"{win.x}, {win.y}",       T["fg2"])
        row("Size",      f"{win.width} × {win.height}", T["fg2"])
        row("Monitor",   win.monitor,               T["fg2"])
        row("DPI Scale", f"{win.dpi_scale:.2f}",    T["fg2"])
        row("Minimized", win.minimized,             T["red"] if win.minimized else T["green"])
        row("Hash",      win.snapshot_hash,         T["fg3"])

        if self._window_target:
            matches = self._wm.match(self._window_target, win)
            m_txt = "✔ Matches target" if matches else "✘ No match"
            m_fg  = T["green"] if matches else T["red"]
            tk.Frame(self._win_frame, bg=T["bg4"], height=1).pack(fill="x", pady=6)
            tk.Label(self._win_frame, text=m_txt,
                     bg=T["bg"], fg=m_fg,
                     font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=4)

    def _capture_window_target(self):
        win = self._wm.get_active_window()
        if win:
            self._window_target = win
            self._refresh_window_panel()
            self._log_result(-1, True, f"Captured: '{win.title}' [{win.process}]", 0)

    def _test_window_match(self):
        if not self._window_target:
            messagebox.showinfo("No Target", "Capture a window target first.")
            return
        ok, msg = self._wm.assert_window(self._window_target)
        self._log_result(-1, ok, msg, 0)

    # ── Breakpoints ───────────────────────────────────────────────────────────

    def _toggle_bp(self, idx: int):
        if idx in self._breakpoints:
            self._breakpoints.discard(idx)
        else:
            self._breakpoints.add(idx)
        self._highlight_current()

    def _cmd_toggle_bp(self):
        self._toggle_bp(self._current_idx)

    # ── Commands ──────────────────────────────────────────────────────────────

    def _cmd_step(self):
        if self._running:
            return
        if self._current_idx >= len(self._steps):
            self._status_lbl.config(text="✔ Flow complete", fg=T["green"])
            return
        self._run_step_at(self._current_idx)

    def _cmd_run(self):
        if self._running:
            return
        self._running = True
        self._exec_thread = threading.Thread(target=self._run_all_thread, daemon=True)
        self._exec_thread.start()

    def _cmd_stop(self):
        self._stop_event.set()
        self._running = False
        self.after(0, lambda: self._status_lbl.config(text="⏹ Stopped", fg=T["red"]))

    def _cmd_reset(self):
        self._stop_event.set()
        self._running = False
        time.sleep(0.1)
        self._stop_event.clear()
        self._current_idx = 0
        self._results.clear()
        self._call_stack.clear()
        self._highlight_current()
        self._clear_results_log()
        self._status_lbl.config(text="⏸ Reset — paused at step 1", fg=T["yellow"])

    def _on_name_change(self, e=None):
        self._current_name = self._name_var.get()
        self._refresh_var_panel()

    # ── Execution core ────────────────────────────────────────────────────────

    def _run_all_thread(self):
        while (self._current_idx < len(self._steps)
               and not self._stop_event.is_set()):
            # Breakpoint check
            if self._current_idx in self._breakpoints and self._current_idx > 0:
                self.after(0, lambda i=self._current_idx: self._status_lbl.config(
                    text=f"🔴 Breakpoint at step {i+1}", fg=T["yellow"]))
                self._running = False
                return

            self._run_step_at(self._current_idx)
            delay = self._speed_var.get()
            if delay > 0:
                self._stop_event.wait(timeout=delay)

        self._running = False
        if not self._stop_event.is_set():
            self.after(0, lambda: self._status_lbl.config(
                text="✔ All steps complete", fg=T["green"]))

    def _run_step_at(self, idx: int):
        if idx >= len(self._steps):
            return
        step = self._steps[idx]

        self.after(0, lambda i=idx: self._status_lbl.config(
            text=f"▶ Running step {i+1}/{len(self._steps)}…", fg=T["acc"]))
        self.after(0, lambda: self._refresh_var_panel())

        # Window validation
        if self._validate_window.get() and self._window_target:
            ok, msg = self._wm.validate_before_action(self._window_target, timeout=5.0,
                                                       stop_event=self._stop_event)
            if not ok:
                self._log_result(idx, False, f"Window validation failed: {msg}", 0)
                self._advance(idx)
                return

        t0  = time.time()
        ok, msg = self._execute_step(step)
        elapsed = time.time() - t0

        self._results.append({"idx": idx, "step": step, "ok": ok,
                               "msg": msg, "elapsed": elapsed})
        self._log_result(idx, ok, msg, elapsed)
        self._advance(idx)

    def _advance(self, from_idx: int):
        next_idx = from_idx + 1
        self._current_idx = next_idx
        self.after(0, self._highlight_current)

    def _run_single_step(self, idx: int):
        """Run a single specific step (from detail panel)."""
        if self._running:
            return
        threading.Thread(target=lambda: self._run_step_at(idx), daemon=True).start()

    def _execute_step(self, step: dict) -> tuple[bool, str]:
        """Execute one step. Returns (ok, message)."""
        t    = step.get("type", "comment")
        dry  = self._dry_run.get()
        vmap = {**self._variables, "name": self._current_name}

        def sub(text): return apply_variables(str(text), vmap)

        try:
            if not step.get("enabled", True):
                return True, "Skipped (disabled)"

            if t == "comment":
                return True, f"Comment: {sub(step.get('text', ''))}"

            elif t == "click":
                x, y = self._resolve_coords(step)
                if not dry: pyautogui.click(x, y)
                return True, f"Clicked ({x}, {y})"

            elif t == "double_click":
                x, y = self._resolve_coords(step)
                if not dry: pyautogui.doubleClick(x, y)
                return True, f"Double-clicked ({x}, {y})"

            elif t == "right_click":
                x, y = self._resolve_coords(step)
                if not dry: pyautogui.rightClick(x, y)
                return True, f"Right-clicked ({x}, {y})"

            elif t == "hotkey":
                keys = parse_hotkey(sub(step.get("keys", "enter")))
                if not dry: pyautogui.hotkey(*keys)
                return True, f"Hotkey: {'+'.join(keys)}"

            elif t == "type_text":
                text = sub(step.get("text", ""))
                if not dry: pyautogui.typewrite(text, interval=0.05)
                return True, f"Typed: {text[:30]}"

            elif t == "clip_type":
                from core.helpers import type_text_safe
                text = sub(step.get("text", ""))
                if not dry: type_text_safe(text)
                return True, f"Clip-typed: {text[:30]}"

            elif t == "wait":
                secs = float(step.get("seconds", 1.0))
                if not dry: self._stop_event.wait(timeout=secs)
                return True, f"Waited {secs}s"

            elif t == "wait_window":
                target = WindowInfo(
                    title=sub(step.get("window_title", "")),
                    process=step.get("process", ""),
                    hwnd=step.get("hwnd", 0),
                )
                timeout = float(step.get("timeout", 10))
                if dry:
                    return True, f"[dry] wait_window: '{target.title}'"
                found = self._wm.wait_for_window(target, timeout=timeout,
                                                  stop_event=self._stop_event)
                if found:
                    return True, f"Window found: '{found.title}'"
                return False, f"Timeout waiting for '{target.title}'"

            elif t == "focus_window":
                target = WindowInfo(
                    title=sub(step.get("window_title", "")),
                    process=step.get("process", ""),
                    hwnd=step.get("hwnd", 0),
                )
                if dry:
                    return True, f"[dry] focus_window: '{target.title}'"
                ok_f = self._wm.focus_window(target)
                return ok_f, ("Focused" if ok_f else "Could not focus") + f" '{target.title}'"

            elif t == "assert_window":
                target = WindowInfo(
                    title=sub(step.get("window_title", "")),
                    process=step.get("process", ""),
                    hwnd=step.get("hwnd", 0),
                )
                ok_a, msg_a = self._wm.assert_window(target)
                return ok_a, msg_a

            elif t in ("pagedown", "pageup"):
                key = "pagedown" if t == "pagedown" else "pageup"
                times = int(step.get("times", 1))
                if not dry:
                    for _ in range(times):
                        pyautogui.press(key)
                        time.sleep(0.05)
                return True, f"{key} ×{times}"

            elif t == "key_repeat":
                key   = step.get("key", "tab")
                times = int(step.get("times", 1))
                if not dry:
                    for _ in range(times):
                        pyautogui.press(key)
                        time.sleep(0.05)
                return True, f"Pressed {key} ×{times}"

            elif t == "scroll":
                amt = int(step.get("clicks", 3))
                x, y = step.get("x", 0), step.get("y", 0)
                d = step.get("direction", "down").lower()
                if not dry:
                    pyautogui.scroll(-amt if d == "down" else amt, x=x, y=y)
                return True, f"Scrolled {d} ×{amt}"

            elif t == "loop":
                times = int(step.get("times", 2))
                sub_steps = step.get("steps", [])
                for rep in range(times):
                    if self._stop_event.is_set():
                        break
                    self._call_stack.append(f"Loop rep {rep+1}/{times}")
                    self.after(0, self._refresh_callstack)
                    for ss in sub_steps:
                        ok_s, msg_s = self._execute_step(ss)
                        if not ok_s:
                            self._call_stack.pop()
                            return False, f"Loop failed at rep {rep+1}: {msg_s}"
                    self._call_stack.pop()
                    self.after(0, self._refresh_callstack)
                return True, f"Loop ×{times} done"

            elif t == "screenshot":
                import os, datetime
                folder = sub(step.get("folder", "screenshots"))
                if not os.path.isabs(folder):
                    from core.constants import _DIR
                    folder = os.path.join(_DIR, folder)
                if not dry:
                    os.makedirs(folder, exist_ok=True)
                    ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    path = os.path.join(folder, f"debug_{ts}.png")
                    pyautogui.screenshot(path)
                return True, f"Screenshot saved"

            else:
                return True, f"Unknown step '{t}' — skipped"

        except pyautogui.FailSafeException:
            self._stop_event.set()
            return False, "FailSafe: mouse corner!"
        except Exception as e:
            return False, str(e)

    def _resolve_coords(self, step: dict) -> tuple[int, int]:
        """Resolve click coordinates — supports relative coords."""
        if step.get("relative", False) and self._active_window:
            return self._active_window.abs_coords(step["x"], step["y"])
        return int(step.get("x", 0)), int(step.get("y", 0))

    # ── Logging ───────────────────────────────────────────────────────────────

    def _log_result(self, idx: int, ok: bool, msg: str, elapsed: float):
        def _do():
            self._results_text.config(state="normal")
            step_label = f"[{idx+1}]" if idx >= 0 else "[info]"
            tag  = "ok" if ok else "err"
            line = f"{step_label} {'✔' if ok else '✘'}  {msg}"
            if elapsed > 0:
                line += f"  ({elapsed:.3f}s)"
            self._results_text.insert("end", line + "\n", tag)
            self._results_text.see("end")
            self._results_text.config(state="disabled")
        self.after(0, _do)

    def _clear_results_log(self):
        self._results_text.config(state="normal")
        self._results_text.delete("1.0", "end")
        self._results_text.config(state="disabled")

    def _refresh_callstack(self):
        self._stack_listbox.delete(0, "end")
        for entry in reversed(self._call_stack):
            self._stack_listbox.insert("end", f"  {entry}")
        if not self._call_stack:
            self._stack_listbox.insert("end", "  (empty)")

    # ── Window polling ────────────────────────────────────────────────────────

    def _start_window_poll(self):
        def _poll():
            if not self.winfo_exists():
                return
            self._active_window = self._wm.get_active_window()
            try:
                self._refresh_window_panel()
            except Exception:
                pass
            self.after(800, _poll)
        self.after(500, _poll)

    # ── Close ─────────────────────────────────────────────────────────────────

    def _on_close_btn(self):
        self._stop_event.set()
        self._running = False
        if self._on_close:
            self._on_close()
        self.destroy()
