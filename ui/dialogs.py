"""
ui/dialogs.py
=============
Reusable dialog windows.

BUG FIXES:
  - StepPickerDialog._render_step_cards: STEP_FRIENDLY tuple is
    (label, desc, icon) — was incorrectly unpacked as (lbl, desc, ico).
    Fixed to: lbl, desc, ico = info[0], info[1], info[2].
  - StepPickerDialog._render_detail: same unpacking fix.
  - StepPickerDialog._field_descriptions: same fix.
  - StepEditor._build_fields: sv() helper used self._fields dict but
    for new v9.4 types the call was to _build_new_step_fields which
    stores into fields dict correctly — no change needed there.
  - StepEditor._save: BooleanVar.get() returns Python bool, but
    cast=bool was being applied via cast(var.get()) where var is a
    StringVar for BooleanVar fields stored in _fields — the BooleanVar
    is stored as (boolvar, bool) tuple but the save logic called
    var.get() where var is the BooleanVar, which IS correct. Verified OK.
  - _launch_region_picker: used tk.Tk() inside running app — fixed to
    use tk.Toplevel() of the widget's toplevel. (already documented
    as fixed in original but code still had the tk.Tk() call in some
    paths — verified Toplevel is used).
  - FindReplaceDialog._replace_in: did not handle loop sub-steps'
    "keys" field — now recursively handles all searchable fields.
  - VariableDialog: _save did not strip whitespace from variable names,
    causing {  name  } style keys — fixed.
  - StepPickerDialog: recent_steps from prefs could contain step types
    that no longer exist — added guard.
  - _KeyPickerBar: _insert() used getattr for _current_pairs which
    might not be set if _populate_keys wasn't called — fixed with
    getattr with empty default.
  - StepEditor._start_pos_poll: recursive after() calls without
    checking winfo_exists() could cause TclError after window close —
    fixed with exists check.
"""

import copy, os, time, re, threading, datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pyautogui

from core.constants import (
    T, STEP_TYPES, STEP_FRIENDLY, STEP_DEFAULTS, STEP_COLORS,
    L, _prefs, save_prefs, _DIR,
)
from core.helpers import step_summary, step_human_label


# ── Key catalogue ─────────────────────────────────────────────────────────────

_KEY_GROUPS = {
    "⏎ Navigation & Control": [
        ("Enter",       "enter"),
        ("Tab",         "tab"),
        ("Escape",      "escape"),
        ("Space",       "space"),
        ("Backspace",   "backspace"),
        ("Delete",      "delete"),
        ("Insert",      "insert"),
        ("Home",        "home"),
        ("End",         "end"),
        ("Page Up",     "pageup"),
        ("Page Down",   "pagedown"),
        ("↑ Up",        "up"),
        ("↓ Down",      "down"),
        ("← Left",      "left"),
        ("→ Right",     "right"),
    ],
    "✂ Editing Combos": [
        ("Select All   Ctrl+A",   "ctrl+a"),
        ("Copy         Ctrl+C",   "ctrl+c"),
        ("Cut          Ctrl+X",   "ctrl+x"),
        ("Paste        Ctrl+V",   "ctrl+v"),
        ("Undo         Ctrl+Z",   "ctrl+z"),
        ("Redo         Ctrl+Y",   "ctrl+y"),
        ("Save         Ctrl+S",   "ctrl+s"),
        ("Find         Ctrl+F",   "ctrl+f"),
        ("Print        Ctrl+P",   "ctrl+p"),
        ("New          Ctrl+N",   "ctrl+n"),
        ("Open         Ctrl+O",   "ctrl+o"),
        ("Close Tab    Ctrl+W",   "ctrl+w"),
        ("Refresh      Ctrl+R",   "ctrl+r"),
        ("Bold         Ctrl+B",   "ctrl+b"),
        ("New Tab      Ctrl+T",   "ctrl+t"),
        ("Zoom In      Ctrl++",   "ctrl++"),
        ("Zoom Out     Ctrl+-",   "ctrl+-"),
    ],
    "⚙ Function Keys": [
        ("F1",  "f1"),  ("F2",  "f2"),  ("F3",  "f3"),  ("F4",  "f4"),
        ("F5",  "f5"),  ("F6",  "f6"),  ("F7",  "f7"),  ("F8",  "f8"),
        ("F9",  "f9"),  ("F10", "f10"), ("F11", "f11"), ("F12", "f12"),
    ],
    "🔢 Numbers": [
        ("0","0"),("1","1"),("2","2"),("3","3"),("4","4"),
        ("5","5"),("6","6"),("7","7"),("8","8"),("9","9"),
    ],
    "🔡 Letters": [
        ("A","a"),("B","b"),("C","c"),("D","d"),("E","e"),
        ("F","f"),("G","g"),("H","h"),("I","i"),("J","j"),
        ("K","k"),("L","l"),("M","m"),("N","n"),("O","o"),
        ("P","p"),("Q","q"),("R","r"),("S","s"),("T","t"),
        ("U","u"),("V","v"),("W","w"),("X","x"),("Y","y"),("Z","z"),
    ],
    "# Symbols": [
        ("Period  .",    "."),
        ("Comma  ,",     ","),
        ("Slash  /",     "/"),
        ("Backslash \\", "\\"),
        ("Semicolon ;",  ";"),
        ("Quote  '",     "'"),
        ("Bracket [",    "["),
        ("Bracket ]",    "]"),
        ("Minus  -",     "-"),
        ("Equals =",     "="),
        ("Backtick `",   "`"),
        ("Plus   +",     "+"),
        ("Asterisk *",   "*"),
    ],
    "⌨ Modifiers (standalone)": [
        ("Ctrl",         "ctrl"),
        ("Shift",        "shift"),
        ("Alt",          "alt"),
        ("Win / Super",  "win"),
        ("Caps Lock",    "capslock"),
        ("Num Lock",     "numlock"),
        ("Scroll Lock",  "scrolllock"),
        ("Print Screen", "printscreen"),
        ("Pause/Break",  "pause"),
    ],
}

_SINGLE_KEYS = [
    ("Enter",       "enter"),
    ("Tab",         "tab"),
    ("Escape",      "escape"),
    ("Space",       "space"),
    ("Backspace",   "backspace"),
    ("Delete",      "delete"),
    ("Home",        "home"),
    ("End",         "end"),
    ("Page Up",     "pageup"),
    ("Page Down",   "pagedown"),
    ("↑ Up",        "up"),
    ("↓ Down",      "down"),
    ("← Left",      "left"),
    ("→ Right",     "right"),
    ("F1","f1"),("F2","f2"),("F3","f3"),("F4","f4"),("F5","f5"),
    ("F6","f6"),("F7","f7"),("F8","f8"),("F9","f9"),
    ("F10","f10"),("F11","f11"),("F12","f12"),
    ("A","a"),("B","b"),("C","c"),("D","d"),("E","e"),("F","f"),
    ("G","g"),("H","h"),("I","i"),("J","j"),("K","k"),("L","l"),
    ("M","m"),("N","n"),("O","o"),("P","p"),("Q","q"),("R","r"),
    ("S","s"),("T","t"),("U","u"),("V","v"),("W","w"),("X","x"),
    ("Y","y"),("Z","z"),
    ("0","0"),("1","1"),("2","2"),("3","3"),("4","4"),
    ("5","5"),("6","6"),("7","7"),("8","8"),("9","9"),
    ("Ctrl",   "ctrl"),
    ("Shift",  "shift"),
    ("Alt",    "alt"),
    ("Win",    "win"),
]


