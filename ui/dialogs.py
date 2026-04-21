"""
ui/dialogs.py
=============
Reusable dialog windows:
  Tooltip, VariableDialog, VariableFillDialog,
  FindReplaceDialog, StepPickerDialog, StepEditor,
  HelpPanel, ColumnChooser

IMPROVEMENTS v9.3:
  - StepPickerDialog: cascading connected-dropdown UI — category → step → inline
    config panel appears below, much clearer and more usable than a flat grid
  - StepEditor pos-poll cancelled on destroy to avoid TclError
  - VariableDialog rows dict keyed by frame widget (not overwritten)
"""

import copy, time, re, threading
import tkinter as tk
from tkinter import messagebox, ttk

import pyautogui

from core.constants import (
    T, STEP_TYPES, STEP_FRIENDLY, STEP_DEFAULTS, STEP_COLORS,
    L, _prefs, save_prefs,
)
from core.helpers import step_summary, step_human_label


# ── Step categories for the cascading picker ─────────────────────────────────

STEP_CATEGORIES = {
    "🖱  Mouse Actions": [
        "click", "double_click", "right_click", "mouse_move", "scroll", "clear_field",
    ],
    "⌨  Keyboard": [
        "hotkey", "type_text", "clip_type", "key_repeat", "hold_key",
    ],
    "⏱  Timing & Flow": [
        "wait", "pagedown", "pageup", "loop",
    ],
    "🔧  Utilities": [
        "screenshot", "condition", "comment",
    ],
}

# Reverse map: step_type → category
_STEP_TO_CAT = {}
for _cat, _types in STEP_CATEGORIES.items():
    for _t in _types:
        _STEP_TO_CAT[_t] = _cat


# ── Tooltip ───────────────────────────────────────────────────────────────────

class Tooltip:
    def __init__(self, widget, text: str):
        self._w   = widget
        self._txt = text
        self._tip = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, e=None):
        if not self._txt: return
        x = self._w.winfo_rootx() + 20
        y = self._w.winfo_rooty() + self._w.winfo_height() + 4
        self._tip = tk.Toplevel(self._w)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        tk.Label(self._tip, text=self._txt,
                 bg=T["bg4"], fg=T["fg"], font=T["font_s"],
                 padx=8, pady=4, relief="flat", wraplength=300).pack()

    def _hide(self, e=None):
        if self._tip:
            try: self._tip.destroy()
            except Exception: pass
            self._tip = None


# ── Variable dialogs ──────────────────────────────────────────────────────────

class VariableDialog(tk.Toplevel):
    """Define / edit {varname} placeholders used in steps."""
    def __init__(self, parent, variables: dict, on_save):
        super().__init__(parent)
        self.title("Variables  —  {varname} placeholders")
        self.configure(bg=T["bg"])
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self._vars    = dict(variables)
        self._on_save = on_save
        self._rows    = {}
        self._build()
        self.grab_set()

    def _build(self):
        tk.Label(self,
                 text=("Define  {varname}  placeholders.\n"
                       "Use them in any Type Text or Clip Type step.\n"
                       "Values are filled in just before each run."),
                 bg=T["bg"], fg=T["fg2"], font=T["font_s"], justify="left"
                 ).pack(padx=20, pady=(12, 8))

        self._frame = tk.Frame(self, bg=T["bg"])
        self._frame.pack(fill="x", padx=20)
        for k, v in self._vars.items():
            self._add_row(k, v)

        bf = tk.Frame(self, bg=T["bg2"], pady=10)
        bf.pack(fill="x", side="bottom")
        tk.Button(bf, text=" + Add Variable ", bg=T["bg3"], fg=T["cyan"],
                  font=T["font_b"], relief="flat", cursor="hand2",
                  command=self._add_empty).pack(side="left", padx=16)
        tk.Button(bf, text="  Save  ", bg=T["acc"], fg="white",
                  font=("Segoe UI Semibold", 9), relief="flat", cursor="hand2",
                  command=self._save).pack(side="left", padx=4)
        tk.Button(bf, text="Cancel", bg=T["bg3"], fg=T["fg2"],
                  font=T["font_b"], relief="flat", cursor="hand2",
                  command=self.destroy).pack(side="left")

    def _add_row(self, name: str = "", value: str = ""):
        r = tk.Frame(self._frame, bg=T["bg"])
        r.pack(fill="x", pady=3)
        nv = tk.StringVar(value=name)
        vv = tk.StringVar(value=value)
        tk.Label(r, text="{", bg=T["bg"], fg=T["fg3"], font=T["font_m"]).pack(side="left")
        tk.Entry(r, textvariable=nv, width=14, bg=T["bg3"], fg=T["cyan"],
                 insertbackground=T["fg"], font=T["font_m"], relief="flat"
                 ).pack(side="left")
        tk.Label(r, text="}", bg=T["bg"], fg=T["fg3"], font=T["font_m"]).pack(side="left")
        tk.Label(r, text="  default:", bg=T["bg"], fg=T["fg3"],
                 font=T["font_s"]).pack(side="left")
        tk.Entry(r, textvariable=vv, width=22, bg=T["bg3"], fg=T["fg"],
                 insertbackground=T["fg"], font=T["font_m"], relief="flat"
                 ).pack(side="left", padx=6)
        tk.Button(r, text="✕", bg=T["bg"], fg=T["fg3"],
                  font=T["font_s"], relief="flat", cursor="hand2",
                  command=lambda rr=r: self._del_row(rr)).pack(side="left")
        self._rows[r] = (nv, vv)

    def _add_empty(self):
        self._add_row()

    def _del_row(self, row):
        self._rows.pop(row, None)
        row.destroy()

    def _save(self):
        result = {}
        for r, (nv, vv) in self._rows.items():
            n = nv.get().strip()
            if n:
                result[n] = vv.get()
        self._on_save(result)
        self.destroy()


