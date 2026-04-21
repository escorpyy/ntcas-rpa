"""
ui/settings_panel.py
====================
SettingsPanel — a full-featured settings tab for Swastik RPA.

Sections (each in its own collapsible card):
  1. Automation Defaults    countdown, between-delay, retries, type interval,
                            pyautogui PAUSE, fail-safe on/off
  2. Keyboard Shortcuts     rebind every app-level hotkey (Ctrl+S, F10, F11 …)
  3. Appearance             theme colours (all T keys), font family & sizes,
                            accent colour presets
  4. Behaviour              dry-run default, screenshot-on-fail, auto-minimise,
                            undo history depth, language
  5. Paths                  default screenshot folder, last-used flow folder
  6. Macro Recorder         auto-wait threshold, double-click window,
                            default wait seconds for manual waits
  7. Vision Agent           default model, max steps, confidence threshold
  8. Advanced               pyautogui FAILSAFE corner, reset all to defaults,
                            export / import settings JSON

All changes are written to _prefs immediately and saved to disk.
The Theme dict (T) is mutated in-place so UI changes apply the next
time widgets are created (a restart notice is shown for font/colour changes).
"""

from __future__ import annotations

import json, os, copy
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

from core.constants import T, _prefs, save_prefs, _PREFS_DIR, PREFS_FILE, _PREFS_DEFAULTS


# ── Accent presets ────────────────────────────────────────────────────────────

ACCENT_PRESETS = [
    ("#388bfd", "GitHub Blue"),
    ("#3fb950", "GitHub Green"),
    ("#bc8cff", "Violet"),
    ("#f78166", "Coral"),
    ("#39c5cf", "Cyan"),
    ("#d29922", "Amber"),
    ("#e3b341", "Gold"),
    ("#ff9966", "Peach"),
    ("#ff6b6b", "Red"),
    ("#4ecdc4", "Teal"),
]

THEME_PRESETS = {
    "GitHub Dark (default)": {
        "bg": "#0d1117", "bg2": "#161b22", "bg3": "#21262d", "bg4": "#30363d",
        "fg": "#e6edf3", "fg2": "#8b949e", "fg3": "#484f58",
    },
    "Pitch Black": {
        "bg": "#000000", "bg2": "#0a0a0a", "bg3": "#141414", "bg4": "#1e1e1e",
        "fg": "#ffffff", "fg2": "#aaaaaa", "fg3": "#555555",
    },
    "Soft Dark": {
        "bg": "#1e1f22", "bg2": "#2b2d31", "bg3": "#313338", "bg4": "#3b3d43",
        "fg": "#dcddde", "fg2": "#b0b3b8", "fg3": "#72767d",
    },
    "Dark Navy": {
        "bg": "#0a0e1a", "bg2": "#0f1629", "bg3": "#1a2340", "bg4": "#243055",
        "fg": "#e2e8f0", "fg2": "#94a3b8", "fg3": "#475569",
    },
    "Monokai": {
        "bg": "#272822", "bg2": "#3e3d32", "bg3": "#49483e", "bg4": "#75715e",
        "fg": "#f8f8f2", "fg2": "#cfcfc2", "fg3": "#75715e",
    },
}

# Default shortcuts — key: (description, default_binding)
DEFAULT_SHORTCUTS = {
    "save_flow":      ("Save Flow",            "Control-s"),
    "load_flow":      ("Load Flow",            "Control-o"),
    "undo":           ("Undo",                 "Control-z"),
    "redo":           ("Redo",                 "Control-y"),
    "dup_step":       ("Duplicate Last Step",  "Control-d"),
    "emergency_stop": ("Emergency Stop",       "F10"),
    "pause_resume":   ("Pause / Resume",       "F11"),
}


# ─────────────────────────────────────────────────────────────────────────────
#  SettingsPanel
# ─────────────────────────────────────────────────────────────────────────────