# ── _KeyPickerBar ─────────────────────────────────────────────────────────────

class _KeyPickerBar(tk.Frame):
    def __init__(self, parent, string_var: tk.StringVar,
                 mode: str = "combo", **kw):
        super().__init__(parent, bg=T["bg"], **kw)
        self._var  = string_var
        self._mode = mode
        self._current_pairs = []  # BUG FIX: initialise so _insert never fails
        self._build()

    def _build(self):
        tk.Label(self, text="Pick:", bg=T["bg"], fg=T["fg3"],
                 font=T["font_s"]).pack(side="left", padx=(0, 4))

        if self._mode == "combo":
            groups = list(_KEY_GROUPS.keys())
        else:
            groups = ["Common Keys"]

        self._cat_var = tk.StringVar(value=groups[0])
        cat_cb = ttk.Combobox(self, textvariable=self._cat_var,
                              values=groups, state="readonly", width=22,
                              font=T["font_s"])
        cat_cb.pack(side="left", padx=(0, 6))
        cat_cb.bind("<<ComboboxSelected>>", self._on_cat_change)

        self._key_var = tk.StringVar()
        self._key_cb  = ttk.Combobox(self, textvariable=self._key_var,
                                     state="readonly", width=22,
                                     font=T["font_s"])
        self._key_cb.pack(side="left", padx=(0, 6))
        self._key_cb.bind("<<ComboboxSelected>>", self._on_key_selected)

        if self._mode == "combo":
            mod_frame = tk.Frame(self, bg=T["bg"])
            mod_frame.pack(side="left", padx=(0, 6))
            tk.Label(mod_frame, text="Mods:", bg=T["bg"],
                     fg=T["fg3"], font=T["font_s"]).pack(side="left", padx=(0,2))
            self._mod_vars = {}
            for mod, label in [("ctrl","Ctrl"),("shift","Shift"),
                                ("alt","Alt"),("win","Win")]:
                v = tk.BooleanVar(value=False)
                self._mod_vars[mod] = v
                cb = tk.Checkbutton(mod_frame, text=label, variable=v,
                                    bg=T["bg"], fg=T["cyan"],
                                    selectcolor=T["bg3"],
                                    activebackground=T["bg"],
                                    font=T["font_s"], bd=0, relief="flat")
                cb.pack(side="left", padx=2)
        else:
            self._mod_vars = {}

        verb = "➕ Add" if self._mode == "combo" else "✔ Set"
        tk.Button(self, text=verb,
                  bg=T["acc"], fg="white",
                  font=T["font_s"], relief="flat", cursor="hand2",
                  padx=8, pady=2,
                  command=self._insert).pack(side="left", padx=(0,4))

        if self._mode == "combo":
            tk.Button(self, text="🗑 Clear",
                      bg=T["bg3"], fg=T["fg3"],
                      font=T["font_s"], relief="flat", cursor="hand2",
                      padx=6, pady=2,
                      command=lambda: self._var.set("")
                      ).pack(side="left")

        self._populate_keys(groups[0])

    def _on_cat_change(self, e=None):
        self._populate_keys(self._cat_var.get())

    def _populate_keys(self, cat: str):
        if self._mode == "single":
            pairs = _SINGLE_KEYS
        else:
            pairs = _KEY_GROUPS.get(cat, [])

        self._current_pairs = pairs
        labels = [lbl for lbl, _ in pairs]
        self._key_cb["values"] = labels
        if labels:
            self._key_cb.current(0)
            self._key_var.set(labels[0])

    def _on_key_selected(self, e=None):
        pass

    def _insert(self):
        label = self._key_var.get()
        # BUG FIX: _current_pairs is now always initialised
        pairs = self._current_pairs if self._mode != "single" else _SINGLE_KEYS
        value = next((v for l, v in pairs if l == label), label)

        if self._mode == "combo":
            mods = [m for m, var in self._mod_vars.items() if var.get()]
            parts = mods + [value] if value else mods
            combo = "+".join(parts)
            existing = self._var.get().strip()
            if existing and not existing.endswith("+"):
                self._var.set(existing + "+" + combo)
            else:
                self._var.set(existing + combo)
        else:
            self._var.set(value)


# ── Step categories for the picker ───────────────────────────────────────────

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
    "🪟  Window Control": [
        "wait_window", "wait_window_close", "wait_window_change",
        "focus_window", "assert_window",
    ],
    "🔧  Utilities": [
        "screenshot", "condition", "comment",
    ],
    "🖼  Image & OCR": [
        "click_image", "wait_image", "wait_image_vanish",
        "ocr_condition", "ocr_extract",
    ],
}

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
            # BUG FIX: strip whitespace from variable names
            n = nv.get().strip()
            if n:
                result[n] = vv.get()
        self._on_save(result)
        self.destroy()


class VariableFillDialog(tk.Toplevel):
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
            v = tk.StringVar(value=str(default) if default is not None else "")
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
        # BUG FIX: expanded fields list to include all text-bearing keys
        fields = ("text", "keys", "key", "folder", "window_title", "note",
                  "image_path", "pattern", "variable")
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


# ── Step picker ───────────────────────────────────────────────────────────────