class VariableFillDialog(tk.Toplevel):
    """Ask user to fill in variable values at run time."""
    def __init__(self, parent, variables: dict):
        super().__init__(parent)
        self.title("Fill Variable Values")
        self.configure(bg=T["bg"])
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.result   = None
        self._entries = {}
        self._build(variables)
        self.grab_set()

    def _build(self, variables: dict):
        tk.Label(self, text="Enter values for your variables",
                 font=T["font_h"], bg=T["bg"], fg=T["fg"]
                 ).pack(padx=20, pady=(16, 4))
        for name, default in variables.items():
            r = tk.Frame(self, bg=T["bg"])
            r.pack(fill="x", padx=20, pady=4)
            tk.Label(r, text=f"{{{name}}}",
                     bg=T["bg"], fg=T["cyan"],
                     font=T["font_m"], width=14, anchor="e").pack(side="left")
            v = tk.StringVar(value=default)
            tk.Entry(r, textvariable=v, width=28,
                     bg=T["bg3"], fg=T["fg"],
                     insertbackground=T["fg"], font=T["font_m"], relief="flat"
                     ).pack(side="left", padx=8)
            self._entries[name] = v
        bf = tk.Frame(self, bg=T["bg2"], pady=10)
        bf.pack(fill="x", side="bottom")
        tk.Button(bf, text="  Run Now  ", bg=T["green"], fg=T["bg"],
                  font=("Segoe UI Semibold", 9), relief="flat", cursor="hand2",
                  command=self._ok).pack(side="left", padx=16)
        tk.Button(bf, text="Cancel", bg=T["bg3"], fg=T["fg2"],
                  font=T["font_b"], relief="flat", cursor="hand2",
                  command=self.destroy).pack(side="left")

    def _ok(self):
        self.result = {k: v.get() for k, v in self._entries.items()}
        self.destroy()


# ── Find & Replace ────────────────────────────────────────────────────────────

class FindReplaceDialog(tk.Toplevel):
    def __init__(self, parent, steps: list, on_replace):
        super().__init__(parent)
        self.title("Find & Replace in Steps")
        self.configure(bg=T["bg"])
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self._steps      = steps
        self._on_replace = on_replace
        self._build()
        self.grab_set()

    def _build(self):
        tk.Label(self, text="Find & Replace across all steps",
                 font=T["font_h"], bg=T["bg"], fg=T["fg"]
                 ).pack(padx=20, pady=(16, 4))
        tk.Label(self,
                 text="Searches: text, hotkey keys, key, folder, window_title, note.",
                 font=T["font_s"], bg=T["bg"], fg=T["fg2"]
                 ).pack(padx=20, pady=(0, 10))

        for label, attr in [("Find:", "_find"), ("Replace with:", "_repl")]:
            r = tk.Frame(self, bg=T["bg"]); r.pack(fill="x", padx=20, pady=4)
            tk.Label(r, text=label, bg=T["bg"], fg=T["fg2"],
                     font=T["font_b"], width=14, anchor="e").pack(side="left")
            v = tk.StringVar(); setattr(self, attr, v)
            tk.Entry(r, textvariable=v, width=30,
                     bg=T["bg3"], fg=T["fg"],
                     insertbackground=T["fg"], font=T["font_m"], relief="flat"
                     ).pack(side="left", padx=8)

        self._case = tk.BooleanVar(value=False)
        tk.Checkbutton(self, text="Case-sensitive", variable=self._case,
                       bg=T["bg"], fg=T["fg2"], selectcolor=T["bg3"],
                       font=T["font_s"], activebackground=T["bg"]
                       ).pack(padx=20, anchor="w")

        self._result_lbl = tk.Label(self, text="", bg=T["bg"],
                                    fg=T["green"], font=T["font_s"])
        self._result_lbl.pack(padx=20, pady=4)

        bf = tk.Frame(self, bg=T["bg2"], pady=10); bf.pack(fill="x", side="bottom")
        tk.Button(bf, text="  Replace All  ", bg=T["acc"], fg="white",
                  font=("Segoe UI Semibold", 9), relief="flat", cursor="hand2",
                  command=self._do_replace).pack(side="left", padx=16)
        tk.Button(bf, text="Close", bg=T["bg3"], fg=T["fg2"],
                  font=T["font_b"], relief="flat", cursor="hand2",
                  command=self.destroy).pack(side="left")

    def _do_replace(self):
        find = self._find.get()
        repl = self._repl.get()
        if not find:
            self._result_lbl.config(text="Enter something to find.", fg=T["yellow"])
            return
        count = self._replace_in(self._steps, find, repl, self._case.get())
        self._on_replace()
        self._result_lbl.config(text=f"✔  {count} replacement(s) made.", fg=T["green"])

    def _replace_in(self, steps: list, find: str, repl: str, case: bool) -> int:
        count = 0
        fields = ("text", "keys", "key", "folder", "window_title", "note")
        for step in steps:
            for f in fields:
                if f in step and isinstance(step[f], str):
                    orig = step[f]
                    if case:
                        step[f] = step[f].replace(find, repl)
                    else:
                        step[f] = re.sub(re.escape(find), repl, step[f],
                                         flags=re.IGNORECASE)
                    if step[f] != orig:
                        count += 1
            if step.get("type") == "loop" and step.get("steps"):
                count += self._replace_in(step["steps"], find, repl, case)
        return count


