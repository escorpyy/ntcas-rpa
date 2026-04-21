"""
ui/app.py
=========
Main application window: App(tk.Tk)

Tabs:
  1. Name List
  2. Build Flow  (main flow + optional first-name flow)
  3. Run
  4. Agent       (Macro Recorder Pro + Vision Agent)
  5. ⚙ Settings  (NEW — full customisation)
  6. Help

Shortcuts are read from _prefs["shortcuts"] at startup and re-applied live
whenever SettingsPanel calls app._apply_shortcuts().
"""

import copy, datetime, json, os, queue, time, threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pyautogui

from core.constants import (
    T, APP_VERSION, L, set_lang,
    _prefs, save_prefs, _DIR,
    load_json_file, save_json_file,
)
from core.executor import FlowExecutor

from ui.dialogs import (
    Tooltip, VariableDialog, VariableFillDialog, HelpPanel,
)
from ui.panels import (
    FlowPanel, NameListPanel, RunStatusPanel,
)
from ui.settings_panel import SettingsPanel, DEFAULT_SHORTCUTS


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Swastik RPA  ·  Automation Flow Builder  v{APP_VERSION}")
        self.configure(bg=T["bg"])
        self.minsize(980, 720)

        self._executor  = None
        self._thread    = None
        self._log_queue = queue.Queue()
        self._run_start = None
        self._variables: dict = {}
        self._bound_shortcuts: list = []

        # Apply any saved theme colour overrides before building widgets
        self._apply_theme_overrides()

        self._style_ttk()
        self._build()
        self._apply_shortcuts()
        self._poll_log()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Theme overrides ───────────────────────────────────────────────────────

    def _apply_theme_overrides(self):
        for k, v in _prefs.get("theme_overrides", {}).items():
            if k in T:
                T[k] = v

    # ── Shortcuts (live-rebindable from Settings) ─────────────────────────────

    def _apply_shortcuts(self):
        """Read shortcuts from _prefs and bind them. Called at startup and
        every time SettingsPanel saves a shortcut change."""
        sc = _prefs.get("shortcuts", {})

        def _get(key):
            raw = sc.get(key, DEFAULT_SHORTCUTS[key][1])
            return raw.replace("+", "-")

        # Remove old bindings
        for seq in self._bound_shortcuts:
            try:
                self.unbind(seq)
            except Exception:
                pass
        self._bound_shortcuts.clear()

        def _bind(seq, fn):
            try:
                full = f"<{seq}>"
                self.bind(full, fn)
                self._bound_shortcuts.append(full)
            except Exception as e:
                print(f"[shortcuts] cannot bind <{seq}>: {e}")

        _bind(_get("save_flow"),      lambda e: self._save_flow())
        _bind(_get("load_flow"),      lambda e: self._load_flow())
        _bind(_get("undo"),           lambda e: self._active_panel().undo())
        _bind(_get("redo"),           lambda e: self._active_panel().redo())
        _bind(_get("dup_step"),       lambda e: self._dup_last_step())
        _bind(_get("emergency_stop"), lambda e: self._do_stop())
        _bind(_get("pause_resume"),   lambda e: self._pause_resume())

    def _dup_last_step(self):
        p = self._active_panel()
        if p.steps:
            p._dup(len(p.steps) - 1)

    # ── TTK style ─────────────────────────────────────────────────────────────

    def _style_ttk(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TCombobox",
                    fieldbackground=T["bg3"], background=T["bg3"],
                    foreground=T["fg"], arrowcolor=T["fg2"])
        s.configure("Vertical.TScrollbar",
                    background=T["bg3"], troughcolor=T["bg2"], arrowcolor=T["fg3"])
        s.configure("TProgressbar",
                    troughcolor=T["bg3"], background=T["green"], thickness=5)
        s.configure("TNotebook", background=T["bg2"], borderwidth=0)
        s.configure("TNotebook.Tab",
                    background=T["bg3"], foreground=T["fg2"],
                    padding=[16, 8], font=("Segoe UI Semibold", 9), borderwidth=0)
        s.map("TNotebook.Tab",
              background=[("selected", T["bg"]),  ("active", T["bg4"])],
              foreground=[("selected", T["fg"]),   ("active", T["fg"])])

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        top = tk.Frame(self, bg=T["bg2"], pady=10); top.pack(fill="x")
        tk.Label(top, text="Swastik RPA",
                 font=("Segoe UI Semibold", 14),
                 bg=T["bg2"], fg=T["fg"]).pack(side="left", padx=16)
        tk.Label(top, text=f"v{APP_VERSION}",
                 font=T["font_s"], bg=T["bg2"], fg=T["fg3"]).pack(side="left", padx=2)

        vb = tk.Button(top, text="⟨⟩ Variables",
                       bg=T["bg3"], fg=T["purple"],
                       font=T["font_s"], relief="flat", cursor="hand2",
                       padx=8, pady=4, command=self._open_variables)
        vb.pack(side="right", padx=4)
        Tooltip(vb, "Define {varname} placeholders filled in at run time")

        for txt, cmd, tip in [
            ("💾 Save", self._save_flow, "Save flow"),
            ("📂 Load", self._load_flow, "Load flow"),
        ]:
            b = tk.Button(top, text=txt, bg=T["bg3"], fg=T["fg2"],
                          font=T["font_s"], relief="flat", cursor="hand2",
                          padx=8, pady=4, command=cmd)
            b.pack(side="right", padx=4)
            Tooltip(b, tip)

        mf = tk.Frame(top, bg=T["bg3"], padx=10, pady=4)
        mf.pack(side="right", padx=12)
        tk.Label(mf, text="🖱", bg=T["bg3"], fg=T["fg3"],
                 font=("Segoe UI", 9)).pack(side="left")
        self._mouse_lbl = tk.Label(mf, text="0, 0",
                                   bg=T["bg3"], fg=T["cyan"],
                                   font=T["font_m"], width=12)
        self._mouse_lbl.pack(side="left", padx=4)
        self._poll_mouse()

        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True)
        self._nb = nb

        t1 = tk.Frame(nb, bg=T["bg"]); nb.add(t1, text=f"  {L('names_tab')}  ")
        self._name_panel = NameListPanel(t1)
        self._name_panel.pack(fill="both", expand=True, padx=20, pady=16)

        t2 = tk.Frame(nb, bg=T["bg"]); nb.add(t2, text=f"  {L('flow_tab')}  ")
        self._build_flow_tab(t2)

        t3 = tk.Frame(nb, bg=T["bg"]); nb.add(t3, text=f"  {L('run_tab')}  ")
        self._run_panel = RunStatusPanel(t3)
        self._run_panel.pack(fill="both", expand=True, padx=20, pady=16)
        self._run_panel.on_start_cb       = self._start
        self._run_panel.on_pause_cb       = self._pause_resume
        self._run_panel.on_stop_cb        = self._do_stop
        self._run_panel.on_test_single_cb = self._start_single

        t4 = tk.Frame(nb, bg=T["bg"]); nb.add(t4, text=f"  {L('agent_tab')}  ")
        self._build_agent_tab(t4)

        # ── Settings tab ──────────────────────────────────────────────────────
        t5 = tk.Frame(nb, bg=T["bg"]); nb.add(t5, text="  ⚙ Settings  ")
        SettingsPanel(t5, app_ref=self).pack(fill="both", expand=True)

        t6 = tk.Frame(nb, bg=T["bg"]); nb.add(t6, text=f"  {L('help_tab')}  ")
        HelpPanel(t6).pack(fill="both", expand=True)

    # ── Flow tab ──────────────────────────────────────────────────────────────

    def _build_flow_tab(self, parent):
        self._use_first = tk.BooleanVar(value=False)
        top = tk.Frame(parent, bg=T["bg"]); top.pack(fill="x", padx=20, pady=(12, 0))
        cb = tk.Checkbutton(
            top,
            text="Use a different flow for the FIRST name only  (e.g. for login steps)",
            variable=self._use_first, command=self._toggle_first,
            bg=T["bg"], fg=T["yellow"], selectcolor=T["bg3"],
            font=T["font_b"], activebackground=T["bg"])
        cb.pack(side="left")
        Tooltip(cb, "Enable to add one-time login steps that only run for name #1")

        self._panels_frame = tk.Frame(parent, bg=T["bg"])
        self._panels_frame.pack(fill="both", expand=True, padx=20, pady=8)
        self._panels_frame.columnconfigure(0, weight=1)
        self._panels_frame.columnconfigure(1, weight=1)

        def get_first():  return self._fp.get() if self._fp.winfo_ismapped() else None
        def get_repeat(): return self._rp.get()

        self._fp = FlowPanel(self._panels_frame, "first",  other_panel_fn=get_repeat)
        self._rp = FlowPanel(self._panels_frame, "repeat", other_panel_fn=get_first)
        self._rp.grid(row=0, column=0, columnspan=2, sticky="nsew")

        self._fp_lbl = tk.Label(self._panels_frame,
                                text="FIRST NAME FLOW  (runs once for name #1)",
                                bg=T["bg"], fg=T["yellow"],
                                font=("Segoe UI Semibold", 8))
        self._rp_lbl = tk.Label(self._panels_frame,
                                text="MAIN FLOW  (runs for every name)",
                                bg=T["bg"], fg=T["acc"],
                                font=("Segoe UI Semibold", 8))
        self._rp_lbl.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def _toggle_first(self):
        if self._use_first.get():
            self._fp_lbl.grid(row=1, column=0, sticky="w", pady=(4, 0))
            self._rp_lbl.grid(row=1, column=1, sticky="w", pady=(4, 0))
            self._fp.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
            self._rp.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
            self._rp.grid_configure(columnspan=1)
        else:
            self._fp.grid_remove()
            self._fp_lbl.grid_remove()
            self._rp.grid(row=0, column=0, columnspan=2, sticky="nsew")
            self._rp_lbl.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def _active_panel(self) -> FlowPanel:
        return self._rp

    # ── Agent tab ─────────────────────────────────────────────────────────────

    def _build_agent_tab(self, parent):
        tk.Label(parent,
                 text="Agent Tools  —  two ways to automate without manually building steps",
                 bg=T["bg"], fg=T["fg2"], font=T["font_h"]
                 ).pack(padx=24, pady=(20, 12))

        rec_card = tk.Frame(parent, bg=T["bg2"])
        rec_card.pack(fill="x", padx=24, pady=(0, 16))
        tk.Frame(rec_card, bg=T["red"], width=6).pack(side="left", fill="y")
        rc = tk.Frame(rec_card, bg=T["bg2"]); rc.pack(fill="both", expand=True, padx=16, pady=14)
        tk.Label(rc, text="🎙  Macro Recorder Pro",
                 bg=T["bg2"], fg=T["fg"],
                 font=("Segoe UI Semibold", 12)).pack(anchor="w")
        tk.Label(rc,
                 text=("Record your actual mouse clicks and keyboard presses.\n"
                       "Pro features: Pause mode · Auto-Wait injection · Global shortcuts.\n"
                       "Configure recorder settings in the ⚙ Settings tab."),
                 bg=T["bg2"], fg=T["fg2"], font=T["font_b"], justify="left"
                 ).pack(anchor="w", pady=(4, 10))
        tk.Label(rc, text="Requires:  pip install pynput",
                 bg=T["bg2"], fg=T["fg3"], font=T["font_s"]).pack(anchor="w")
        tk.Button(rc, text="Open Macro Recorder Pro",
                  bg=T["red"], fg="white",
                  font=("Segoe UI Semibold", 10), relief="flat", cursor="hand2",
                  padx=14, pady=7, command=self._open_recorder
                  ).pack(anchor="w", pady=(10, 0))

        va_card = tk.Frame(parent, bg=T["bg2"])
        va_card.pack(fill="x", padx=24, pady=(0, 16))
        tk.Frame(va_card, bg=T["green"], width=6).pack(side="left", fill="y")
        vc = tk.Frame(va_card, bg=T["bg2"]); vc.pack(fill="both", expand=True, padx=16, pady=14)
        tk.Label(vc, text="🚀  Vision Agent  (AI-powered)",
                 bg=T["bg2"], fg=T["fg"],
                 font=("Segoe UI Semibold", 12)).pack(anchor="w")
        tk.Label(vc,
                 text=("Describe your goal in plain English or Nepali.\n"
                       "The AI sees your screen, decides what to click or type,\n"
                       "and acts automatically for every name in your list.\n"
                       "Configure model and thresholds in the ⚙ Settings tab."),
                 bg=T["bg2"], fg=T["fg2"], font=T["font_b"], justify="left"
                 ).pack(anchor="w", pady=(4, 10))
        tk.Label(vc, text="Requires:  pip install ollama   +   ollama pull llava",
                 bg=T["bg2"], fg=T["fg3"], font=T["font_s"]).pack(anchor="w")
        tk.Button(vc, text="Open Vision Agent",
                  bg=T["green"], fg=T["bg"],
                  font=("Segoe UI Semibold", 10), relief="flat", cursor="hand2",
                  padx=14, pady=7, command=self._open_vision_agent
                  ).pack(anchor="w", pady=(10, 0))

    # ── Agent launchers ───────────────────────────────────────────────────────

    def _open_recorder(self):
        from agent.macro_recorder import MacroRecorderPro

        def _on_import(steps):
            self._rp._save_undo()
            self._rp.steps = copy.deepcopy(steps)
            self._rp._refresh()
            self._run_panel.log(
                f"Macro Recorder imported {len(steps)} step(s) into Main Flow.", "ok")
            messagebox.showinfo("Imported",
                f"{len(steps)} step(s) imported.\nSwitch to Build Flow to review them.")

        MacroRecorderPro(self, on_import=_on_import)

    def _open_vision_agent(self):
        from agent.vision_agent import AutonomousVisionAgent

        names = self._name_panel.get_names()
        if not names:
            messagebox.showwarning("No Names", "Please add names to the Name List first.")
            return
        AutonomousVisionAgent(self, names=names, variables=dict(self._variables))

    # ── Variables ─────────────────────────────────────────────────────────────

    def _open_variables(self):
        def _on_save(new_vars):
            self._variables = dict(new_vars)
        VariableDialog(self, self._variables, _on_save)

    # ── Mouse tracker ─────────────────────────────────────────────────────────

    def _poll_mouse(self):
        try:
            x, y = pyautogui.position()
            self._mouse_lbl.config(text=f"{x},  {y}")
        except Exception:
            pass
        self.after(100, self._poll_mouse)

    # ── Save / Load flow ──────────────────────────────────────────────────────

    def _save_flow(self, e=None):
        init_dir = _prefs.get("flow_folder", "")
        path = filedialog.asksaveasfilename(
            initialdir=init_dir or None,
            defaultextension=".json",
            filetypes=[("Flow JSON", "*.json"), ("All", "*.*")])
        if not path: return
        _prefs["flow_folder"] = os.path.dirname(path)
        s = self._run_panel.get_settings()
        data = {
            "app_version": APP_VERSION,
            "saved_at":    datetime.datetime.now().isoformat(),
            "use_first":   self._use_first.get(),
            "first":       self._fp.get(),
            "repeat":      self._rp.get(),
            "variables":   self._variables,
            "settings":    s,
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self._run_panel.log(f"Flow saved → {os.path.basename(path)}", "ok")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def _load_flow(self, e=None):
        init_dir = _prefs.get("flow_folder", "")
        path = filedialog.askopenfilename(
            initialdir=init_dir or None,
            filetypes=[("Flow JSON", "*.json"), ("All", "*.*")])
        if not path: return
        _prefs["flow_folder"] = os.path.dirname(path)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self._use_first.set(data.get("use_first", False))
            self._toggle_first()
            self._fp.load(data.get("first", []))
            self._rp.load(data.get("repeat", []))
            self._variables = data.get("variables", {})
            s = data.get("settings", {})
            for k in ("countdown", "between", "retries"):
                if k in s and k in self._run_panel._svars:
                    self._run_panel._svars[k].set(str(s[k]))
            self._run_panel.log(f"Flow loaded ← {os.path.basename(path)}", "ok")
        except Exception as e:
            messagebox.showerror("Load Error", str(e))

    # ── Run ───────────────────────────────────────────────────────────────────

    def _start(self):
        names = self._name_panel.get_names()
        if not names:
            messagebox.showwarning("No Names", L("no_names_warn"))
            return
        self._run(names)

    def _start_single(self, name: str):
        if not name:
            messagebox.showwarning("Empty", "Enter a name to test with.")
            return
        self._run([name])

    def _run(self, names: list):
        flow = self._rp.get()
        if not flow:
            messagebox.showwarning("No Steps", L("no_steps_warn"))
            return

        if _prefs.get("warn_zero_coords", True):
            zero_steps = [
                i+1 for i, s in enumerate(flow)
                if s["type"] in ("click", "double_click", "right_click", "clear_field")
                and s.get("x", 0) == 0 and s.get("y", 0) == 0
                and s.get("enabled", True)
            ]
            if zero_steps:
                if not messagebox.askyesno("Zero coordinates",
                        f"Steps {zero_steps} have coordinates (0, 0).\n"
                        f"They will click the top-left corner.\n\nContinue anyway?"):
                    return

        variables = dict(self._variables)
        if variables:
            dlg = VariableFillDialog(self, variables)
            self.wait_window(dlg)
            if dlg.result is None:
                return
            variables = dlg.result

        first_flow = self._fp.get() if self._use_first.get() else []
        s          = self._run_panel.get_settings()

        self._run_panel.set_running(True, len(names))
        self._run_start = time.time()
        self._update_timer()

        if _prefs.get("auto_minimise", True):
            self.iconify()

        self._launch(names, flow, first_flow, s, variables)

    def _launch(self, names, flow, first_flow, s, variables):
        self._executor = FlowExecutor(
            names, flow,
            first_flow  = first_flow,
            log_fn      = self._log_queue.put,
            between     = s["between"],
            countdown   = s["countdown"],
            dry_run     = s["dry_run"],
            on_fail_ss  = s["fail_ss"],
            retries     = s["retries"],
            variables   = variables,
            progress_fn = lambda i, n, nm: self.after(0,
                lambda i=i, n=n, nm=nm: self._run_panel.update_progress(i, n, nm)),
            status_fn   = lambda nm, ok: self.after(0,
                lambda nm=nm, ok=ok: self._run_panel.update_name_status(nm, ok)),
            eta_fn      = lambda t: self.after(0,
                lambda t=t: self._run_panel.set_eta(t)),
        )
        self._thread = threading.Thread(target=self._run_thread, daemon=True)
        self._thread.start()

    def _run_thread(self):
        s, f = self._executor.start()
        self.after(0, self._on_done, s, f)

    def _on_done(self, s: int, f: list):
        self.deiconify()
        elapsed = time.time() - self._run_start if self._run_start else 0
        self._run_start = None
        self._run_panel.set_running(False)
        self._run_panel.set_done(s, f, elapsed)

    def _update_timer(self):
        if self._run_start:
            e = time.time() - self._run_start
            self._run_panel.set_timer(f"⏱ {e:.0f}s")
            self.after(1000, self._update_timer)
        else:
            self._run_panel.set_timer("")

    def _pause_resume(self):
        if not self._executor: return
        if self._executor._pause:
            self._executor.resume()
            self._run_panel.toggle_pause_label(False)
            self._run_panel.log("▶ Resumed.", "warn")
        else:
            self._executor.pause()
            self._run_panel.toggle_pause_label(True)
            self._run_panel.log("⏸ Paused.", "warn")

    def _do_stop(self):
        if self._executor:
            self._executor.stop()

    def _poll_log(self):
        batch = []
        try:
            while True:
                batch.append(self._log_queue.get_nowait())
        except queue.Empty:
            pass
        if batch:
            self._run_panel.log("\n".join(batch))
        self.after(50, self._poll_log)

    def _on_close(self):
        if self._executor:
            self._executor.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        save_prefs()
        self.destroy()