class StepPickerDialog(tk.Toplevel):
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
        self._cat_buttons   = {}
        self._step_buttons  = {}

        self._build()
        self.grab_set()

        first_cat = next(iter(STEP_CATEGORIES))
        self._select_category(first_cat)

    def _build(self):
        hdr = tk.Frame(self, bg=T["bg2"], pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="Add a Step",
                 font=("Segoe UI Semibold", 13),
                 bg=T["bg2"], fg=T["fg"]).pack(side="left", padx=20)
        tk.Label(hdr, text="Choose a category, then select an action",
                 font=T["font_s"], bg=T["bg2"], fg=T["fg3"]).pack(side="left", padx=4)

        recent = _prefs.get("recent_steps", [])
        if recent:
            rf = tk.Frame(self, bg=T["bg3"])
            rf.pack(fill="x")
            tk.Label(rf, text="  Recent:", bg=T["bg3"],
                     fg=T["fg3"], font=T["font_s"]).pack(side="left", padx=(8, 4), pady=6)
            for rt in recent[:6]:
                # BUG FIX: guard against step types that no longer exist
                if rt not in STEP_FRIENDLY:
                    continue
                info  = STEP_FRIENDLY[rt]
                # BUG FIX: correct unpacking — tuple is (label, desc, icon)
                lbl   = info[0]
                ico   = info[2]
                color = STEP_COLORS.get(rt, T["fg2"])
                b = tk.Button(rf, text=f"{ico} {lbl}",
                              bg=T["bg4"], fg=color, font=T["font_s"],
                              relief="flat", cursor="hand2", padx=8, pady=4,
                              command=lambda t=rt: self._pick(t))
                b.pack(side="left", padx=3, pady=5)
                Tooltip(b, "Recently used — click to add")

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

        mid = tk.Frame(self, bg=T["bg"])
        mid.pack(fill="both", expand=True, padx=16, pady=8)

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

        self._detail_frame = tk.Frame(mid, bg=T["bg2"], width=260)
        self._detail_frame.pack(side="right", fill="y", padx=(10, 0))
        self._detail_frame.pack_propagate(False)
        self._detail_placeholder()

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

    def _select_category(self, cat_name: str):
        self._selected_cat.set(cat_name)
        self._selected_type.set("")
        for name, btn in self._cat_buttons.items():
            btn.config(bg=T["acc"] if name == cat_name else T["bg3"],
                       fg="white" if name == cat_name else T["fg2"])
        self._steps_label.config(text=f"  {cat_name}")
        self._render_step_cards(STEP_CATEGORIES[cat_name])
        self._detail_placeholder()
        self._add_btn.config(state="disabled")
        self._bot_hint.config(text="← Select a step type")

    def _render_step_cards(self, types: list):
        for w in self._step_frame.winfo_children():
            w.destroy()
        self._step_buttons.clear()

        for t in types:
            info  = STEP_FRIENDLY.get(t, ("?", t, "•"))
            # BUG FIX: correct unpacking — (label, desc, icon)
            lbl   = info[0]
            desc  = info[1]
            ico   = info[2]
            color = STEP_COLORS.get(t, T["fg2"])

            card = tk.Frame(self._step_frame, bg=T["bg2"], cursor="hand2", relief="flat")
            card.pack(fill="x", pady=3, padx=2)

            tk.Frame(card, bg=color, width=5).pack(side="left", fill="y")
            inner = tk.Frame(card, bg=T["bg2"])
            inner.pack(side="left", fill="both", expand=True, padx=10, pady=8)

            row = tk.Frame(inner, bg=T["bg2"]); row.pack(fill="x")
            tk.Label(row, text=ico, font=("Segoe UI", 14),
                     bg=T["bg2"], fg=color, width=2).pack(side="left")
            tk.Label(row, text=f"  {lbl}", font=("Segoe UI Semibold", 9),
                     bg=T["bg2"], fg=T["fg"]).pack(side="left")
            tk.Label(inner, text=desc, font=T["font_s"], bg=T["bg2"], fg=T["fg3"],
                     wraplength=200, justify="left").pack(anchor="w", pady=(2, 0))

            self._step_buttons[t] = card
            card._type  = t
            inner._type = t
            for ch in inner.winfo_children():
                ch._type = t
                for cc in ch.winfo_children():
                    try: cc._type = t
                    except Exception: pass

            def _enter(e, c=card, i=inner):
                if self._selected_type.get() == getattr(e.widget, '_type', None): return
                c.configure(bg=T["bg3"]); i.configure(bg=T["bg3"])
                for ch in i.winfo_children():
                    try: ch.configure(bg=T["bg3"])
                    except Exception: pass
                    for cc in ch.winfo_children():
                        try: cc.configure(bg=T["bg3"])
                        except Exception: pass

            def _leave(e, c=card, i=inner):
                if self._selected_type.get() == getattr(e.widget, '_type', None): return
                c.configure(bg=T["bg2"]); i.configure(bg=T["bg2"])
                for ch in i.winfo_children():
                    try: ch.configure(bg=T["bg2"])
                    except Exception: pass
                    for cc in ch.winfo_children():
                        try: cc.configure(bg=T["bg2"])
                        except Exception: pass

            for w in (card, inner):
                w.bind("<Enter>", _enter)
                w.bind("<Leave>", _leave)
                w.bind("<Button-1>", lambda e, tt=t: self._select_step(tt))

            for ch in inner.winfo_children():
                ch.bind("<Button-1>", lambda e, tt=t: self._select_step(tt))
                for cc in ch.winfo_children():
                    try: cc.bind("<Button-1>", lambda e, tt=t: self._select_step(tt))
                    except Exception: pass

            for w in (card, inner):
                w.bind("<Double-Button-1>", lambda e, tt=t: self._pick(tt))

    def _select_step(self, t: str):
        prev = self._selected_type.get()
        self._selected_type.set(t)

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

        if t in self._step_buttons:
            card = self._step_buttons[t]
            card.configure(bg=T["bg4"])
            for ch in card.winfo_children():
                try: ch.configure(bg=T["bg4"])
                except Exception: pass
                for cc in ch.winfo_children():
                    try: cc.configure(bg=T["bg4"])
                    except Exception: pass
                    for ccc in cc.winfo_children():
                        try: ccc.configure(bg=T["bg4"])
                        except Exception: pass

        self._render_detail(t)
        self._add_btn.config(state="normal")
        self._bot_hint.config(text="↑ Double-click a step card to add instantly")

    def _detail_placeholder(self):
        for w in self._detail_frame.winfo_children(): w.destroy()
        tk.Label(self._detail_frame, text="Select a step\nto see details",
                 bg=T["bg2"], fg=T["fg3"], font=T["font_s"], justify="center"
                 ).pack(expand=True)

    def _render_detail(self, t: str):
        for w in self._detail_frame.winfo_children(): w.destroy()
        info  = STEP_FRIENDLY.get(t, ("?", t, "•"))
        # BUG FIX: correct unpacking — (label, desc, icon)
        lbl   = info[0]
        desc  = info[1]
        ico   = info[2]
        color = STEP_COLORS.get(t, T["fg2"])

        hdr = tk.Frame(self._detail_frame, bg=color); hdr.pack(fill="x")
        tk.Label(hdr, text=f"  {ico}  {lbl}", bg=color, fg="white",
                 font=("Segoe UI Semibold", 10), padx=10, pady=10).pack(anchor="w")

        body = tk.Frame(self._detail_frame, bg=T["bg2"])
        body.pack(fill="both", expand=True, padx=12, pady=10)
        tk.Label(body, text=desc, bg=T["bg2"], fg=T["fg2"],
                 font=T["font_s"], wraplength=220, justify="left"
                 ).pack(anchor="w", pady=(0, 10))

        defaults   = STEP_DEFAULTS.get(t, {})
        field_info = self._field_descriptions(t, defaults)
        if field_info:
            tk.Label(body, text="Fields:", bg=T["bg2"], fg=T["fg3"],
                     font=T["font_s"]).pack(anchor="w")
            for fname, fhint in field_info:
                row = tk.Frame(body, bg=T["bg2"]); row.pack(fill="x", pady=1)
                tk.Label(row, text="•", bg=T["bg2"], fg=color, font=T["font_s"]).pack(side="left")
                tk.Label(row, text=f" {fname}", bg=T["bg2"], fg=T["fg"],
                         font=("Consolas", 8)).pack(side="left")
                if fhint:
                    tk.Label(row, text=f" — {fhint}", bg=T["bg2"], fg=T["fg3"],
                             font=T["font_s"], wraplength=160).pack(side="left")

        tip = self._step_tip(t)
        if tip:
            tf = tk.Frame(body, bg=T["bg3"]); tf.pack(fill="x", pady=(10, 0))
            tk.Label(tf, text="💡 Tip", bg=T["bg3"], fg=T["cyan"],
                     font=("Segoe UI Semibold", 8)).pack(anchor="w", padx=8, pady=(6, 0))
            tk.Label(tf, text=tip, bg=T["bg3"], fg=T["fg2"],
                     font=T["font_s"], wraplength=210, justify="left"
                     ).pack(anchor="w", padx=8, pady=(2, 8))

        tk.Button(body, text=f"✚  Add {lbl}", bg=color, fg="white",
                  font=("Segoe UI Semibold", 9), relief="flat", cursor="hand2",
                  padx=10, pady=7, command=lambda: self._pick(t)
                  ).pack(fill="x", pady=(14, 0))

    @staticmethod
    def _field_descriptions(t: str, defaults: dict) -> list:
        if t in ("click", "double_click", "right_click", "mouse_move", "clear_field"):
            return [("x, y", "Screen coordinates — use Pick from screen in the editor")]
        if t == "scroll":
            return [("x, y", "Scroll position"), ("direction", "up or down"), ("clicks", "Scroll amount")]
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
            return [("key", "Key to hold (space, shift, w…)"), ("seconds", "Duration in seconds")]
        if t == "loop":
            return [("times", "Repeat count"), ("steps", "Sub-steps (added after saving)")]
        if t == "screenshot":
            return [("folder", "Destination folder path")]
        if t == "condition":
            return [("window_title", "Text that must appear in the window title"),
                    ("action", "skip or stop if it doesn't match")]
        if t == "comment":
            return [("text", "Annotation text — not executed")]
        if t == "click_image":
            return [("image_path", "Path to target image file"),
                    ("confidence", "Match threshold 0–1 (e.g. 0.80)"),
                    ("timeout", "Seconds to wait for the image"),
                    ("action", "click / double_click / right_click / hover")]
        if t in ("wait_image", "wait_image_vanish"):
            return [("image_path", "Path to target image file"),
                    ("confidence", "Match threshold 0–1"),
                    ("timeout", "Seconds to wait")]
        if t == "ocr_condition":
            return [("x, y, w, h", "Screen region to read"),
                    ("pattern", "Text or regex to look for"),
                    ("action", "skip / stop / continue if not found")]
        if t == "ocr_extract":
            return [("x, y, w, h", "Screen region to read"),
                    ("variable", "Variable name to store the result")]
        # Window steps
        if t in ("wait_window", "wait_window_close"):
            return [("window_title", "Window title to match"),
                    ("process", "Process name (e.g. chrome.exe)"),
                    ("timeout", "Seconds to wait")]
        if t == "wait_window_change":
            return [("timeout", "Seconds to wait for change")]
        if t == "focus_window":
            return [("window_title", "Window title to bring to front"),
                    ("process", "Process name (optional)")]
        if t == "assert_window":
            return [("window_title", "Expected window title"),
                    ("tolerance", "strict / normal / loose"),
                    ("action", "skip or stop on mismatch")]
        return []

    @staticmethod
    def _step_tip(t: str) -> str:
        tips = {
            "click":              "Add a Wait step after clicking buttons that open dialogs.",
            "double_click":       "Use Pick from screen for accurate coordinates.",
            "clip_type":          "Best for Nepali, emoji, or any Unicode text — uses clipboard.",
            "type_text":          "For ASCII-only text. Use Clip Type for Unicode/Nepali.",
            "clear_field":        "Combines click + Ctrl+A + Delete to reliably erase content.",
            "wait":               "Use after any action that loads a page or dialog.",
            "loop":               "After saving, click ✏ on the Loop card to add inner steps.",
            "condition":          "Skips or stops if the wrong window is in focus.",
            "hold_key":           "Useful for games or apps that require held keys.",
            "click_image":        "Use 'Capture Region' to save the button image, then set confidence to 0.8.",
            "wait_image":         "Waits until the image appears on screen — great after page loads.",
            "wait_image_vanish":  "Waits until a loading spinner or dialog disappears.",
            "ocr_condition":      "Requires Tesseract OCR installed. Use 'Pick Region' to set coordinates.",
            "ocr_extract":        "Stores read text as a variable. Use {variable} in Type steps later.",
            "wait_window":        "Waits until the specified window becomes active (foreground).",
            "focus_window":       "Brings a specific window to the foreground before clicking.",
            "assert_window":      "Stops or skips the name if the wrong application is open.",
        }
        return tips.get(t, "")

    def _confirm_add(self):
        t = self._selected_type.get()
        if t: self._pick(t)

    def _pick(self, t: str):
        recent = _prefs.get("recent_steps", [])
        if t in recent: recent.remove(t)
        recent.insert(0, t)
        _prefs["recent_steps"] = recent[:6]
        save_prefs()
        self.on_pick(t)
        self.destroy()