# ── Step picker (NEW cascading connected-dropdown UI) ─────────────────────────

class StepPickerDialog(tk.Toplevel):
    """
    Improved step picker with cascading connected dropdowns:
      1. Category selector (big pill buttons)
      2. Step selector within category (named cards with icon + desc)
      3. Inline quick-config panel slides in below

    Much clearer than the old 3-column flat grid.
    """

    def __init__(self, parent, on_pick):
        super().__init__(parent)
        self.title("Add a Step")
        self.configure(bg=T["bg"])
        self.resizable(True, True)
        self.attributes("-topmost", True)
        self.geometry("680x580")
        self.minsize(560, 440)
        self.on_pick = on_pick

        self._selected_cat  = tk.StringVar(value="")
        self._selected_type = tk.StringVar(value="")
        self._cat_buttons   = {}   # cat_name → Button
        self._step_buttons  = {}   # type_key → Frame (card)

        self._build()
        self.grab_set()

        # Auto-select first category
        first_cat = next(iter(STEP_CATEGORIES))
        self._select_category(first_cat)

    # ── Build skeleton ────────────────────────────────────────────────────────

    def _build(self):
        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=T["bg2"], pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Add a Step",
                 font=("Segoe UI Semibold", 13),
                 bg=T["bg2"], fg=T["fg"]).pack(side="left", padx=20)
        tk.Label(hdr, text="Choose a category, then select an action",
                 font=T["font_s"], bg=T["bg2"], fg=T["fg3"]).pack(side="left", padx=4)

        # Recently used strip
        recent = _prefs.get("recent_steps", [])
        if recent:
            rf = tk.Frame(self, bg=T["bg3"])
            rf.pack(fill="x")
            tk.Label(rf, text="  Recent:", bg=T["bg3"],
                     fg=T["fg3"], font=T["font_s"]).pack(side="left", padx=(8, 4), pady=6)
            for rt in recent[:6]:
                if rt not in STEP_FRIENDLY: continue
                ico  = STEP_FRIENDLY[rt][2]
                lbl  = STEP_FRIENDLY[rt][0]
                color = STEP_COLORS.get(rt, T["fg2"])
                b = tk.Button(rf, text=f"{ico} {lbl}",
                              bg=T["bg4"], fg=color, font=T["font_s"],
                              relief="flat", cursor="hand2", padx=8, pady=4,
                              command=lambda t=rt: self._pick(t))
                b.pack(side="left", padx=3, pady=5)
                Tooltip(b, "Recently used — click to add")

        # ── Category pill row ─────────────────────────────────────────────────
        cat_wrap = tk.Frame(self, bg=T["bg"])
        cat_wrap.pack(fill="x", padx=16, pady=(12, 0))
        tk.Label(cat_wrap, text="Category:", bg=T["bg"], fg=T["fg3"],
                 font=T["font_s"]).pack(side="left", padx=(0, 8))

        for cat_name in STEP_CATEGORIES:
            b = tk.Button(
                cat_wrap, text=cat_name,
                bg=T["bg3"], fg=T["fg2"],
                font=("Segoe UI Semibold", 9),
                relief="flat", cursor="hand2", padx=14, pady=7,
                command=lambda c=cat_name: self._select_category(c))
            b.pack(side="left", padx=3)
            self._cat_buttons[cat_name] = b

        # ── Step cards area (scrollable) ──────────────────────────────────────
        mid = tk.Frame(self, bg=T["bg"])
        mid.pack(fill="both", expand=True, padx=16, pady=8)

        # Left: step list
        left = tk.Frame(mid, bg=T["bg"])
        left.pack(side="left", fill="both", expand=True)

        self._steps_label = tk.Label(left, text="Steps", bg=T["bg"], fg=T["fg3"],
                                     font=T["font_s"], anchor="w")
        self._steps_label.pack(fill="x", pady=(0, 4))

        step_outer = tk.Frame(left, bg=T["bg"])
        step_outer.pack(fill="both", expand=True)
        self._step_canvas = tk.Canvas(step_outer, bg=T["bg"], highlightthickness=0)
        step_sb = ttk.Scrollbar(step_outer, orient="vertical",
                                command=self._step_canvas.yview)
        self._step_canvas.configure(yscrollcommand=step_sb.set)
        step_sb.pack(side="right", fill="y")
        self._step_canvas.pack(side="left", fill="both", expand=True)
        self._step_canvas.bind("<MouseWheel>",
            lambda e: self._step_canvas.yview_scroll(-1*(e.delta//120), "units"))
        self._step_frame = tk.Frame(self._step_canvas, bg=T["bg"])
        self._step_win = self._step_canvas.create_window(
            (0, 0), window=self._step_frame, anchor="nw")
        self._step_frame.bind("<Configure>",
            lambda e: self._step_canvas.configure(
                scrollregion=self._step_canvas.bbox("all")))
        self._step_canvas.bind("<Configure>",
            lambda e: self._step_canvas.itemconfig(self._step_win, width=e.width))

        # Right: detail / quick-config panel
        self._detail_frame = tk.Frame(mid, bg=T["bg2"], width=260)
        self._detail_frame.pack(side="right", fill="y", padx=(10, 0))
        self._detail_frame.pack_propagate(False)
        self._detail_placeholder()

        # ── Bottom bar ────────────────────────────────────────────────────────
        bot = tk.Frame(self, bg=T["bg2"], pady=10)
        bot.pack(fill="x", side="bottom")
        self._add_btn = tk.Button(
            bot, text="✚  Add Selected Step",
            bg=T["acc"], fg="white",
            font=("Segoe UI Semibold", 10), relief="flat", cursor="hand2",
            padx=18, pady=8, state="disabled",
            command=self._confirm_add)
        self._add_btn.pack(side="left", padx=16)
        tk.Button(bot, text="Cancel", bg=T["bg3"], fg=T["fg2"],
                  font=T["font_b"], relief="flat", cursor="hand2",
                  padx=10, pady=8, command=self.destroy).pack(side="left")
        self._bot_hint = tk.Label(bot, text="← Select a step type first",
                                  bg=T["bg2"], fg=T["fg3"], font=T["font_s"])
        self._bot_hint.pack(side="left", padx=12)

    # ── Category selection ────────────────────────────────────────────────────

    def _select_category(self, cat_name: str):
        self._selected_cat.set(cat_name)
        self._selected_type.set("")

        # Update pill highlights
        for name, btn in self._cat_buttons.items():
            if name == cat_name:
                btn.config(bg=T["acc"], fg="white")
            else:
                btn.config(bg=T["bg3"], fg=T["fg2"])

        self._steps_label.config(text=f"  {cat_name}")
        self._render_step_cards(STEP_CATEGORIES[cat_name])
        self._detail_placeholder()
        self._add_btn.config(state="disabled")
        self._bot_hint.config(text="← Select a step type")

    # ── Step cards ────────────────────────────────────────────────────────────

    def _render_step_cards(self, types: list):
        for w in self._step_frame.winfo_children():
            w.destroy()
        self._step_buttons.clear()

        for t in types:
            info = STEP_FRIENDLY.get(t, ("?", t, ""))
            lbl, desc, ico = info[0], info[1], info[2]
            color = STEP_COLORS.get(t, T["fg2"])

            card = tk.Frame(self._step_frame, bg=T["bg2"],
                            cursor="hand2", relief="flat")
            card.pack(fill="x", pady=3, padx=2)

            # Color accent bar
            tk.Frame(card, bg=color, width=5).pack(side="left", fill="y")

            inner = tk.Frame(card, bg=T["bg2"])
            inner.pack(side="left", fill="both", expand=True, padx=10, pady=8)

            row = tk.Frame(inner, bg=T["bg2"])
            row.pack(fill="x")
            tk.Label(row, text=ico, font=("Segoe UI", 14),
                     bg=T["bg2"], fg=color, width=2).pack(side="left")
            tk.Label(row, text=f"  {lbl}",
                     font=("Segoe UI Semibold", 9),
                     bg=T["bg2"], fg=T["fg"]).pack(side="left")

            tk.Label(inner, text=desc, font=T["font_s"],
                     bg=T["bg2"], fg=T["fg3"],
                     wraplength=200, justify="left").pack(anchor="w", pady=(2, 0))

            self._step_buttons[t] = card

            def _enter(e, c=card, i=inner):
                if self._selected_type.get() == e.widget._type: return
                c.configure(bg=T["bg3"]); i.configure(bg=T["bg3"])
                for ch in i.winfo_children():
                    ch.configure(bg=T["bg3"])
                    for cc in ch.winfo_children():
                        try: cc.configure(bg=T["bg3"])
                        except Exception: pass

            def _leave(e, c=card, i=inner):
                if self._selected_type.get() == e.widget._type: return
                c.configure(bg=T["bg2"]); i.configure(bg=T["bg2"])
                for ch in i.winfo_children():
                    ch.configure(bg=T["bg2"])
                    for cc in ch.winfo_children():
                        try: cc.configure(bg=T["bg2"])
                        except Exception: pass

            card._type  = t
            inner._type = t
            for ch in inner.winfo_children():
                ch._type = t
                for cc in ch.winfo_children():
                    try: cc._type = t
                    except Exception: pass

            for w in (card, inner):
                w.bind("<Enter>", _enter)
                w.bind("<Leave>", _leave)
                w.bind("<Button-1>", lambda e, tt=t: self._select_step(tt))

            # Propagate clicks to children
            for ch in inner.winfo_children():
                ch.bind("<Button-1>", lambda e, tt=t: self._select_step(tt))
                for cc in ch.winfo_children():
                    try:
                        cc.bind("<Button-1>", lambda e, tt=t: self._select_step(tt))
                    except Exception:
                        pass

            # Double-click to add directly
            for w in (card, inner):
                w.bind("<Double-Button-1>", lambda e, tt=t: self._pick(tt))

    # ── Step selection → detail panel ─────────────────────────────────────────

    def _select_step(self, t: str):
        prev = self._selected_type.get()
        self._selected_type.set(t)

        # De-highlight old
        if prev and prev in self._step_buttons:
            old = self._step_buttons[prev]
            old.configure(bg=T["bg2"])
            for ch in old.winfo_children():
                try: ch.configure(bg=T["bg2"])
                except Exception: pass
                for cc in ch.winfo_children():
                    try: cc.configure(bg=T["bg2"])
                    except Exception: pass
                    for ccc in cc.winfo_children():
                        try: ccc.configure(bg=T["bg2"])
                        except Exception: pass

        # Highlight new
        if t in self._step_buttons:
            card = self._step_buttons[t]
            hl = T["bg4"]
            card.configure(bg=hl)
            for ch in card.winfo_children():
                try: ch.configure(bg=hl)
                except Exception: pass
                for cc in ch.winfo_children():
                    try: cc.configure(bg=hl)
                    except Exception: pass
                    for ccc in cc.winfo_children():
                        try: ccc.configure(bg=hl)
                        except Exception: pass

        # Show detail panel
        self._render_detail(t)
        self._add_btn.config(state="normal")
        self._bot_hint.config(text="↑ Double-click a step card to add instantly")

    def _detail_placeholder(self):
        for w in self._detail_frame.winfo_children():
            w.destroy()
        tk.Label(self._detail_frame,
                 text="Select a step\nto see details",
                 bg=T["bg2"], fg=T["fg3"],
                 font=T["font_s"], justify="center"
                 ).pack(expand=True)

    def _render_detail(self, t: str):
        for w in self._detail_frame.winfo_children():
            w.destroy()

        info  = STEP_FRIENDLY.get(t, ("?", t, ""))
        lbl, desc, ico = info[0], info[1], info[2]
        color = STEP_COLORS.get(t, T["fg2"])

        # Header
        hdr = tk.Frame(self._detail_frame, bg=color)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"  {ico}  {lbl}",
                 bg=color, fg="white",
                 font=("Segoe UI Semibold", 10),
                 padx=10, pady=10).pack(anchor="w")

        body = tk.Frame(self._detail_frame, bg=T["bg2"])
        body.pack(fill="both", expand=True, padx=12, pady=10)

        # Description
        tk.Label(body, text=desc, bg=T["bg2"], fg=T["fg2"],
                 font=T["font_s"], wraplength=220, justify="left"
                 ).pack(anchor="w", pady=(0, 10))

        # What fields this step has
        defaults = STEP_DEFAULTS.get(t, {})
        field_info = self._field_descriptions(t, defaults)
        if field_info:
            tk.Label(body, text="Fields:", bg=T["bg2"], fg=T["fg3"],
                     font=T["font_s"]).pack(anchor="w")
            for fname, fhint in field_info:
                row = tk.Frame(body, bg=T["bg2"])
                row.pack(fill="x", pady=1)
                tk.Label(row, text="•", bg=T["bg2"], fg=color,
                         font=T["font_s"]).pack(side="left")
                tk.Label(row, text=f" {fname}", bg=T["bg2"], fg=T["fg"],
                         font=("Consolas", 8)).pack(side="left")
                if fhint:
                    tk.Label(row, text=f" — {fhint}", bg=T["bg2"],
                             fg=T["fg3"], font=T["font_s"],
                             wraplength=160).pack(side="left")

        # Tip / example
        tip = self._step_tip(t)
        if tip:
            tf = tk.Frame(body, bg=T["bg3"])
            tf.pack(fill="x", pady=(10, 0))
            tk.Label(tf, text="💡 Tip", bg=T["bg3"], fg=T["cyan"],
                     font=("Segoe UI Semibold", 8)).pack(anchor="w", padx=8, pady=(6, 0))
            tk.Label(tf, text=tip, bg=T["bg3"], fg=T["fg2"],
                     font=T["font_s"], wraplength=210, justify="left"
                     ).pack(anchor="w", padx=8, pady=(2, 8))

        # Add button (also at bottom of detail)
        tk.Button(body, text=f"✚  Add {lbl}",
                  bg=color, fg="white",
                  font=("Segoe UI Semibold", 9), relief="flat", cursor="hand2",
                  padx=10, pady=7,
                  command=lambda: self._pick(t)).pack(fill="x", pady=(14, 0))

    @staticmethod
    def _field_descriptions(t: str, defaults: dict) -> list:
        """Return [(field_name, hint_text)] for a step type."""
        if t in ("click", "double_click", "right_click", "mouse_move", "clear_field"):
            return [("x, y", "Screen coordinates — use Pick from screen in the editor")]
        if t == "scroll":
            return [("x, y", "Scroll position"), ("direction", "up or down"),
                    ("clicks", "Scroll amount")]
        if t == "hotkey":
            return [("keys", "e.g.  ctrl+s   alt+f4   enter")]
        if t in ("type_text", "clip_type"):
            return [("text", "Use {name} for current name, {var} for custom vars")]
        if t == "wait":
            return [("seconds", "How long to pause, e.g. 1.5")]
        if t in ("pagedown", "pageup"):
            return [("times", "How many pages to scroll")]
        if t == "key_repeat":
            return [("key", "tab  enter  space  escape…"), ("times", "Repetitions")]
        if t == "hold_key":
            return [("key", "Key to hold (space, shift, w…)"),
                    ("seconds", "Duration in seconds")]
        if t == "loop":
            return [("times", "Repeat count"), ("steps", "Sub-steps (added after saving)")]
        if t == "screenshot":
            return [("folder", "Destination folder path")]
        if t == "condition":
            return [("window_title", "Text that must appear in the window title"),
                    ("action", "skip or stop if it doesn't match")]
        if t == "comment":
            return [("text", "Annotation text — not executed")]
        return []

    @staticmethod
    def _step_tip(t: str) -> str:
        tips = {
            "click":        "Add a Wait step after clicking buttons that open dialogs.",
            "double_click": "Use Pick from screen for accurate coordinates.",
            "clip_type":    "Best for Nepali, emoji, or any Unicode text — uses clipboard.",
            "type_text":    "For ASCII-only text. Use Clip Type for Unicode/Nepali.",
            "clear_field":  "Combines click + Ctrl+A + Delete to reliably erase content.",
            "wait":         "Use after any action that loads a page or dialog.",
            "loop":         "After saving, click ✏ on the Loop card to add inner steps.",
            "condition":    "Skips or stops if the wrong window is in focus.",
            "hold_key":     "Useful for games or apps that require held keys.",
        }
        return tips.get(t, "")

    # ── Confirm and add ───────────────────────────────────────────────────────

    def _confirm_add(self):
        t = self._selected_type.get()
        if t:
            self._pick(t)

    def _pick(self, t: str):
        recent = _prefs.get("recent_steps", [])
        if t in recent: recent.remove(t)
        recent.insert(0, t)
        _prefs["recent_steps"] = recent[:6]
        save_prefs()
        self.on_pick(t)
        self.destroy()


# ── Step editor ───────────────────────────────────────────────────────────────

class StepEditor(tk.Toplevel):
    def __init__(self, parent, step: dict = None, on_save=None):
        super().__init__(parent)
        t = step["type"] if step else "click"
        ico, lbl, desc = STEP_FRIENDLY.get(t, ("•", t, ""))[:3]
        self.title(f"Edit: {lbl}")
        self.configure(bg=T["bg"])
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.on_save     = on_save
        self._step       = copy.deepcopy(step) if step else None
        self._fields     = {}
        self._loop_steps = copy.deepcopy(step.get("steps", [])) if step else []
        self._pos_job    = None

        color = STEP_COLORS.get(t, T["acc"])
        hdr   = tk.Frame(self, bg=T["bg2"], pady=12); hdr.pack(fill="x")
        tk.Label(hdr, text=f"  {ico}", font=("Segoe UI", 16),
                 bg=T["bg2"], fg=color).pack(side="left")
        lf = tk.Frame(hdr, bg=T["bg2"]); lf.pack(side="left", padx=8)
        tk.Label(lf, text=lbl, font=("Segoe UI Semibold", 11),
                 bg=T["bg2"], fg=T["fg"]).pack(anchor="w")
        tk.Label(lf, text=desc, font=T["font_s"],
                 bg=T["bg2"], fg=T["fg2"]).pack(anchor="w")

        self._ff = tk.Frame(self, bg=T["bg"])
        self._ff.pack(fill="both", padx=20, pady=12)
        self._build_fields(t, step or {"type": t, **STEP_DEFAULTS[t]})

        # Note
        nf = tk.Frame(self, bg=T["bg"]); nf.pack(fill="x", padx=20, pady=(0, 6))
        tk.Label(nf, text="Label / Note:", bg=T["bg"], fg=T["fg3"],
                 font=T["font_s"]).pack(side="left")
        self._note_var = tk.StringVar(value=step.get("note", "") if step else "")
        tk.Entry(nf, textvariable=self._note_var, width=28,
                 bg=T["bg3"], fg=T["fg2"], insertbackground=T["fg"],
                 font=T["font_m"], relief="flat").pack(side="left", padx=8)

        # Enabled toggle
        ef = tk.Frame(self, bg=T["bg"]); ef.pack(fill="x", padx=20, pady=(0, 6))
        self._enabled_var = tk.BooleanVar(value=step.get("enabled", True) if step else True)
        tk.Checkbutton(ef, text="Step is enabled (uncheck to skip without deleting)",
                       variable=self._enabled_var, bg=T["bg"], fg=T["fg2"],
                       selectcolor=T["bg3"], font=T["font_s"],
                       activebackground=T["bg"]).pack(side="left")

        bf = tk.Frame(self, bg=T["bg2"], pady=10); bf.pack(fill="x", side="bottom")
        tk.Button(bf, text="  Save  ", bg=T["acc"], fg="white",
                  font=("Segoe UI Semibold", 9), relief="flat", cursor="hand2",
                  command=self._save).pack(side="left", padx=16)
        tk.Button(bf, text="Cancel", bg=T["bg3"], fg=T["fg2"],
                  font=T["font_b"], relief="flat", cursor="hand2",
                  command=self._cancel).pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.grab_set(); self.lift()

    def _cancel(self):
        if self._pos_job:
            try: self.after_cancel(self._pos_job)
            except Exception: pass
        self.destroy()

    def _row(self, label: str, widget_fn, hint: str = None):
        r = tk.Frame(self._ff, bg=T["bg"]); r.pack(fill="x", pady=5)
        tk.Label(r, text=label, bg=T["bg"], fg=T["fg2"],
                 font=T["font_b"], width=18, anchor="e").pack(side="left")
        w = widget_fn(r); w.pack(side="left", padx=8)
        if hint:
            tk.Label(r, text=hint, bg=T["bg"], fg=T["fg3"],
                     font=T["font_s"]).pack(side="left")
        return w

    def _entry(self, parent, var, width: int = 14):
        return tk.Entry(parent, textvariable=var, width=width,
                        bg=T["bg3"], fg=T["fg"],
                        insertbackground=T["fg"], font=T["font_m"], relief="flat")

    def _build_fields(self, t: str, d: dict):
        def sv(key): return tk.StringVar(value=str(d.get(key, "")))

        if t in ("click", "double_click", "right_click", "mouse_move", "clear_field"):
            self._fields["x"] = sv("x"); self._fields["y"] = sv("y")
            self._row("X position:", lambda p: self._entry(p, self._fields["x"], 8))
            self._row("Y position:", lambda p: self._entry(p, self._fields["y"], 8))
            pf = tk.Frame(self._ff, bg=T["bg"]); pf.pack(fill="x", pady=6)
            tk.Label(pf, text="", width=18, bg=T["bg"]).pack(side="left")
            tk.Button(pf, text="📍  Pick from screen  (3s)",
                      bg=T["purple"], fg="white", font=T["font_b"],
                      relief="flat", cursor="hand2",
                      command=self._pick).pack(side="left", padx=8)
            self._pos_lbl = tk.Label(pf, text="", bg=T["bg"],
                                     fg=T["cyan"], font=T["font_m"])
            self._pos_lbl.pack(side="left", padx=8)
            self._start_pos_poll()

        elif t == "hotkey":
            self._fields["keys"] = sv("keys")
            self._row("Keys:", lambda p: self._entry(p, self._fields["keys"], 22),
                      "e.g.  ctrl+s   alt+f4   enter   ctrl+shift+p")

        elif t in ("type_text", "clip_type"):
            self._fields["text"] = sv("text")
            r = tk.Frame(self._ff, bg=T["bg"]); r.pack(fill="x", pady=5)
            tk.Label(r, text="Text to type:", bg=T["bg"], fg=T["fg2"],
                     font=T["font_b"], width=18, anchor="e").pack(side="left")
            txt = tk.Text(r, width=28, height=3, bg=T["bg3"], fg=T["fg"],
                          insertbackground=T["fg"], font=T["font_m"], relief="flat")
            txt.insert("1.0", str(d.get("text", "")))
            txt.pack(side="left", padx=8)
            def _sync(*a): self._fields["text"].set(txt.get("1.0", "end-1c"))
            txt.bind("<KeyRelease>", _sync)
            self._txt_widget = txt
            hint = ("Use  {name}  for the current name, or  {varname}  for a variable."
                    if t == "clip_type" else
                    "Tip: use Clip Type for Nepali, emoji, or any Unicode text.")
            tk.Label(self._ff, text=hint, bg=T["bg"], fg=T["fg3"],
                     font=T["font_s"], wraplength=340, justify="left"
                     ).pack(anchor="w", pady=(0, 4))

        elif t == "wait":
            self._fields["seconds"] = sv("seconds")
            self._row("Wait (seconds):", lambda p: self._entry(p, self._fields["seconds"], 8),
                      "e.g.  1  or  2.5")

        elif t in ("pagedown", "pageup"):
            self._fields["times"] = sv("times")
            self._row("How many times:", lambda p: self._entry(p, self._fields["times"], 6))

        elif t == "scroll":
            self._fields["x"]         = sv("x")
            self._fields["y"]         = sv("y")
            self._fields["clicks"]    = sv("clicks")
            self._fields["direction"] = sv("direction")
            self._row("X position:", lambda p: self._entry(p, self._fields["x"], 8))
            self._row("Y position:", lambda p: self._entry(p, self._fields["y"], 8))
            r = tk.Frame(self._ff, bg=T["bg"]); r.pack(fill="x", pady=5)
            tk.Label(r, text="Direction:", bg=T["bg"], fg=T["fg2"],
                     font=T["font_b"], width=18, anchor="e").pack(side="left")
            ttk.Combobox(r, textvariable=self._fields["direction"],
                         values=["down", "up"], state="readonly", width=8
                         ).pack(side="left", padx=8)
            self._row("Scroll amount:", lambda p: self._entry(p, self._fields["clicks"], 6),
                      "clicks")

        elif t == "key_repeat":
            self._fields["key"]   = sv("key")
            self._fields["times"] = sv("times")
            self._row("Key to press:", lambda p: self._entry(p, self._fields["key"], 12),
                      "tab  enter  space  escape  up  down  delete")
            self._row("How many times:", lambda p: self._entry(p, self._fields["times"], 6))

        elif t == "hold_key":
            self._fields["key"]     = sv("key")
            self._fields["seconds"] = sv("seconds")
            self._row("Key to hold:", lambda p: self._entry(p, self._fields["key"], 12),
                      "space  shift  ctrl  alt  w  a  s  d  …")
            self._row("Hold duration (s):", lambda p: self._entry(p, self._fields["seconds"], 8),
                      "e.g.  0.5  or  2.0")
            tk.Label(self._ff,
                     text="💡 Hold the key pressed for N seconds. Great for Shift, Space, game keys.",
                     bg=T["bg"], fg=T["fg3"], font=T["font_s"]
                     ).pack(anchor="w", pady=4)

        elif t == "loop":
            self._fields["times"] = sv("times")
            self._row("Repeat N times:", lambda p: self._entry(p, self._fields["times"], 6))
            tk.Label(self._ff,
                     text="After saving, click ✏ on this Loop card to add steps inside it.",
                     bg=T["bg"], fg=T["fg3"], font=T["font_s"]
                     ).pack(anchor="w", pady=4)

        elif t == "screenshot":
            self._fields["folder"] = sv("folder")
            self._row("Save folder:", lambda p: self._entry(p, self._fields["folder"], 22))

        elif t == "condition":
            self._fields["window_title"] = sv("window_title")
            self._fields["action"]       = sv("action")
            self._row("Window title contains:",
                      lambda p: self._entry(p, self._fields["window_title"], 22))
            r = tk.Frame(self._ff, bg=T["bg"]); r.pack(fill="x", pady=5)
            tk.Label(r, text="If it doesn't match:", bg=T["bg"], fg=T["fg2"],
                     font=T["font_b"], width=18, anchor="e").pack(side="left")
            ttk.Combobox(r, textvariable=self._fields["action"],
                         values=["skip", "stop"], state="readonly", width=8
                         ).pack(side="left", padx=8)
            tk.Label(r, text="skip = next name   stop = abort run",
                     bg=T["bg"], fg=T["fg3"], font=T["font_s"]).pack(side="left")

        elif t == "comment":
            self._fields["text"] = sv("text")
            r = tk.Frame(self._ff, bg=T["bg"]); r.pack(fill="x", pady=5)
            tk.Label(r, text="Comment:", bg=T["bg"], fg=T["fg2"],
                     font=T["font_b"], width=18, anchor="e").pack(side="left")
            txt = tk.Text(r, width=28, height=2, bg=T["bg3"], fg=T["fg"],
                          insertbackground=T["fg"], font=T["font_m"], relief="flat")
            txt.insert("1.0", str(d.get("text", "")))
            txt.pack(side="left", padx=8)
            def _sync2(*a): self._fields["text"].set(txt.get("1.0", "end-1c"))
            txt.bind("<KeyRelease>", _sync2)
            self._txt_widget = txt

    def _start_pos_poll(self):
        def _poll():
            if not self.winfo_exists():
                return
            try:
                x, y = pyautogui.position()
                if hasattr(self, "_pos_lbl") and self._pos_lbl.winfo_exists():
                    self._pos_lbl.config(text=f"Mouse: {x}, {y}")
            except Exception:
                pass
            self._pos_job = self.after(80, _poll)
        _poll()

    def _pick(self):
        self.withdraw()
        def _grab():
            for _ in range(3): time.sleep(1)
            x, y = pyautogui.position()
            self._fields["x"].set(str(x))
            self._fields["y"].set(str(y))
            self.after(0, self.deiconify)
        threading.Thread(target=_grab, daemon=True).start()

    def _save(self):
        if self._pos_job:
            try: self.after_cancel(self._pos_job)
            except Exception: pass
        t    = self._step["type"] if self._step else "click"
        step = {"type": t,
                "note": self._note_var.get().strip(),
                "enabled": self._enabled_var.get()}
        try:
            for k, v in self._fields.items():
                raw = v.get().strip()
                if k in ("x", "y", "times", "clicks"):
                    step[k] = int(float(raw or 0))
                elif k == "seconds":
                    step[k] = float(raw or 0)
                else:
                    step[k] = raw
            if t == "loop":
                step["steps"] = copy.deepcopy(self._loop_steps)
        except ValueError as e:
            messagebox.showerror("Invalid value", str(e), parent=self)
            return
        if self.on_save:
            self.on_save(step)
        self.destroy()


# ── Help panel ────────────────────────────────────────────────────────────────

HELP_TEXT = """
╔══════════════════════════════════════════════════════════════╗
║          SWASTIK RPA v9.3  —  Quick Reference Guide          ║
╚══════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GETTING STARTED IN 3 STEPS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. NAME LIST TAB   → Add names / values (one per line or load Excel/CSV).
  2. BUILD FLOW TAB  → Add steps that describe what to automate.
  3. RUN TAB         → Click ▶ Start Automation.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 STEP PICKER  (v9.3 IMPROVED)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Category pills → click to filter the step list by type.
  Step cards     → click to see details + tip in the right panel.
  Double-click   → add the step instantly.
  Recent strip   → your last 6 used steps appear at the top.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 MACRO RECORDER  (v9.3 IMPROVED)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  A floating mini-overlay appears when you open the recorder.
  It stays on top and records everything EXCEPT its own window.
  Record, Pause, Stop buttons are in the overlay.
  Configure overlay shortcuts in ⚙ Settings → Macro Recorder.
  Shortcuts configured there will NOT be recorded as steps.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 KEYBOARD SHORTCUTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Ctrl+S   Save flow       Ctrl+O   Load flow
  Ctrl+Z   Undo            Ctrl+Y   Redo
  Ctrl+D   Duplicate last step
  F10      Emergency stop  F11      Pause / Resume

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 VARIABLES  {varname}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  • Use the Variables button to define {url}, {password}, etc.
  • Put {url} in any Type Text / Clip Type step.
  • {name} is always replaced automatically from the Name List.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 TIPS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ✔  Always add Wait steps after clicks that open windows.
  ✔  Use Clear a Field before typing to avoid appending to old text.
  ✔  Use Clip Type for Nepali names and Unicode.
  ✔  Enable Practice mode to test without real clicks.
  ✔  Move mouse to screen corner for emergency stop (fail-safe).
  ✔  Click 👁 on a card to disable a step without deleting it.
"""


class HelpPanel(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=T["bg"], **kw)
        tb = tk.Text(self, bg=T["bg2"], fg=T["fg2"],
                     font=("Consolas", 9), relief="flat",
                     padx=20, pady=16, wrap="word",
                     state="normal", spacing1=1, spacing3=1)
        sb = ttk.Scrollbar(self, orient="vertical", command=tb.yview)
        tb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        tb.pack(fill="both", expand=True)
        tb.insert("end", HELP_TEXT)
        tb.config(state="disabled")


# ── Column chooser ────────────────────────────────────────────────────────────

class ColumnChooser(tk.Toplevel):
    def __init__(self, parent, cols: list):
        super().__init__(parent)
        self.title("Choose Column")
        self.configure(bg=T["bg"])
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.chosen = None
        tk.Label(self, text="Which column has the names?",
                 bg=T["bg"], fg=T["fg"], font=T["font_h"]
                 ).pack(padx=20, pady=(16, 8))
        for col in cols:
            tk.Button(self, text=col,
                      bg=T["bg3"], fg=T["fg"],
                      font=T["font_b"], relief="flat", cursor="hand2",
                      padx=20, pady=6,
                      command=lambda c=col: self._pick(c)
                      ).pack(fill="x", padx=20, pady=3)
        tk.Button(self, text="Cancel", bg=T["bg"], fg=T["fg3"],
                  font=T["font_s"], relief="flat",
                  command=self.destroy).pack(pady=8)
        self.grab_set()

    def _pick(self, col: str):
        self.chosen = col
        self.destroy()