class SettingsPanel(tk.Frame):
    """
    Drop this into a notebook tab:
        t = tk.Frame(nb, bg=T["bg"])
        nb.add(t, text="  ⚙ Settings  ")
        SettingsPanel(t, app_ref=self).pack(fill="both", expand=True)
    """

    def __init__(self, parent, app_ref=None, **kw):
        super().__init__(parent, bg=T["bg"], **kw)
        self._app       = app_ref        # reference to App for live rebinding
        self._restart_needed = False

        # Load shortcut map from prefs (fall back to defaults)
        stored_sc = _prefs.get("shortcuts", {})
        self._shortcuts: dict[str, tk.StringVar] = {}
        for key, (desc, default) in DEFAULT_SHORTCUTS.items():
            val = stored_sc.get(key, default)
            self._shortcuts[key] = tk.StringVar(value=val)

        self._build()

    # ─────────────────────────────────────────────────────────────────────────
    #  Layout
    # ─────────────────────────────────────────────────────────────────────────

    def _build(self):
        # Scrollable outer container
        outer = tk.Frame(self, bg=T["bg"])
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, bg=T["bg"], highlightthickness=0)
        sb     = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._inner = tk.Frame(canvas, bg=T["bg"])
        win = canvas.create_window((0, 0), window=self._inner, anchor="nw")

        self._inner.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
            lambda e: canvas.itemconfig(win, width=e.width))
        canvas.bind("<MouseWheel>",
            lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        # Page header
        hdr = tk.Frame(self._inner, bg=T["bg2"], pady=14)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚙  Settings",
                 bg=T["bg2"], fg=T["fg"],
                 font=("Segoe UI Semibold", 15)).pack(side="left", padx=20)
        tk.Label(hdr, text="All changes save automatically",
                 bg=T["bg2"], fg=T["fg3"],
                 font=T["font_s"]).pack(side="left", padx=4)

        self._save_indicator = tk.Label(
            hdr, text="", bg=T["bg2"], fg=T["green"], font=T["font_s"])
        self._save_indicator.pack(side="right", padx=20)

        # Section cards
        self._section_automation()
        self._section_shortcuts()
        self._section_appearance()
        self._section_behaviour()
        self._section_paths()
        self._section_macro_recorder()
        self._section_vision_agent()
        self._section_advanced()

    # ─────────────────────────────────────────────────────────────────────────
    #  Shared widgets
    # ─────────────────────────────────────────────────────────────────────────

    def _card(self, title: str, icon: str = "") -> tk.Frame:
        """Create a section card and return the content frame."""
        outer = tk.Frame(self._inner, bg=T["bg"])
        outer.pack(fill="x", padx=20, pady=(12, 0))

        # Collapsible header
        hdr_f  = tk.Frame(outer, bg=T["bg3"], cursor="hand2")
        hdr_f.pack(fill="x")
        arrow  = tk.Label(hdr_f, text="▾", bg=T["bg3"], fg=T["fg2"],
                          font=("Segoe UI", 10))
        arrow.pack(side="left", padx=(10, 0), pady=6)
        tk.Label(hdr_f, text=f"  {icon}  {title}" if icon else f"  {title}",
                 bg=T["bg3"], fg=T["fg"],
                 font=("Segoe UI Semibold", 10)).pack(side="left", pady=8)

        body = tk.Frame(outer, bg=T["bg2"])
        body.pack(fill="x")

        def _toggle(e=None):
            if body.winfo_viewable():
                body.pack_forget()
                arrow.config(text="▸")
            else:
                body.pack(fill="x")
                arrow.config(text="▾")

        hdr_f.bind("<Button-1>", _toggle)
        for w in hdr_f.winfo_children():
            w.bind("<Button-1>", _toggle)

        return body

    def _row(self, parent, label: str, widget_fn, hint: str = "") -> tk.Widget:
        r = tk.Frame(parent, bg=T["bg2"]); r.pack(fill="x", padx=20, pady=5)
        tk.Label(r, text=label, bg=T["bg2"], fg=T["fg2"],
                 font=T["font_b"], width=28, anchor="e").pack(side="left")
        w = widget_fn(r)
        w.pack(side="left", padx=10)
        if hint:
            tk.Label(r, text=hint, bg=T["bg2"], fg=T["fg3"],
                     font=T["font_s"]).pack(side="left")
        return w

    def _entry(self, parent, var, width=10, fg=None):
        return tk.Entry(parent, textvariable=var, width=width,
                        bg=T["bg3"], fg=fg or T["yellow"],
                        insertbackground=T["fg"],
                        font=T["font_m"], relief="flat")

    def _check(self, parent, var, text=""):
        return tk.Checkbutton(parent, variable=var, text=text,
                              bg=T["bg2"], fg=T["fg2"],
                              selectcolor=T["bg3"], activebackground=T["bg2"],
                              font=T["font_b"])

    def _sep(self, parent):
        tk.Frame(parent, bg=T["bg4"], height=1).pack(fill="x", padx=20, pady=4)

    def _flash_saved(self):
        self._save_indicator.config(text="✔  Saved")
        self.after(1800, lambda: self._save_indicator.config(text=""))

    def _auto_save(self, *_):
        save_prefs()
        self._flash_saved()

    # ─────────────────────────────────────────────────────────────────────────
    #  Section 1 — Automation Defaults
    # ─────────────────────────────────────────────────────────────────────────

    def _section_automation(self):
        body = self._card("Automation Defaults", "🤖")

        def pref_var(key, cast=float):
            v = tk.StringVar(value=str(_prefs.get(key, _PREFS_DEFAULTS.get(key, ""))))
            def _write(*_):
                try:
                    _prefs[key] = cast(v.get())
                    self._auto_save()
                except ValueError:
                    pass
            v.trace_add("write", _write)
            return v

        countdown_v  = pref_var("countdown", int)
        between_v    = pref_var("between", float)
        retries_v    = pref_var("retries", int)
        type_iv      = pref_var("type_interval", float)
        pau_v        = pref_var("pyautogui_pause", float)

        self._row(body, "Startup countdown (seconds):", lambda p: self._entry(p, countdown_v),
                  "Delay before automation begins")
        self._row(body, "Delay between names (seconds):", lambda p: self._entry(p, between_v),
                  "Rest time after processing each name")
        self._row(body, "Retries on failure:", lambda p: self._entry(p, retries_v),
                  "0 = no retry")
        self._row(body, "Type interval (seconds/char):", lambda p: self._entry(p, type_iv),
                  "For type_text steps  (default 0.05)")
        self._row(body, "PyAutoGUI global pause (seconds):", lambda p: self._entry(p, pau_v),
                  "Added after every pyautogui call  (default 0.05)")

        self._sep(body)

        fs_v  = tk.BooleanVar(value=_prefs.get("failsafe", True))
        fss_v = tk.BooleanVar(value=_prefs.get("fail_ss", False))
        dry_v = tk.BooleanVar(value=_prefs.get("dry_run", False))

        def _bpref(key, var):
            def _cmd():
                _prefs[key] = var.get()
                self._auto_save()
            return _cmd

        r1 = tk.Frame(body, bg=T["bg2"]); r1.pack(fill="x", padx=20, pady=6)
        for var, text, key, tip in [
            (fs_v,  "PyAutoGUI fail-safe (mouse corner = emergency stop)", "failsafe",
             "Move mouse to top-left corner to abort"),
            (fss_v, "Screenshot on name failure",                           "fail_ss",
             "Saves a PNG when a name's flow fails"),
            (dry_v, "Practice mode by default (no actual clicks)",          "dry_run",
             "Log steps without executing — useful for testing"),
        ]:
            cb = tk.Checkbutton(r1, text=text, variable=var,
                                bg=T["bg2"], fg=T["fg2"],
                                selectcolor=T["bg3"], activebackground=T["bg2"],
                                font=T["font_b"], command=_bpref(key, var))
            cb.pack(anchor="w", pady=2)
            _tooltip(cb, tip)

        tk.Frame(body, bg=T["bg2"], height=8).pack()

    # ─────────────────────────────────────────────────────────────────────────
    #  Section 2 — Keyboard Shortcuts
    # ─────────────────────────────────────────────────────────────────────────

    def _section_shortcuts(self):
        body = self._card("Keyboard Shortcuts", "⌨")

        tk.Label(body,
                 text="  Click a field and press your desired key combination.  "
                      "Changes take effect after restart.",
                 bg=T["bg2"], fg=T["fg3"], font=T["font_s"]
                 ).pack(anchor="w", padx=20, pady=(8, 4))

        for key, (desc, default) in DEFAULT_SHORTCUTS.items():
            var = self._shortcuts[key]
            r   = tk.Frame(body, bg=T["bg2"]); r.pack(fill="x", padx=20, pady=4)
            tk.Label(r, text=desc, bg=T["bg2"], fg=T["fg2"],
                     font=T["font_b"], width=26, anchor="e").pack(side="left")

            entry = tk.Entry(r, textvariable=var, width=20,
                             bg=T["bg3"], fg=T["cyan"],
                             insertbackground=T["fg"],
                             font=("Consolas", 9), relief="flat")
            entry.pack(side="left", padx=10)

            # Capture key press and format it
            def _on_key(event, v=var, e_ref=entry):
                parts = []
                if event.state & 0x4:  parts.append("Control")
                if event.state & 0x1:  parts.append("Shift")
                if event.state & 0x8:  parts.append("Alt")
                key_sym = event.keysym
                if key_sym not in ("Control_L","Control_R","Shift_L","Shift_R",
                                   "Alt_L","Alt_R","Super_L","Super_R"):
                    parts.append(key_sym)
                combo = "-".join(parts)
                if combo:
                    v.set(combo)
                return "break"

            entry.bind("<KeyPress>", _on_key)

            # Reset button
            def _reset(v=var, d=default):
                v.set(d)
                self._save_shortcuts()
            tk.Button(r, text="↺ Reset", bg=T["bg3"], fg=T["fg3"],
                      font=T["font_s"], relief="flat", cursor="hand2",
                      command=_reset).pack(side="left", padx=4)

            var.trace_add("write", lambda *_: self._save_shortcuts())

        r_all = tk.Frame(body, bg=T["bg2"]); r_all.pack(fill="x", padx=20, pady=10)
        tk.Button(r_all, text="↺  Reset All Shortcuts to Default",
                  bg=T["bg3"], fg=T["red"],
                  font=T["font_b"], relief="flat", cursor="hand2",
                  padx=10, pady=5,
                  command=self._reset_all_shortcuts).pack(side="left")

        tk.Label(r_all,
                 text="Tip: F-keys don't need modifiers (just type F10).",
                 bg=T["bg2"], fg=T["fg3"], font=T["font_s"]).pack(side="left", padx=12)

        tk.Frame(body, bg=T["bg2"], height=6).pack()

    def _save_shortcuts(self):
        _prefs["shortcuts"] = {k: v.get() for k, v in self._shortcuts.items()}
        self._auto_save()
        if self._app:
            try:
                self._app._apply_shortcuts()
            except Exception:
                pass

    def _reset_all_shortcuts(self):
        for key, (desc, default) in DEFAULT_SHORTCUTS.items():
            self._shortcuts[key].set(default)
        self._save_shortcuts()

    # ─────────────────────────────────────────────────────────────────────────
    #  Section 3 — Appearance
    # ─────────────────────────────────────────────────────────────────────────

    def _section_appearance(self):
        body = self._card("Appearance", "🎨")

        tk.Label(body,
                 text="  Colour and font changes apply after restarting the app.",
                 bg=T["bg2"], fg=T["fg3"], font=T["font_s"]
                 ).pack(anchor="w", padx=20, pady=(8, 4))

        # ── Theme presets ─────────────────────────────────────────────────────
        tp = tk.Frame(body, bg=T["bg2"]); tp.pack(fill="x", padx=20, pady=(4, 8))
        tk.Label(tp, text="Theme preset:", bg=T["bg2"], fg=T["fg2"],
                 font=T["font_b"]).pack(side="left")
        for name, colors in THEME_PRESETS.items():
            short = name.split("(")[0].strip()
            tk.Button(tp, text=short,
                      bg=T["bg3"], fg=T["fg2"],
                      font=T["font_s"], relief="flat", cursor="hand2",
                      padx=8, pady=4,
                      command=lambda c=colors, n=name: self._apply_theme_preset(c, n)
                      ).pack(side="left", padx=3)

        self._sep(body)

        # ── Accent presets ────────────────────────────────────────────────────
        ap = tk.Frame(body, bg=T["bg2"]); ap.pack(fill="x", padx=20, pady=(4, 8))
        tk.Label(ap, text="Accent colour:", bg=T["bg2"], fg=T["fg2"],
                 font=T["font_b"]).pack(side="left")
        for hex_c, label in ACCENT_PRESETS:
            btn = tk.Button(ap, text="  ", bg=hex_c, relief="flat",
                            cursor="hand2", width=2,
                            command=lambda h=hex_c: self._set_accent(h))
            btn.pack(side="left", padx=2)
            _tooltip(btn, label)
        tk.Button(ap, text="Custom…", bg=T["bg3"], fg=T["fg2"],
                  font=T["font_s"], relief="flat", cursor="hand2",
                  command=self._pick_accent).pack(side="left", padx=8)

        self._sep(body)

        # ── Individual colour pickers ─────────────────────────────────────────
        colour_keys = [
            ("bg",      "Background"),
            ("bg2",     "Background 2 (cards)"),
            ("bg3",     "Background 3 (inputs)"),
            ("fg",      "Foreground (primary text)"),
            ("fg2",     "Foreground 2 (secondary)"),
            ("fg3",     "Foreground 3 (muted)"),
            ("acc",     "Accent / links"),
            ("green",   "Green (success)"),
            ("red",     "Red (error/stop)"),
            ("yellow",  "Yellow (warning)"),
            ("purple",  "Purple"),
            ("cyan",    "Cyan"),
        ]
        grid = tk.Frame(body, bg=T["bg2"]); grid.pack(fill="x", padx=20, pady=4)
        cols = 3
        for idx, (tkey, label) in enumerate(colour_keys):
            r = idx // cols
            c = idx % cols
            cell = tk.Frame(grid, bg=T["bg2"]); cell.grid(row=r, column=c, padx=8, pady=4, sticky="w")
            swatch = tk.Label(cell, text="  ", bg=T.get(tkey, "#888"),
                              width=3, relief="flat", cursor="hand2")
            swatch.pack(side="left")
            tk.Label(cell, text=label, bg=T["bg2"], fg=T["fg2"],
                     font=T["font_s"]).pack(side="left", padx=4)
            hex_lbl = tk.Label(cell, text=T.get(tkey, "?"),
                               bg=T["bg2"], fg=T["fg3"], font=("Consolas", 8))
            hex_lbl.pack(side="left")

            def _pick(k=tkey, sw=swatch, hl=hex_lbl):
                cur  = T.get(k, "#888888")
                rgb, hex_c = colorchooser.askcolor(color=cur, title=f"Pick colour — {k}")
                if hex_c:
                    T[k] = hex_c
                    sw.config(bg=hex_c); hl.config(text=hex_c)
                    _prefs.setdefault("theme_overrides", {})[k] = hex_c
                    self._auto_save()
                    self._mark_restart()

            swatch.bind("<Button-1>", lambda e, fn=_pick: fn())

        self._sep(body)

        # ── Fonts ─────────────────────────────────────────────────────────────
        font_frame = tk.Frame(body, bg=T["bg2"]); font_frame.pack(fill="x", padx=20, pady=6)
        tk.Label(font_frame, text="UI font family:", bg=T["bg2"], fg=T["fg2"],
                 font=T["font_b"]).pack(side="left")

        ui_fonts = ["Segoe UI", "Calibri", "Arial", "Helvetica", "Tahoma",
                    "Verdana", "Inter", "Roboto"]
        font_v = tk.StringVar(value=_prefs.get("ui_font", "Segoe UI"))
        cb = ttk.Combobox(font_frame, textvariable=font_v,
                          values=ui_fonts, state="readonly", width=18)
        cb.pack(side="left", padx=10)

        tk.Label(font_frame, text="Size:", bg=T["bg2"], fg=T["fg2"],
                 font=T["font_b"]).pack(side="left")
        size_v = tk.StringVar(value=str(_prefs.get("ui_font_size", 9)))
        tk.Spinbox(font_frame, from_=7, to=16, textvariable=size_v,
                   width=4, bg=T["bg3"], fg=T["fg"],
                   buttonbackground=T["bg4"], relief="flat"
                   ).pack(side="left", padx=6)

        def _apply_font(*_):
            _prefs["ui_font"]      = font_v.get()
            _prefs["ui_font_size"] = int(size_v.get() or 9)
            self._auto_save()
            self._mark_restart()

        font_v.trace_add("write", _apply_font)
        size_v.trace_add("write", _apply_font)

        tk.Frame(body, bg=T["bg2"], height=6).pack()

    def _apply_theme_preset(self, colors: dict, name: str):
        for k, v in colors.items():
            T[k] = v
        overrides = _prefs.setdefault("theme_overrides", {})
        overrides.update(colors)
        self._auto_save()
        self._mark_restart()
        messagebox.showinfo("Theme applied",
            f"'{name}' applied. Restart the app to see all changes.")

    def _set_accent(self, hex_c: str):
        T["acc"] = hex_c
        T["acc_dark"] = hex_c  # simplified — could darken programmatically
        _prefs.setdefault("theme_overrides", {})["acc"] = hex_c
        _prefs.setdefault("theme_overrides", {})["acc_dark"] = hex_c
        self._auto_save()
        self._mark_restart()

    def _pick_accent(self):
        _, hex_c = colorchooser.askcolor(color=T["acc"], title="Pick accent colour")
        if hex_c:
            self._set_accent(hex_c)

    def _mark_restart(self):
        self._restart_needed = True
        self._save_indicator.config(
            text="✔ Saved — restart to apply visual changes", fg=T["yellow"])

    # ─────────────────────────────────────────────────────────────────────────
    #  Section 4 — Behaviour
    # ─────────────────────────────────────────────────────────────────────────

    def _section_behaviour(self):
        body = self._card("Behaviour", "🔧")

        # Language
        lr = tk.Frame(body, bg=T["bg2"]); lr.pack(fill="x", padx=20, pady=8)
        tk.Label(lr, text="Interface language:", bg=T["bg2"], fg=T["fg2"],
                 font=T["font_b"], width=28, anchor="e").pack(side="left")
        lang_v = tk.StringVar(value=_prefs.get("lang", "en"))
        for code, lbl in [("en", "English"), ("np", "Nepali (नेपाली)")]:
            tk.Radiobutton(lr, text=lbl, variable=lang_v, value=code,
                           bg=T["bg2"], fg=T["fg2"], selectcolor=T["bg3"],
                           activebackground=T["bg2"], font=T["font_b"],
                           command=lambda: (
                               _prefs.__setitem__("lang", lang_v.get()),
                               self._auto_save(),
                               messagebox.showinfo("Language",
                                   "Language saved. Restart the app to apply."))
                           ).pack(side="left", padx=8)

        self._sep(body)

        # Undo depth
        undo_v = tk.StringVar(value=str(_prefs.get("undo_depth", 40)))
        def _undo_save(*_):
            try:
                _prefs["undo_depth"] = max(5, int(undo_v.get() or 40))
                self._auto_save()
            except ValueError:
                pass
        undo_v.trace_add("write", _undo_save)
        self._row(body, "Undo history depth:", lambda p: self._entry(p, undo_v, 6),
                  "Max undoable actions per flow panel")

        # Auto-minimise on run
        am_v = tk.BooleanVar(value=_prefs.get("auto_minimise", True))
        def _am():
            _prefs["auto_minimise"] = am_v.get(); self._auto_save()
        r = tk.Frame(body, bg=T["bg2"]); r.pack(fill="x", padx=20, pady=4)
        tk.Checkbutton(r, text="Auto-minimise window when run starts",
                       variable=am_v, bg=T["bg2"], fg=T["fg2"],
                       selectcolor=T["bg3"], activebackground=T["bg2"],
                       font=T["font_b"], command=_am).pack(anchor="w")

        # Confirm before clear
        cc_v = tk.BooleanVar(value=_prefs.get("confirm_clear", True))
        def _cc():
            _prefs["confirm_clear"] = cc_v.get(); self._auto_save()
        r2 = tk.Frame(body, bg=T["bg2"]); r2.pack(fill="x", padx=20, pady=4)
        tk.Checkbutton(r2, text="Ask confirmation before clearing all steps",
                       variable=cc_v, bg=T["bg2"], fg=T["fg2"],
                       selectcolor=T["bg3"], activebackground=T["bg2"],
                       font=T["font_b"], command=_cc).pack(anchor="w")

        # Warn zero coords
        wz_v = tk.BooleanVar(value=_prefs.get("warn_zero_coords", True))
        def _wz():
            _prefs["warn_zero_coords"] = wz_v.get(); self._auto_save()
        r3 = tk.Frame(body, bg=T["bg2"]); r3.pack(fill="x", padx=20, pady=4)
        tk.Checkbutton(r3, text="Warn when click steps have (0, 0) coordinates",
                       variable=wz_v, bg=T["bg2"], fg=T["fg2"],
                       selectcolor=T["bg3"], activebackground=T["bg2"],
                       font=T["font_b"], command=_wz).pack(anchor="w")

        # Show step count badge
        sc_v = tk.BooleanVar(value=_prefs.get("show_step_count", True))
        def _sc():
            _prefs["show_step_count"] = sc_v.get(); self._auto_save()
        r4 = tk.Frame(body, bg=T["bg2"]); r4.pack(fill="x", padx=20, pady=4)
        tk.Checkbutton(r4, text="Show step count badge on flow panel",
                       variable=sc_v, bg=T["bg2"], fg=T["fg2"],
                       selectcolor=T["bg3"], activebackground=T["bg2"],
                       font=T["font_b"], command=_sc).pack(anchor="w")

        tk.Frame(body, bg=T["bg2"], height=6).pack()

    # ─────────────────────────────────────────────────────────────────────────
    #  Section 5 — Paths
    # ─────────────────────────────────────────────────────────────────────────

    def _section_paths(self):
        body = self._card("Paths & Folders", "📁")

        for pref_key, label, hint in [
            ("screenshot_folder", "Default screenshot folder:",
             "Where Take Screenshot steps save files"),
            ("flow_folder",       "Default flow folder:",
             "Opening folder for Save/Load flow dialogs"),
            ("export_folder",     "Default log export folder:",
             "Folder for exported log files"),
        ]:
            r = tk.Frame(body, bg=T["bg2"]); r.pack(fill="x", padx=20, pady=6)
            tk.Label(r, text=label, bg=T["bg2"], fg=T["fg2"],
                     font=T["font_b"], width=28, anchor="e").pack(side="left")
            v = tk.StringVar(value=_prefs.get(pref_key, ""))

            def _trace(v=v, k=pref_key):
                def _w(*_):
                    _prefs[k] = v.get()
                    self._auto_save()
                return _w

            v.trace_add("write", _trace())
            ent = tk.Entry(r, textvariable=v, width=32,
                           bg=T["bg3"], fg=T["fg"],
                           insertbackground=T["fg"],
                           font=T["font_m"], relief="flat")
            ent.pack(side="left", padx=8)

            def _browse(v=v):
                p = filedialog.askdirectory()
                if p:
                    v.set(p)
            tk.Button(r, text="Browse…", bg=T["bg3"], fg=T["fg2"],
                      font=T["font_s"], relief="flat", cursor="hand2",
                      command=_browse).pack(side="left")

            if hint:
                tk.Label(r, text=hint, bg=T["bg2"], fg=T["fg3"],
                         font=T["font_s"]).pack(side="left", padx=8)

        tk.Frame(body, bg=T["bg2"], height=6).pack()

    # ─────────────────────────────────────────────────────────────────────────
    #  Section 6 — Macro Recorder
    # ─────────────────────────────────────────────────────────────────────────

    def _section_macro_recorder(self):
        body = self._card("Macro Recorder Pro", "🎙")

        def pref_var(key, default, cast=float):
            v = tk.StringVar(value=str(_prefs.get(key, default)))
            def _write(*_):
                try:
                    _prefs[key] = cast(v.get())
                    self._auto_save()
                except ValueError:
                    pass
            v.trace_add("write", _write)
            return v

        aw_thresh_v  = pref_var("recorder_auto_wait_threshold", 1.5)
        dbl_window_v = pref_var("recorder_dbl_click_window",    0.35)
        wait_dflt_v  = pref_var("recorder_wait_default",        1.0)

        self._row(body, "Auto-Wait threshold (seconds):",
                  lambda p: self._entry(p, aw_thresh_v),
                  "Idle gap that triggers an automatic Wait step")
        self._row(body, "Double-click detection window (seconds):",
                  lambda p: self._entry(p, dbl_window_v),
                  "Max gap between two clicks to count as double-click")
        self._row(body, "Manual Wait step default (seconds):",
                  lambda p: self._entry(p, wait_dflt_v),
                  "Value inserted when you press Ctrl+Shift+W")

        self._sep(body)

        # Auto-wait enabled by default
        aw_on_v = tk.BooleanVar(value=_prefs.get("recorder_auto_wait_on", True))
        def _aw():
            _prefs["recorder_auto_wait_on"] = aw_on_v.get(); self._auto_save()
        r = tk.Frame(body, bg=T["bg2"]); r.pack(fill="x", padx=20, pady=4)
        tk.Checkbutton(r, text="Auto-Wait enabled by default when recorder opens",
                       variable=aw_on_v, bg=T["bg2"], fg=T["fg2"],
                       selectcolor=T["bg3"], activebackground=T["bg2"],
                       font=T["font_b"], command=_aw).pack(anchor="w")

        # Show recorder on top
        top_v = tk.BooleanVar(value=_prefs.get("recorder_topmost", True))
        def _top():
            _prefs["recorder_topmost"] = top_v.get(); self._auto_save()
        r2 = tk.Frame(body, bg=T["bg2"]); r2.pack(fill="x", padx=20, pady=4)
        tk.Checkbutton(r2, text="Keep Macro Recorder window always-on-top",
                       variable=top_v, bg=T["bg2"], fg=T["fg2"],
                       selectcolor=T["bg3"], activebackground=T["bg2"],
                       font=T["font_b"], command=_top).pack(anchor="w")

        tk.Frame(body, bg=T["bg2"], height=6).pack()

    # ─────────────────────────────────────────────────────────────────────────
    #  Section 7 — Vision Agent
    # ─────────────────────────────────────────────────────────────────────────

    def _section_vision_agent(self):
        body = self._card("Vision Agent", "🚀")

        def pref_var(key, default, cast=str):
            v = tk.StringVar(value=str(_prefs.get(key, default)))
            def _write(*_):
                try:
                    _prefs[key] = cast(v.get())
                    self._auto_save()
                except ValueError:
                    pass
            v.trace_add("write", _write)
            return v

        model_v   = pref_var("agent_model",      "llava")
        max_v     = pref_var("agent_max_steps",   30,   int)
        conf_v    = pref_var("agent_confidence",  0.35, float)
        settle_v  = pref_var("agent_settle_time", 0.6,  float)

        self._row(body, "Default model:", lambda p: self._entry(p, model_v, 16, T["fg"]),
                  "e.g. llava  llava:13b  llava-phi3")
        self._row(body, "Max actions per name:", lambda p: self._entry(p, max_v),
                  "Safety limit — agent stops after this many steps")
        self._row(body, "Confidence threshold:", lambda p: self._entry(p, conf_v),
                  "Actions below this confidence are skipped (0.0–1.0)")
        self._row(body, "Settle time after action (seconds):", lambda p: self._entry(p, settle_v),
                  "Brief pause between LLM actions")

        self._sep(body)

        # Show reasoning log
        log_v = tk.BooleanVar(value=_prefs.get("agent_show_log", True))
        def _log():
            _prefs["agent_show_log"] = log_v.get(); self._auto_save()
        r = tk.Frame(body, bg=T["bg2"]); r.pack(fill="x", padx=20, pady=4)
        tk.Checkbutton(r, text="Show live reasoning log panel",
                       variable=log_v, bg=T["bg2"], fg=T["fg2"],
                       selectcolor=T["bg3"], activebackground=T["bg2"],
                       font=T["font_b"], command=_log).pack(anchor="w")

        tk.Frame(body, bg=T["bg2"], height=6).pack()

    # ─────────────────────────────────────────────────────────────────────────
    #  Section 8 — Advanced
    # ─────────────────────────────────────────────────────────────────────────

    def _section_advanced(self):
        body = self._card("Advanced", "🛠")

        # PyAutoGUI fail-safe corner
        fc_r = tk.Frame(body, bg=T["bg2"]); fc_r.pack(fill="x", padx=20, pady=8)
        tk.Label(fc_r, text="Fail-safe corner:", bg=T["bg2"], fg=T["fg2"],
                 font=T["font_b"], width=28, anchor="e").pack(side="left")
        corner_v = tk.StringVar(value=_prefs.get("failsafe_corner", "top-left"))
        corners  = ["top-left", "top-right", "bottom-left", "bottom-right"]
        cb = ttk.Combobox(fc_r, textvariable=corner_v,
                          values=corners, state="readonly", width=14)
        cb.pack(side="left", padx=10)
        def _corner(*_):
            _prefs["failsafe_corner"] = corner_v.get(); self._auto_save()
        corner_v.trace_add("write", _corner)
        tk.Label(fc_r, text="Move mouse here to emergency-stop",
                 bg=T["bg2"], fg=T["fg3"], font=T["font_s"]).pack(side="left", padx=8)

        self._sep(body)

        # Export / Import settings JSON
        ei_r = tk.Frame(body, bg=T["bg2"]); ei_r.pack(fill="x", padx=20, pady=8)
        tk.Button(ei_r, text="📤  Export Settings",
                  bg=T["bg3"], fg=T["fg2"],
                  font=T["font_b"], relief="flat", cursor="hand2",
                  padx=10, pady=5, command=self._export_settings
                  ).pack(side="left")
        tk.Button(ei_r, text="📥  Import Settings",
                  bg=T["bg3"], fg=T["fg2"],
                  font=T["font_b"], relief="flat", cursor="hand2",
                  padx=10, pady=5, command=self._import_settings
                  ).pack(side="left", padx=8)
        tk.Label(ei_r, text="Share your settings between machines",
                 bg=T["bg2"], fg=T["fg3"], font=T["font_s"]).pack(side="left", padx=8)

        self._sep(body)

        # Open prefs folder
        pf_r = tk.Frame(body, bg=T["bg2"]); pf_r.pack(fill="x", padx=20, pady=6)
        tk.Button(pf_r, text="📂  Open Settings Folder",
                  bg=T["bg3"], fg=T["fg2"],
                  font=T["font_b"], relief="flat", cursor="hand2",
                  padx=10, pady=5,
                  command=lambda: os.startfile(_PREFS_DIR) if os.name == "nt"
                          else os.system(f'xdg-open "{_PREFS_DIR}"')
                  ).pack(side="left")
        tk.Label(pf_r, text=_PREFS_DIR,
                 bg=T["bg2"], fg=T["fg3"], font=("Consolas", 8)).pack(side="left", padx=10)

        self._sep(body)

        # Danger zone
        dz = tk.Frame(body, bg=T["bg2"]); dz.pack(fill="x", padx=20, pady=10)
        tk.Label(dz, text="⚠  Danger Zone", bg=T["bg2"], fg=T["red"],
                 font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(0, 6))

        btn_r = tk.Frame(dz, bg=T["bg2"]); btn_r.pack(anchor="w")
        tk.Button(btn_r, text="↺  Reset All Settings to Default",
                  bg=T["red_bg"], fg=T["red"],
                  font=T["font_b"], relief="flat", cursor="hand2",
                  padx=12, pady=6,
                  command=self._reset_all).pack(side="left")
        tk.Label(btn_r,
                 text="Clears every customisation — cannot be undone.",
                 bg=T["bg2"], fg=T["fg3"], font=T["font_s"]).pack(side="left", padx=12)

        tk.Frame(body, bg=T["bg2"], height=10).pack()

    # ─────────────────────────────────────────────────────────────────────────
    #  Actions
    # ─────────────────────────────────────────────────────────────────────────

    def _export_settings(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            initialfile="swastik_settings.json",
            filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(_prefs, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Exported", f"Settings saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _import_settings(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            _prefs.update(data)
            save_prefs()
            messagebox.showinfo("Imported",
                "Settings imported. Restart the app to apply all changes.")
        except Exception as e:
            messagebox.showerror("Import Error", str(e))

    def _reset_all(self):
        if not messagebox.askyesno(
            "Reset all settings?",
            "This will reset EVERYTHING — colours, shortcuts, all preferences.\n\n"
            "This cannot be undone. Continue?",
            icon="warning"
        ):
            return
        _prefs.clear()
        _prefs.update(copy.deepcopy(_PREFS_DEFAULTS))
        save_prefs()
        messagebox.showinfo("Reset complete",
            "All settings have been reset to defaults.\nRestart the app to apply.")


# ── Tooltip helper (standalone so no circular import needed) ──────────────────

def _tooltip(widget: tk.Widget, text: str):
    tip: list = [None]

    def _show(e):
        if tip[0]: return
        tw = tk.Toplevel(widget)
        tw.wm_overrideredirect(True)
        tw.configure(bg=T["bg4"])
        tk.Label(tw, text=text, bg=T["bg4"], fg=T["fg2"],
                 font=T["font_s"], padx=8, pady=4,
                 relief="flat", wraplength=280, justify="left").pack()
        x = widget.winfo_rootx() + 20
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        tw.wm_geometry(f"+{x}+{y}")
        tip[0] = tw

    def _hide(e):
        if tip[0]:
            try: tip[0].destroy()
            except Exception: pass
            tip[0] = None

    widget.bind("<Enter>", _show)
    widget.bind("<Leave>", _hide)