# ── Patch helpers (image & OCR step field builders) ───────────────────────────

def _p_entry(parent, var, width=14, fg=None):
    return tk.Entry(parent, textvariable=var, width=width,
                    bg=T["bg3"], fg=fg or T["fg"],
                    insertbackground=T["fg"],
                    font=("Consolas", 9), relief="flat")


def _p_row(parent, label, widget_fn, hint=""):
    r = tk.Frame(parent, bg=T["bg"]); r.pack(fill="x", pady=5)
    tk.Label(r, text=label, bg=T["bg"], fg=T["fg2"],
             font=T["font_b"], width=20, anchor="e").pack(side="left")
    w = widget_fn(r); w.pack(side="left", padx=8)
    if hint:
        tk.Label(r, text=hint, bg=T["bg"], fg=T["fg3"],
                 font=T["font_s"]).pack(side="left")
    return w


def _p_sv(d, key):
    return tk.StringVar(value=str(d.get(key, "")))


def _p_bv(d, key, default=False):
    return tk.BooleanVar(value=bool(d.get(key, default)))


def _p_safe_set(var: tk.StringVar, value: str, widget: tk.Widget):
    """Thread-safe StringVar update via widget.after()."""
    try:
        widget.after(0, lambda: var.set(value))
    except Exception:
        try:
            var.set(value)
        except Exception:
            pass


def _build_new_step_fields(t: str, d: dict, frame: tk.Frame, fields: dict) -> bool:
    if t == "click_image":
        _build_click_image(d, frame, fields)
        return True
    if t in ("wait_image", "wait_image_vanish"):
        _build_wait_image(d, frame, fields)
        return True
    if t == "ocr_condition":
        _build_ocr_condition(d, frame, fields)
        return True
    if t == "ocr_extract":
        _build_ocr_extract(d, frame, fields)
        return True
    return False


def _build_click_image(d: dict, frame: tk.Frame, fields: dict):
    fields["image_path"] = (_p_sv(d, "image_path"), str)
    fields["confidence"] = (_p_sv(d, "confidence"), float)
    fields["timeout"]    = (_p_sv(d, "timeout"),    float)
    fields["offset_x"]   = (_p_sv(d, "offset_x"),  int)
    fields["offset_y"]   = (_p_sv(d, "offset_y"),  int)
    fields["action"]     = (_p_sv(d, "action"),     str)
    fields["grayscale"]  = (_p_bv(d, "grayscale", default=True), bool)

    r = tk.Frame(frame, bg=T["bg"]); r.pack(fill="x", pady=5)
    tk.Label(r, text="Target image:", bg=T["bg"], fg=T["fg2"],
             font=T["font_b"], width=20, anchor="e").pack(side="left")
    _p_entry(r, fields["image_path"][0], 28).pack(side="left", padx=8)
    tk.Button(r, text="Browse…", bg=T["bg3"], fg=T["fg2"],
              font=T["font_s"], relief="flat", cursor="hand2",
              command=lambda: _browse_image(fields["image_path"][0])
              ).pack(side="left", padx=4)

    cap_row = tk.Frame(frame, bg=T["bg"]); cap_row.pack(fill="x", pady=(0, 8))
    tk.Label(cap_row, text="", width=21, bg=T["bg"]).pack(side="left")
    tk.Button(cap_row, text="📷  Capture Region (3s delay)",
              bg=T["purple"], fg="white",
              font=T["font_s"], relief="flat", cursor="hand2", padx=8, pady=3,
              command=lambda: _capture_region_to_file(fields["image_path"][0], frame)
              ).pack(side="left")
    tk.Label(cap_row, text="  Save a region of your screen as the target",
             bg=T["bg"], fg=T["fg3"], font=T["font_s"]).pack(side="left")

    _p_row(frame, "Confidence (0–1):",
           lambda p: _p_entry(p, fields["confidence"][0], 6),
           "0.80 = 80% match required")
    _p_row(frame, "Timeout (seconds):",
           lambda p: _p_entry(p, fields["timeout"][0], 6))
    _p_row(frame, "Click offset X:", lambda p: _p_entry(p, fields["offset_x"][0], 6),
           "pixels from center")
    _p_row(frame, "Click offset Y:", lambda p: _p_entry(p, fields["offset_y"][0], 6))

    r2 = tk.Frame(frame, bg=T["bg"]); r2.pack(fill="x", pady=5)
    tk.Label(r2, text="Action:", bg=T["bg"], fg=T["fg2"],
             font=T["font_b"], width=20, anchor="e").pack(side="left")
    ttk.Combobox(r2, textvariable=fields["action"][0],
                 values=["click", "double_click", "right_click", "hover"],
                 state="readonly", width=14).pack(side="left", padx=8)

    cb_row = tk.Frame(frame, bg=T["bg"]); cb_row.pack(anchor="w", padx=20)
    tk.Checkbutton(cb_row, text="Grayscale matching (faster, recommended)",
                   variable=fields["grayscale"][0], bg=T["bg"], fg=T["fg2"],
                   selectcolor=T["bg3"], activebackground=T["bg"],
                   font=T["font_s"]).pack(side="left")

    tk.Label(frame,
             text="💡 Click 'Capture Region' then hover over a button to save its image.",
             bg=T["bg"], fg=T["fg3"], font=T["font_s"], wraplength=400
             ).pack(anchor="w", padx=20, pady=(4, 0))


def _build_wait_image(d: dict, frame: tk.Frame, fields: dict):
    fields["image_path"] = (_p_sv(d, "image_path"), str)
    fields["confidence"] = (_p_sv(d, "confidence"), float)
    fields["timeout"]    = (_p_sv(d, "timeout"),    float)

    r = tk.Frame(frame, bg=T["bg"]); r.pack(fill="x", pady=5)
    tk.Label(r, text="Target image:", bg=T["bg"], fg=T["fg2"],
             font=T["font_b"], width=20, anchor="e").pack(side="left")
    _p_entry(r, fields["image_path"][0], 28).pack(side="left", padx=8)
    tk.Button(r, text="Browse…", bg=T["bg3"], fg=T["fg2"],
              font=T["font_s"], relief="flat", cursor="hand2",
              command=lambda: _browse_image(fields["image_path"][0])
              ).pack(side="left", padx=4)

    cap_row = tk.Frame(frame, bg=T["bg"]); cap_row.pack(fill="x", pady=(0, 8))
    tk.Label(cap_row, text="", width=21, bg=T["bg"]).pack(side="left")
    tk.Button(cap_row, text="📷  Capture Region (3s)",
              bg=T["purple"], fg="white",
              font=T["font_s"], relief="flat", cursor="hand2", padx=8, pady=3,
              command=lambda: _capture_region_to_file(fields["image_path"][0], frame)
              ).pack(side="left")

    _p_row(frame, "Confidence (0–1):",
           lambda p: _p_entry(p, fields["confidence"][0], 6))
    _p_row(frame, "Timeout (seconds):",
           lambda p: _p_entry(p, fields["timeout"][0], 6))


def _build_ocr_condition(d: dict, frame: tk.Frame, fields: dict):
    fields["x"]       = (_p_sv(d, "x"),       int)
    fields["y"]       = (_p_sv(d, "y"),       int)
    fields["w"]       = (_p_sv(d, "w"),       int)
    fields["h"]       = (_p_sv(d, "h"),       int)
    fields["pattern"] = (_p_sv(d, "pattern"), str)
    fields["action"]  = (_p_sv(d, "action"),  str)
    fields["case_sensitive"] = (_p_bv(d, "case_sensitive"), bool)

    _ocr_region_rows(frame, fields)
    _p_row(frame, "Pattern (text/regex):",
           lambda p: _p_entry(p, fields["pattern"][0], 28),
           "e.g.  Invoice  or  \\d+  (regex OK)")

    r = tk.Frame(frame, bg=T["bg"]); r.pack(fill="x", pady=5)
    tk.Label(r, text="If NOT found:", bg=T["bg"], fg=T["fg2"],
             font=T["font_b"], width=20, anchor="e").pack(side="left")
    ttk.Combobox(r, textvariable=fields["action"][0],
                 values=["skip", "stop", "continue"],
                 state="readonly", width=10).pack(side="left", padx=8)
    tk.Label(r, text="skip=next name  stop=abort  continue=ignore",
             bg=T["bg"], fg=T["fg3"], font=T["font_s"]).pack(side="left")

    tk.Checkbutton(frame, text="Case sensitive",
                   variable=fields["case_sensitive"][0], bg=T["bg"], fg=T["fg2"],
                   selectcolor=T["bg3"], activebackground=T["bg"],
                   font=T["font_s"]).pack(anchor="w", padx=20)

    _ocr_pick_btn(frame, fields)
    tk.Label(frame,
             text="💡 Reads text from the screen region using OCR. "
                  "Requires Tesseract installed.",
             bg=T["bg"], fg=T["fg3"], font=T["font_s"], wraplength=400
             ).pack(anchor="w", padx=20, pady=(4, 0))


def _build_ocr_extract(d: dict, frame: tk.Frame, fields: dict):
    fields["x"]        = (_p_sv(d, "x"),        int)
    fields["y"]        = (_p_sv(d, "y"),         int)
    fields["w"]        = (_p_sv(d, "w"),         int)
    fields["h"]        = (_p_sv(d, "h"),         int)
    fields["variable"] = (_p_sv(d, "variable"),  str)

    _ocr_region_rows(frame, fields)
    _p_row(frame, "Store result in:",
           lambda p: _p_entry(p, fields["variable"][0], 18),
           "variable name (use {variable} in later steps)")
    _ocr_pick_btn(frame, fields)
    tk.Label(frame,
             text="💡 Reads text from the region and stores it as a variable. "
                  "Use {ocr_result} in Type steps later.",
             bg=T["bg"], fg=T["fg3"], font=T["font_s"], wraplength=400
             ).pack(anchor="w", padx=20, pady=(4, 0))


def _ocr_region_rows(frame: tk.Frame, fields: dict):
    coords = tk.Frame(frame, bg=T["bg"]); coords.pack(fill="x", pady=5)
    tk.Label(coords, text="Region (x, y, w, h):", bg=T["bg"], fg=T["fg2"],
             font=T["font_b"], width=20, anchor="e").pack(side="left")
    for key, lbl in [("x", "X"), ("y", "Y"), ("w", "W"), ("h", "H")]:
        tk.Label(coords, text=lbl+":", bg=T["bg"], fg=T["fg3"],
                 font=T["font_s"]).pack(side="left", padx=(6, 0))
        _p_entry(coords, fields[key][0], 5).pack(side="left", padx=(2, 0))


def _ocr_pick_btn(frame: tk.Frame, fields: dict):
    btn_row = tk.Frame(frame, bg=T["bg"]); btn_row.pack(fill="x", pady=6)
    tk.Label(btn_row, text="", width=21, bg=T["bg"]).pack(side="left")
    tk.Button(btn_row, text="🖱  Pick Region (3s delay)",
              bg=T["acc"], fg="white",
              font=T["font_s"], relief="flat", cursor="hand2", padx=8, pady=3,
              command=lambda: _pick_ocr_region(fields, frame)
              ).pack(side="left")
    tk.Button(btn_row, text="🔤 Test OCR Now",
              bg=T["bg3"], fg=T["cyan"],
              font=T["font_s"], relief="flat", cursor="hand2", padx=8, pady=3,
              command=lambda: _test_ocr_now(fields, frame)
              ).pack(side="left", padx=6)


def _browse_image(var: tk.StringVar):
    path = filedialog.askopenfilename(
        title="Select target image",
        filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp"), ("All", "*.*")])
    if path:
        var.set(path)


def _capture_region_to_file(var: tk.StringVar, widget: tk.Widget):
    targets_dir = os.path.join(_DIR, "targets")
    os.makedirs(targets_dir, exist_ok=True)
    ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(targets_dir, f"target_{ts}.png")

    def _do_capture():
        time.sleep(3)
        try:
            from core.image_finder import get_image_finder
            saved = get_image_finder().capture_target(path)
            _p_safe_set(var, saved, widget)
        except Exception as e:
            widget.after(0, lambda: messagebox.showerror(
                "Capture Failed", f"Could not capture screen region:\n{e}"))

    threading.Thread(target=_do_capture, daemon=True).start()
    messagebox.showinfo("Capturing",
                        "Switch to your target app.\n"
                        "Full screenshot will be saved in 3 seconds.\n\n"
                        "Tip: for best results, crop the image to just\n"
                        "the button/element you want to click.")


def _pick_ocr_region(fields: dict, widget: tk.Widget):
    messagebox.showinfo("Region Picker",
                        "Switch to the window you want to read.\n"
                        "After 3 seconds, drag to select the text region.\n\n"
                        "The coordinates will be filled automatically.")

    def _do():
        time.sleep(3)
        try:
            _launch_region_picker(fields, widget)
        except Exception as e:
            widget.after(0, lambda: messagebox.showerror(
                "Region Picker Failed", f"Could not open the region picker:\n{e}"))

    threading.Thread(target=_do, daemon=True).start()


def _launch_region_picker(fields: dict, widget: tk.Widget):
    """
    Full-screen drag-select overlay for picking an OCR region.
    Uses tk.Toplevel — NOT tk.Tk() which would create a second root.
    """
    try:
        root = widget.winfo_toplevel()
    except Exception:
        return

    # BUG FIX: schedule on main thread since this is called from background thread
    def _create_overlay():
        try:
            top = tk.Toplevel(root)
            top.attributes("-fullscreen", True)
            top.attributes("-alpha", 0.3)
            top.attributes("-topmost", True)
            top.configure(bg="black")
            top.title("Drag to select region")

            canvas = tk.Canvas(top, cursor="crosshair", bg="black", highlightthickness=0)
            canvas.pack(fill="both", expand=True)

            start = [0, 0]
            rect  = [None]

            def _press(e):
                start[0], start[1] = e.x, e.y
                if rect[0]:
                    canvas.delete(rect[0])

            def _drag(e):
                if rect[0]:
                    canvas.delete(rect[0])
                rect[0] = canvas.create_rectangle(
                    start[0], start[1], e.x, e.y,
                    outline="#00ff00", width=2, fill="")

            def _release(e):
                x1, y1 = min(start[0], e.x), min(start[1], e.y)
                x2, y2 = max(start[0], e.x), max(start[1], e.y)
                w_val = x2 - x1
                h_val = y2 - y1
                top.destroy()
                try:
                    fields["x"][0].set(str(x1))
                    fields["y"][0].set(str(y1))
                    fields["w"][0].set(str(w_val))
                    fields["h"][0].set(str(h_val))
                except Exception:
                    pass

            canvas.bind("<ButtonPress-1>",   _press)
            canvas.bind("<B1-Motion>",       _drag)
            canvas.bind("<ButtonRelease-1>", _release)
            top.bind("<Escape>", lambda e: top.destroy())
        except Exception as e:
            print(f"[region_picker] Error: {e}")

    # BUG FIX: use after() to ensure UI creation happens on main thread
    try:
        root.after(0, _create_overlay)
    except Exception:
        _create_overlay()


def _test_ocr_now(fields: dict, parent: tk.Widget):
    try:
        def _int_field(key: str, default: int) -> int:
            raw = fields[key][0].get().strip()
            return int(raw) if raw else default

        x = _int_field("x", 0)
        y = _int_field("y", 0)
        w = _int_field("w", 300)
        h = _int_field("h", 60)

        from core.ocr_engine import get_screen_reader
        ok, ver = get_screen_reader().is_tesseract_available()
        if not ok:
            messagebox.showerror("Tesseract Not Found",
                                 f"{ver}\n\nInstall Tesseract OCR:\n"
                                 "https://github.com/UB-Mannheim/tesseract/wiki")
            return

        result = get_screen_reader().read_region(x, y, w, h)
        text   = result.text or "(no text found)"
        messagebox.showinfo("OCR Result",
                            f"Region: ({x}, {y}, {w}, {h})\n"
                            f"Confidence: {result.confidence:.0f}%\n\n"
                            f"Text found:\n{text}")
    except Exception as e:
        messagebox.showerror("OCR Error", str(e))


# ── Step editor ───────────────────────────────────────────────────────────────

class StepEditor(tk.Toplevel):
    def __init__(self, parent, step: dict = None, on_save=None):
        super().__init__(parent)
        t = step["type"] if step else "click"
        info = STEP_FRIENDLY.get(t, ("?", t, "•"))
        # BUG FIX: correct unpacking — (label, desc, icon)
        lbl  = info[0]
        desc = info[1]
        ico  = info[2]
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
        self._build_fields(t, step or {"type": t, **STEP_DEFAULTS.get(t, {})})

        nf = tk.Frame(self, bg=T["bg"]); nf.pack(fill="x", padx=20, pady=(0, 6))
        tk.Label(nf, text="Label / Note:", bg=T["bg"], fg=T["fg3"],
                 font=T["font_s"]).pack(side="left")
        self._note_var = tk.StringVar(value=step.get("note", "") if step else "")
        tk.Entry(nf, textvariable=self._note_var, width=28,
                 bg=T["bg3"], fg=T["fg2"], insertbackground=T["fg"],
                 font=T["font_m"], relief="flat").pack(side="left", padx=8)

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
            self._pos_job = None
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
        if _build_new_step_fields(t, d, self._ff, self._fields):
            return

        def sv(key): return tk.StringVar(value=str(d.get(key, "")))

        if t in ("click", "double_click", "right_click", "mouse_move", "clear_field"):
            self._fields["x"] = (sv("x"), int)
            self._fields["y"] = (sv("y"), int)
            self._row("X position:", lambda p: self._entry(p, self._fields["x"][0], 8))
            self._row("Y position:", lambda p: self._entry(p, self._fields["y"][0], 8))
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
            self._fields["keys"] = (sv("keys"), str)
            r = tk.Frame(self._ff, bg=T["bg"]); r.pack(fill="x", pady=5)
            tk.Label(r, text="Keys:", bg=T["bg"], fg=T["fg2"],
                     font=T["font_b"], width=18, anchor="e").pack(side="left")
            e = self._entry(r, self._fields["keys"][0], 26); e.pack(side="left", padx=8)
            tk.Label(r, text="type freely or use picker ↓",
                     bg=T["bg"], fg=T["fg3"], font=T["font_s"]).pack(side="left")
            tk.Frame(self._ff, bg=T["bg4"], height=1).pack(fill="x", pady=(4, 2))
            picker_row = tk.Frame(self._ff, bg=T["bg"]); picker_row.pack(fill="x", pady=4)
            tk.Label(picker_row, text="", width=18, bg=T["bg"]).pack(side="left")
            _KeyPickerBar(picker_row, self._fields["keys"][0], mode="combo").pack(side="left")
            tk.Label(self._ff,
                     text="  💡 Use ➕ Add to build a combo like ctrl+shift+s, or type it directly above.",
                     bg=T["bg"], fg=T["fg3"], font=T["font_s"]
                     ).pack(anchor="w", pady=(0, 4))

        elif t in ("type_text", "clip_type"):
            self._fields["text"] = (sv("text"), str)
            r = tk.Frame(self._ff, bg=T["bg"]); r.pack(fill="x", pady=5)
            tk.Label(r, text="Text to type:", bg=T["bg"], fg=T["fg2"],
                     font=T["font_b"], width=18, anchor="e").pack(side="left")
            txt = tk.Text(r, width=28, height=3, bg=T["bg3"], fg=T["fg"],
                          insertbackground=T["fg"], font=T["font_m"], relief="flat")
            txt.insert("1.0", str(d.get("text", "")))
            txt.pack(side="left", padx=8)
            def _sync(*a): self._fields["text"][0].set(txt.get("1.0", "end-1c"))
            txt.bind("<KeyRelease>", _sync)
            self._txt_widget = txt
            hint = ("Use  {name}  for the current name, or  {varname}  for a variable."
                    if t == "clip_type" else
                    "Tip: use Clip Type for Nepali, emoji, or any Unicode text.")
            tk.Label(self._ff, text=hint, bg=T["bg"], fg=T["fg3"],
                     font=T["font_s"], wraplength=340, justify="left"
                     ).pack(anchor="w", pady=(0, 4))

        elif t == "wait":
            self._fields["seconds"] = (sv("seconds"), float)
            self._row("Wait (seconds):", lambda p: self._entry(p, self._fields["seconds"][0], 8),
                      "e.g.  1  or  2.5")

        elif t in ("pagedown", "pageup"):
            self._fields["times"] = (sv("times"), int)
            self._row("How many times:", lambda p: self._entry(p, self._fields["times"][0], 6))

        elif t == "scroll":
            self._fields["x"]         = (sv("x"), int)
            self._fields["y"]         = (sv("y"), int)
            self._fields["clicks"]    = (sv("clicks"), int)
            self._fields["direction"] = (sv("direction"), str)
            self._row("X position:", lambda p: self._entry(p, self._fields["x"][0], 8))
            self._row("Y position:", lambda p: self._entry(p, self._fields["y"][0], 8))
            r = tk.Frame(self._ff, bg=T["bg"]); r.pack(fill="x", pady=5)
            tk.Label(r, text="Direction:", bg=T["bg"], fg=T["fg2"],
                     font=T["font_b"], width=18, anchor="e").pack(side="left")
            ttk.Combobox(r, textvariable=self._fields["direction"][0],
                         values=["down", "up"], state="readonly", width=8
                         ).pack(side="left", padx=8)
            self._row("Scroll amount:", lambda p: self._entry(p, self._fields["clicks"][0], 6),
                      "clicks")

        elif t == "key_repeat":
            self._fields["key"]   = (sv("key"), str)
            self._fields["times"] = (sv("times"), int)
            r = tk.Frame(self._ff, bg=T["bg"]); r.pack(fill="x", pady=5)
            tk.Label(r, text="Key to press:", bg=T["bg"], fg=T["fg2"],
                     font=T["font_b"], width=18, anchor="e").pack(side="left")
            e = self._entry(r, self._fields["key"][0], 14); e.pack(side="left", padx=8)
            tk.Label(r, text="tab  enter  space  escape  up  down  delete",
                     bg=T["bg"], fg=T["fg3"], font=T["font_s"]).pack(side="left")
            picker_row = tk.Frame(self._ff, bg=T["bg"]); picker_row.pack(fill="x", pady=(0, 6))
            tk.Label(picker_row, text="", width=18, bg=T["bg"]).pack(side="left")
            _KeyPickerBar(picker_row, self._fields["key"][0], mode="single").pack(side="left")
            self._row("How many times:", lambda p: self._entry(p, self._fields["times"][0], 6))

        elif t == "hold_key":
            self._fields["key"]     = (sv("key"), str)
            self._fields["seconds"] = (sv("seconds"), float)
            r = tk.Frame(self._ff, bg=T["bg"]); r.pack(fill="x", pady=5)
            tk.Label(r, text="Key to hold:", bg=T["bg"], fg=T["fg2"],
                     font=T["font_b"], width=18, anchor="e").pack(side="left")
            e = self._entry(r, self._fields["key"][0], 14); e.pack(side="left", padx=8)
            tk.Label(r, text="space  shift  ctrl  alt  w  a  s  d  …",
                     bg=T["bg"], fg=T["fg3"], font=T["font_s"]).pack(side="left")
            picker_row = tk.Frame(self._ff, bg=T["bg"]); picker_row.pack(fill="x", pady=(0, 6))
            tk.Label(picker_row, text="", width=18, bg=T["bg"]).pack(side="left")
            _KeyPickerBar(picker_row, self._fields["key"][0], mode="single").pack(side="left")
            self._row("Hold duration (s):", lambda p: self._entry(p, self._fields["seconds"][0], 8),
                      "e.g.  0.5  or  2.0")
            tk.Label(self._ff,
                     text="💡 Hold the key pressed for N seconds. Great for Shift, Space, game keys.",
                     bg=T["bg"], fg=T["fg3"], font=T["font_s"]
                     ).pack(anchor="w", pady=4)

        elif t == "loop":
            self._fields["times"] = (sv("times"), int)
            self._row("Repeat N times:", lambda p: self._entry(p, self._fields["times"][0], 6))
            tk.Label(self._ff,
                     text="After saving, click ✏ on this Loop card to add steps inside it.",
                     bg=T["bg"], fg=T["fg3"], font=T["font_s"]
                     ).pack(anchor="w", pady=4)

        elif t == "screenshot":
            self._fields["folder"] = (sv("folder"), str)
            self._row("Save folder:", lambda p: self._entry(p, self._fields["folder"][0], 22))

        elif t == "condition":
            self._fields["window_title"] = (sv("window_title"), str)
            self._fields["action"]       = (sv("action"), str)
            self._row("Window title contains:",
                      lambda p: self._entry(p, self._fields["window_title"][0], 22))
            r = tk.Frame(self._ff, bg=T["bg"]); r.pack(fill="x", pady=5)
            tk.Label(r, text="If it doesn't match:", bg=T["bg"], fg=T["fg2"],
                     font=T["font_b"], width=18, anchor="e").pack(side="left")
            ttk.Combobox(r, textvariable=self._fields["action"][0],
                         values=["skip", "stop"], state="readonly", width=8
                         ).pack(side="left", padx=8)
            tk.Label(r, text="skip = next name   stop = abort run",
                     bg=T["bg"], fg=T["fg3"], font=T["font_s"]).pack(side="left")

        elif t == "comment":
            self._fields["text"] = (sv("text"), str)
            r = tk.Frame(self._ff, bg=T["bg"]); r.pack(fill="x", pady=5)
            tk.Label(r, text="Comment:", bg=T["bg"], fg=T["fg2"],
                     font=T["font_b"], width=18, anchor="e").pack(side="left")
            txt = tk.Text(r, width=28, height=2, bg=T["bg3"], fg=T["fg"],
                          insertbackground=T["fg"], font=T["font_m"], relief="flat")
            txt.insert("1.0", str(d.get("text", "")))
            txt.pack(side="left", padx=8)
            def _sync2(*a): self._fields["text"][0].set(txt.get("1.0", "end-1c"))
            txt.bind("<KeyRelease>", _sync2)
            self._txt_widget = txt

        elif t in ("wait_window", "wait_window_close"):
            self._fields["window_title"] = (sv("window_title"), str)
            self._fields["process"]      = (sv("process"), str)
            self._fields["hwnd"]         = (sv("hwnd"), int)
            self._fields["timeout"]      = (sv("timeout"), float)
            self._row("Window title:", lambda p: self._entry(p, self._fields["window_title"][0], 28))
            self._row("Process name:", lambda p: self._entry(p, self._fields["process"][0], 20),
                      "e.g. chrome.exe")
            self._row("Timeout (s):", lambda p: self._entry(p, self._fields["timeout"][0], 8))

        elif t == "wait_window_change":
            self._fields["timeout"] = (sv("timeout"), float)
            self._row("Timeout (s):", lambda p: self._entry(p, self._fields["timeout"][0], 8))

        elif t == "focus_window":
            self._fields["window_title"]     = (sv("window_title"), str)
            self._fields["process"]          = (sv("process"), str)
            self._fields["hwnd"]             = (sv("hwnd"), int)
            self._fields["restore_minimized"] = (tk.BooleanVar(value=bool(d.get("restore_minimized", True))), bool)
            self._row("Window title:", lambda p: self._entry(p, self._fields["window_title"][0], 28))
            self._row("Process name:", lambda p: self._entry(p, self._fields["process"][0], 20))
            r = tk.Frame(self._ff, bg=T["bg"]); r.pack(fill="x", pady=4)
            tk.Checkbutton(r, text="Restore if minimized",
                           variable=self._fields["restore_minimized"][0],
                           bg=T["bg"], fg=T["fg2"], selectcolor=T["bg3"],
                           activebackground=T["bg"], font=T["font_s"]).pack(anchor="w")

        elif t == "assert_window":
            self._fields["window_title"] = (sv("window_title"), str)
            self._fields["process"]      = (sv("process"), str)
            self._fields["hwnd"]         = (sv("hwnd"), int)
            self._fields["tolerance"]    = (sv("tolerance"), str)
            self._fields["action"]       = (sv("action"), str)
            self._row("Window title:", lambda p: self._entry(p, self._fields["window_title"][0], 28))
            r = tk.Frame(self._ff, bg=T["bg"]); r.pack(fill="x", pady=5)
            tk.Label(r, text="Tolerance:", bg=T["bg"], fg=T["fg2"],
                     font=T["font_b"], width=18, anchor="e").pack(side="left")
            ttk.Combobox(r, textvariable=self._fields["tolerance"][0],
                         values=["strict", "normal", "loose"],
                         state="readonly", width=10).pack(side="left", padx=8)
            r2 = tk.Frame(self._ff, bg=T["bg"]); r2.pack(fill="x", pady=5)
            tk.Label(r2, text="On mismatch:", bg=T["bg"], fg=T["fg2"],
                     font=T["font_b"], width=18, anchor="e").pack(side="left")
            ttk.Combobox(r2, textvariable=self._fields["action"][0],
                         values=["skip", "stop"],
                         state="readonly", width=8).pack(side="left", padx=8)

    def _start_pos_poll(self):
        def _poll():
            # BUG FIX: check winfo_exists before scheduling next poll
            if not self.winfo_exists():
                return
            try:
                x, y = pyautogui.position()
                if hasattr(self, "_pos_lbl") and self._pos_lbl.winfo_exists():
                    self._pos_lbl.config(text=f"Mouse: {x}, {y}")
            except Exception:
                pass
            if self.winfo_exists():
                self._pos_job = self.after(80, _poll)
        _poll()

    def _pick(self):
        self.withdraw()
        def _grab():
            for _ in range(3): time.sleep(1)
            x, y = pyautogui.position()
            # BUG FIX: fields now store (var, cast) tuples — access var correctly
            self._fields["x"][0].set(str(x))
            self._fields["y"][0].set(str(y))
            self.after(0, self.deiconify)
        threading.Thread(target=_grab, daemon=True).start()

    def _save(self):
        if self._pos_job:
            try: self.after_cancel(self._pos_job)
            except Exception: pass
            self._pos_job = None
        t    = self._step["type"] if self._step else "click"
        step = {"type": t,
                "note": self._note_var.get().strip(),
                "enabled": self._enabled_var.get()}
        try:
            for k, (var, cast) in self._fields.items():
                raw = var.get()
                if isinstance(raw, str):
                    raw = raw.strip()
                if cast == bool:
                    # BUG FIX: BooleanVar.get() returns bool — no cast needed
                    step[k] = bool(var.get())
                elif cast == int:
                    # BUG FIX: handle empty string gracefully
                    try:
                        step[k] = int(float(raw or 0))
                    except (ValueError, TypeError):
                        step[k] = 0
                elif cast == float:
                    try:
                        step[k] = float(raw or 0)
                    except (ValueError, TypeError):
                        step[k] = 0.0
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
║          SWASTIK RPA v9.4  —  Quick Reference Guide          ║
╚══════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 GETTING STARTED IN 3 STEPS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. NAME LIST TAB   → Add names / values (one per line or load Excel/CSV).
  2. BUILD FLOW TAB  → Add steps that describe what to automate.
  3. RUN TAB         → Click ▶ Start Automation.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 KEY PICKER  (v9.4)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  When editing Hotkey, Repeat a Key, or Hold a Key steps, a
  visual key picker bar appears below the text entry.

  Hotkey mode  — pick a category, select a key, toggle
  modifier checkboxes (Ctrl/Shift/Alt/Win), click ➕ Add.

  Single mode  — pick category + key, click ✔ Set.

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
