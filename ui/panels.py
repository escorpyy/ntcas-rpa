"""
ui/panels.py
============
Major UI panels:
  FlowPanel          – build / edit a list of steps (inline compact view)
  FlowEditorWindow   – maximised drag-drop-replace editor (full-size)
  NameListPanel      – manage the name list (paste or load from Excel/CSV)
  RunStatusPanel     – run controls, settings, log

BUG FIXES vs V9:
  - FlowPanel._drag_end: target clamped correctly, avoids IndexError
  - FlowEditorWindow._on_close: properly compares step lists (deepcopy)
  - RunStatusPanel.log: auto-scroll only when already near bottom
  - NameListPanel recent-file buttons rebuilt after first file load
  - FlowPanel._step_card hover: bg restored correctly for disabled steps
"""

import copy, datetime, os, queue, time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from collections import deque

import pandas as pd

from core.constants import (
    T, STEP_TYPES, STEP_FRIENDLY, STEP_DEFAULTS, STEP_COLORS,
    TEMPLATES, L, _prefs, _DIR,
    load_json_file, save_json_file, RECENT_FILE,
)
from core.helpers import step_summary, step_human_label

from .dialogs import (
    Tooltip, FindReplaceDialog, StepPickerDialog, StepEditor,
)


# ── Flow panel (inline compact view) ─────────────────────────────────────────

class FlowPanel(tk.Frame):
    MAX_UNDO = 40

    def __init__(self, parent, panel_id: str = "main", other_panel_fn=None, **kw):
        super().__init__(parent, bg=T["bg"], **kw)
        self.panel_id       = panel_id
        self.other_panel_fn = other_panel_fn
        self.steps: list    = []
        self._undo          = deque(maxlen=self.MAX_UNDO)
        self._redo          = deque(maxlen=self.MAX_UNDO)
        self._drag_src      = None
        self._drag_ghost    = None
        self._drop_line     = None
        self._build()

    # ── Undo / Redo ───────────────────────────────────────────────────────────

    def _save_undo(self):
        self._undo.append(copy.deepcopy(self.steps))
        self._redo.clear()

    def undo(self):
        if not self._undo: return
        self._redo.append(copy.deepcopy(self.steps))
        self.steps = self._undo.pop(); self._refresh()

    def redo(self):
        if not self._redo: return
        self._undo.append(copy.deepcopy(self.steps))
        self.steps = self._redo.pop(); self._refresh()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        tb = tk.Frame(self, bg=T["bg"]); tb.pack(fill="x", pady=(0, 4))

        def btn(text, bg, fg, cmd, tip="", side="left", padx=3):
            b = tk.Button(tb, text=text, bg=bg, fg=fg, font=T["font_s"],
                          relief="flat", cursor="hand2", padx=6, pady=3, command=cmd)
            b.pack(side=side, padx=padx)
            if tip: Tooltip(b, tip)
            return b

        btn(L("add_step"),     T["acc"],  "white",     self._add_step,      "+ Add a step")
        btn("↩ Undo",          T["bg3"],  T["fg2"],    self.undo,           "Undo  (Ctrl+Z)")
        btn("↪ Redo",          T["bg3"],  T["fg2"],    self.redo,           "Redo  (Ctrl+Y)")
        btn("🔍 Find/Replace", T["bg3"],  T["fg2"],    self._find_replace,  "Find & Replace")
        btn("⧉ Copy Other",    T["bg3"],  T["fg2"],    self._copy_other,    "Copy steps from the other panel")
        btn("⛶ Full Editor",   T["bg3"],  T["purple"], self._open_full_editor,
            "Open a maximised drag-drop editor window")

        self._count_lbl = tk.Label(tb, text="", bg=T["bg"],
                                   fg=T["fg3"], font=T["font_s"])
        self._count_lbl.pack(side="right", padx=6)
        btn(L("clear_all"), T["bg3"], T["red"], self._clear, "Remove all steps", side="right")

        # Templates row
        tmpl_f = tk.Frame(self, bg=T["bg2"]); tmpl_f.pack(fill="x", pady=(0, 4))
        tk.Label(tmpl_f, text="Templates:", bg=T["bg2"], fg=T["fg3"],
                 font=T["font_s"]).pack(side="left", padx=8)
        for name, tdata in TEMPLATES.items():
            tk.Button(tmpl_f, text=f"{tdata['icon']} {name}",
                      bg=T["bg3"], fg=T["fg2"], font=T["font_s"],
                      relief="flat", cursor="hand2", padx=6, pady=2,
                      command=lambda d=tdata: self._load_template(d)
                      ).pack(side="left", padx=2, pady=3)

        # Search bar
        sf = tk.Frame(self, bg=T["bg"]); sf.pack(fill="x", pady=(2, 4))
        tk.Label(sf, text="🔍", bg=T["bg"], fg=T["fg3"],
                 font=T["font_s"]).pack(side="left", padx=(0, 2))
        self._search = tk.StringVar()
        self._search.trace_add("write", lambda *a: self._refresh())
        tk.Entry(sf, textvariable=self._search, width=18,
                 bg=T["bg3"], fg=T["fg"], insertbackground=T["fg"],
                 font=T["font_m"], relief="flat").pack(side="left")
        tk.Label(sf, text=L("step_search"), bg=T["bg"],
                 fg=T["fg3"], font=T["font_s"]).pack(side="left", padx=4)
        tk.Label(sf, text="≡ Drag  •  dbl-click to edit",
                 bg=T["bg"], fg=T["fg3"], font=T["font_s"]).pack(side="right", padx=8)

        # Scrollable canvas
        outer = tk.Frame(self, bg=T["bg"]); outer.pack(fill="both", expand=True)
        self._canvas = tk.Canvas(outer, bg=T["bg"], highlightthickness=0, height=260)
        sb = ttk.Scrollbar(outer, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._frame = tk.Frame(self._canvas, bg=T["bg"])
        self._win   = self._canvas.create_window((0, 0), window=self._frame, anchor="nw")
        self._frame.bind("<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
            lambda e: self._canvas.itemconfig(self._win, width=e.width))
        self._canvas.bind("<MouseWheel>",
            lambda e: self._canvas.yview_scroll(-1*(e.delta//120), "units"))
        self._refresh()

    # ── Render ────────────────────────────────────────────────────────────────

    def _refresh(self):
        if self._drag_ghost:
            try: self._drag_ghost.destroy()
            except Exception: pass
            self._drag_ghost = None
        self._drag_src  = None
        self._drop_line = None
        for w in self._frame.winfo_children(): w.destroy()

        query = self._search.get().lower().strip() if hasattr(self, "_search") else ""
        n     = len(self.steps)
        self._count_lbl.config(text=f"{n} step{'s' if n != 1 else ''}")

        if not self.steps:
            ef = tk.Frame(self._frame, bg=T["bg"]); ef.pack(fill="x", pady=30)
            tk.Label(ef, text="No steps yet",
                     font=("Segoe UI Semibold", 11), bg=T["bg"], fg=T["fg3"]).pack()
            tk.Label(ef, text="Click  + Add Step  or pick a template above.",
                     font=T["font_s"], bg=T["bg"], fg=T["fg3"]).pack(pady=4)
            return

        visible = [(i, s) for i, s in enumerate(self.steps)
                   if not query
                   or query in STEP_FRIENDLY.get(s["type"], ("", "", ""))[0].lower()
                   or query in step_summary(s).lower()
                   or query in s.get("note", "").lower()
                   or query in s["type"].lower()]

        if query and not visible:
            tk.Label(self._frame, text=f'No steps match "{query}"',
                     bg=T["bg"], fg=T["fg3"], font=T["font_s"]).pack(pady=12)
            return

        for i, step in visible:
            self._step_card(i, step)

    def _step_card(self, i: int, step: dict):
        t       = step["type"]
        enabled = step.get("enabled", True)
        color   = STEP_COLORS.get(t, T["fg2"]) if enabled else T["fg3"]
        card_bg = T["bg2"] if enabled else T["bg"]
        ico, lbl, _, _ = step_human_label(step)
        summary = step_summary(step)
        note    = step.get("note", "")

        if i > 0:
            af = tk.Frame(self._frame, bg=T["bg"], height=14); af.pack(fill="x")
            tk.Label(af, text="↓", bg=T["bg"],
                     fg=T["fg3"] if enabled else T["bg3"],
                     font=("Segoe UI", 8)).pack()

        wrapper = tk.Frame(self._frame, bg=T["bg"])
        wrapper.pack(fill="x")
        wrapper._step_index = i

        card = tk.Frame(wrapper, bg=card_bg, relief="flat")
        card.pack(fill="x", pady=1)
        tk.Frame(card, bg=color, width=5).pack(side="left", fill="y")

        handle = tk.Label(card, text="≡", bg=T["bg3"], fg=T["fg3"],
                          font=("Segoe UI", 11), padx=8, cursor="fleur", width=2)
        handle.pack(side="left", fill="y")
        Tooltip(handle, "Drag to reorder")

        body = tk.Frame(card, bg=card_bg)
        body.pack(side="left", fill="both", expand=True, padx=10, pady=8)
        top  = tk.Frame(body, bg=card_bg); top.pack(fill="x")

        tk.Label(top, text=f"{i+1}.", width=3, bg=card_bg,
                 fg=T["fg3"] if enabled else T["bg4"],
                 font=T["font_s"]).pack(side="left")
        lbl_text = f"⊘ {lbl}" if not enabled else f"{ico} {lbl}"
        tk.Label(top, text=lbl_text, bg=card_bg, fg=color,
                 font=("Segoe UI Semibold", 9)).pack(side="left", padx=4)
        if summary:
            tk.Label(top, text=summary, bg=card_bg,
                     fg=T["fg2"] if enabled else T["fg3"],
                     font=T["font_m"]).pack(side="left", padx=6)
        if note:
            tk.Label(top, text=f"// {note}", bg=card_bg,
                     fg=T["fg3"], font=T["font_s"]).pack(side="left")

        acts = tk.Frame(card, bg=card_bg); acts.pack(side="right", padx=6, pady=4)
        eye_txt = "👁" if enabled else "🚫"
        for txt, tip, cmd in [
            (eye_txt, "Toggle enabled",  lambda i=i: self._toggle_enabled(i)),
            ("✏",     L("edit"),         lambda i=i: self._edit(i)),
            ("⧉",     L("duplicate"),    lambda i=i: self._dup(i)),
            ("▲",     L("move_up"),      lambda i=i: self._mv(i, -1)),
            ("▼",     L("move_down"),    lambda i=i: self._mv(i,  1)),
            ("✕",     L("delete"),       lambda i=i: self._del(i)),
        ]:
            b = tk.Button(acts, text=txt, bg=card_bg, fg=T["fg3"],
                          font=("Segoe UI", 9), relief="flat", cursor="hand2",
                          padx=4, activebackground=T["bg3"], command=cmd)
            b.pack(side="left"); Tooltip(b, tip)

        all_bg = [card, body, acts, top]

        def _enter(e, hover_bg=T["bg3"], normal_bg=card_bg):
            if not step.get("enabled", True): return
            for w in all_bg: w.configure(bg=hover_bg)
            for ch in top.winfo_children():  ch.configure(bg=hover_bg)
            for ch in acts.winfo_children():
                if isinstance(ch, tk.Button): ch.configure(bg=hover_bg)

        def _leave(e, hover_bg=T["bg3"], normal_bg=card_bg):
            if not step.get("enabled", True): return
            for w in all_bg: w.configure(bg=normal_bg)
            for ch in top.winfo_children():  ch.configure(bg=normal_bg)
            for ch in acts.winfo_children():
                if isinstance(ch, tk.Button): ch.configure(bg=normal_bg)

        for w in (card, body):
            w.bind("<Enter>", _enter); w.bind("<Leave>", _leave)
        for w in (card, body, top):
            w.bind("<Double-Button-1>", lambda e, idx=i: self._edit(idx))

        handle.bind("<ButtonPress-1>",   lambda e, idx=i: self._drag_start(e, idx))
        handle.bind("<B1-Motion>",       lambda e, idx=i: self._drag_motion(e, idx))
        handle.bind("<ButtonRelease-1>", lambda e, idx=i: self._drag_end(e, idx))

    # ── Drag reorder ──────────────────────────────────────────────────────────

    def _drag_start(self, event, idx: int):
        self._drag_src = idx
        step  = self.steps[idx]
        ico, lbl, _, _ = step_human_label(step)
        color = STEP_COLORS.get(step["type"], T["fg2"])
        g = tk.Toplevel(self); g.overrideredirect(True)
        g.attributes("-alpha", 0.80); g.attributes("-topmost", True)
        tk.Label(tk.Frame(g, bg=color).pack() or g,
                 text=f"  {ico} {lbl}  ", bg=color, fg="white",
                 font=("Segoe UI Semibold", 9), padx=10, pady=6).pack()
        self._drag_ghost = g
        self._drag_motion(event, idx)

    def _drag_motion(self, event, idx: int):
        if self._drag_ghost:
            rx = event.widget.winfo_rootx() + event.x + 10
            ry = event.widget.winfo_rooty() + event.y + 10
            self._drag_ghost.geometry(f"+{rx}+{ry}")
        cy = self._canvas.canvasy(
            event.widget.winfo_rooty() + event.y - self._canvas.winfo_rooty())
        self._show_drop_indicator(self._y_to_step_index(cy))

    def _drag_end(self, event, idx: int):
        if self._drag_ghost:
            try: self._drag_ghost.destroy()
            except Exception: pass
            self._drag_ghost = None
        if self._drop_line:
            try: self._drop_line.destroy()
            except Exception: pass
            self._drop_line = None

        cy  = self._canvas.canvasy(
            event.widget.winfo_rooty() + event.y - self._canvas.winfo_rooty())
        tgt = self._y_to_step_index(cy)
        src = self._drag_src; self._drag_src = None

        if src is None or tgt is None: return
        tgt = max(0, min(tgt, len(self.steps) - 1))
        if src == tgt: return

        self._save_undo()
        step = self.steps.pop(src)
        self.steps.insert(tgt, step)
        self._refresh()

    def _y_to_step_index(self, canvas_y: float) -> int:
        children = [w for w in self._frame.winfo_children() if hasattr(w, "_step_index")]
        if not children: return 0
        for w in children:
            mid = w.winfo_y() + w.winfo_height() / 2
            if canvas_y < mid:
                return w._step_index
        return children[-1]._step_index

    def _show_drop_indicator(self, tgt_idx: int):
        if self._drop_line:
            try: self._drop_line.destroy()
            except Exception: pass
            self._drop_line = None
        children = [w for w in self._frame.winfo_children() if hasattr(w, "_step_index")]
        tgt_w = next((w for w in children if w._step_index == tgt_idx), None)
        if not tgt_w: return
        line = tk.Frame(self._frame, bg=T["acc"], height=3)
        line.place(in_=tgt_w, relx=0, rely=0, relwidth=1)
        self._drop_line = line

    # ── Step actions ──────────────────────────────────────────────────────────

    def _add_step(self):
        def on_pick(t):
            d = {"type": t, **copy.deepcopy(STEP_DEFAULTS[t])}
            StepEditor(self, step=d, on_save=self._append)
        StepPickerDialog(self, on_pick)

    def _append(self, s: dict):   self._save_undo(); self.steps.append(s);        self._refresh()
    def _edit(self, i: int):      StepEditor(self, step=self.steps[i],
                                             on_save=lambda s, i=i: self._replace(i, s))
    def _replace(self, i, s):     self._save_undo(); self.steps[i] = s;           self._refresh()
    def _del(self, i: int):       self._save_undo(); self.steps.pop(i);           self._refresh()
    def _dup(self, i: int):
        self._save_undo()
        self.steps.insert(i+1, copy.deepcopy(self.steps[i]))
        self._refresh()
    def _mv(self, i: int, d: int):
        j = i + d
        if 0 <= j < len(self.steps):
            self._save_undo()
            self.steps[i], self.steps[j] = self.steps[j], self.steps[i]
            self._refresh()
    def _toggle_enabled(self, i: int):
        self._save_undo()
        self.steps[i]["enabled"] = not self.steps[i].get("enabled", True)
        self._refresh()
    def _clear(self):
        if not self.steps: return
        if messagebox.askyesno("Clear steps", f"Remove all {len(self.steps)} steps?"):
            self._save_undo(); self.steps.clear(); self._refresh()
    def _copy_other(self):
        if self.other_panel_fn:
            other = self.other_panel_fn()
            if other is not None:
                self._save_undo()
                self.steps = copy.deepcopy(other)
                self._refresh()
    def _load_template(self, tdata: dict):
        if self.steps:
            if not messagebox.askyesno("Load template",
                                       "This replaces your current steps. Continue?"):
                return
        self._save_undo()
        self.steps = copy.deepcopy(tdata["steps"])
        self._refresh()
        messagebox.showinfo("Template loaded",
            f"'{tdata['desc']}'\n\nNow edit each Click step to set correct X,Y coords.")
    def _find_replace(self):
        FindReplaceDialog(self, self.steps, self._refresh)
    def _open_full_editor(self):
        title = ("Main Flow Editor" if self.panel_id == "repeat"
                 else "First-Name Flow Editor")
        FlowEditorWindow(self.winfo_toplevel(), self, title=title)

    def load(self, steps: list):
        self._save_undo()
        self.steps = copy.deepcopy(steps)
        self._refresh()

    def get(self) -> list:
        return copy.deepcopy(self.steps)


# ── Full-size Flow Editor Window ──────────────────────────────────────────────

class FlowEditorWindow(tk.Toplevel):
    """
    Maximised standalone editor with large cards, drag-drop-replace,
    and apply-back to source FlowPanel.
    """
    CARD_H = 72

    def __init__(self, parent, flow_panel: FlowPanel, title: str = "Flow Editor"):
        super().__init__(parent)
        self.title(f"Swastik RPA  ·  {title}")
        self.configure(bg=T["bg"])
        self.state("zoomed")
        self.minsize(800, 600)
        self._panel  = flow_panel
        self._steps  = copy.deepcopy(flow_panel.steps)
        self._undo   = deque(maxlen=40)
        self._redo   = deque(maxlen=40)
        self._drag_src   = None
        self._drag_ghost = None
        self._drop_line  = None

        self._build()
        self._refresh()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Control-z>", lambda e: self.undo())
        self.bind("<Control-y>", lambda e: self.redo())
        self.bind("<Control-d>", lambda e: self._dup_last())
        self.grab_set()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        tb = tk.Frame(self, bg=T["bg2"], pady=8); tb.pack(fill="x")

        def btn(text, bg, fg, cmd, tip=""):
            b = tk.Button(tb, text=text, bg=bg, fg=fg, font=T["font_b"],
                          relief="flat", cursor="hand2", padx=10, pady=5, command=cmd)
            b.pack(side="left", padx=4)
            if tip: Tooltip(b, tip)
            return b

        btn("+ Add Step",    T["acc"],  "white",  self._add_step,   "Add a new step")
        btn("↩ Undo",        T["bg3"],  T["fg2"], self.undo,        "Ctrl+Z")
        btn("↪ Redo",        T["bg3"],  T["fg2"], self.redo,        "Ctrl+Y")
        btn("⧉ Dup Last",    T["bg3"],  T["fg2"], self._dup_last,   "Duplicate last step  (Ctrl+D)")
        btn("🔍 Find/Replace",T["bg3"], T["fg2"], self._find_replace,"Find & Replace")

        self._count_lbl = tk.Label(tb, text="", bg=T["bg2"],
                                   fg=T["fg3"], font=T["font_s"])
        self._count_lbl.pack(side="left", padx=10)
        btn("Clear All", T["bg3"], T["red"], self._clear)
        tk.Label(tb, text="≡ drag to reorder  •  drop ON card = replace  •  dbl-click = edit",
                 bg=T["bg2"], fg=T["fg3"], font=T["font_s"]).pack(side="right", padx=16)

        outer = tk.Frame(self, bg=T["bg"]); outer.pack(fill="both", expand=True)
        self._canvas = tk.Canvas(outer, bg=T["bg"], highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._canvas.bind("<MouseWheel>",
            lambda e: self._canvas.yview_scroll(-1*(e.delta//120), "units"))
        self._frame = tk.Frame(self._canvas, bg=T["bg"])
        self._win   = self._canvas.create_window((0, 0), window=self._frame, anchor="nw")
        self._frame.bind("<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
            lambda e: self._canvas.itemconfig(self._win, width=e.width))

        sb2 = tk.Frame(self, bg=T["bg2"], pady=6); sb2.pack(fill="x", side="bottom")
        tk.Button(sb2, text="✔  Apply & Close",
                  bg=T["green"], fg=T["bg"],
                  font=("Segoe UI Semibold", 10), relief="flat", cursor="hand2",
                  padx=16, pady=6, command=self._apply_close).pack(side="left", padx=12)
        tk.Button(sb2, text="Cancel", bg=T["bg3"], fg=T["fg2"],
                  font=T["font_b"], relief="flat", cursor="hand2",
                  padx=10, pady=6, command=self.destroy).pack(side="left")
        tk.Label(sb2, text="Changes apply when you click ✔ Apply & Close",
                 bg=T["bg2"], fg=T["fg3"], font=T["font_s"]).pack(side="left", padx=16)

    # ── Undo/Redo ─────────────────────────────────────────────────────────────

    def _save_undo(self):
        self._undo.append(copy.deepcopy(self._steps)); self._redo.clear()

    def undo(self):
        if not self._undo: return
        self._redo.append(copy.deepcopy(self._steps))
        self._steps = self._undo.pop(); self._refresh()

    def redo(self):
        if not self._redo: return
        self._undo.append(copy.deepcopy(self._steps))
        self._steps = self._redo.pop(); self._refresh()

    # ── Render ────────────────────────────────────────────────────────────────

    def _refresh(self):
        for w in self._frame.winfo_children(): w.destroy()
        self._drop_line = None
        n = len(self._steps)
        self._count_lbl.config(text=f"{n} step{'s' if n != 1 else ''}")

        if not self._steps:
            ef = tk.Frame(self._frame, bg=T["bg"]); ef.pack(fill="x", pady=60)
            tk.Label(ef, text="No steps yet",
                     font=("Segoe UI Semibold", 14), bg=T["bg"], fg=T["fg3"]).pack()
            tk.Label(ef, text="Click  + Add Step  to begin.",
                     font=T["font_b"], bg=T["bg"], fg=T["fg3"]).pack(pady=4)
            return

        for i, step in enumerate(self._steps):
            self._big_card(i, step)

    def _big_card(self, i: int, step: dict):
        t       = step["type"]
        enabled = step.get("enabled", True)
        color   = STEP_COLORS.get(t, T["fg2"]) if enabled else T["fg3"]
        card_bg = T["bg2"] if enabled else T["bg"]
        ico, lbl, _, _ = step_human_label(step)
        summary = step_summary(step)
        note    = step.get("note", "")

        if i > 0:
            af = tk.Frame(self._frame, bg=T["bg"], height=10); af.pack(fill="x")
            tk.Label(af, text="↓", bg=T["bg"],
                     fg=T["fg3"], font=("Segoe UI", 9)).pack()

        wrapper = tk.Frame(self._frame, bg=T["bg"])
        wrapper.pack(fill="x", padx=16, pady=1)
        wrapper._step_index = i

        card = tk.Frame(wrapper, bg=card_bg, height=self.CARD_H, relief="flat")
        card.pack(fill="x"); card.pack_propagate(False)

        tk.Frame(card, bg=color, width=8).pack(side="left", fill="y")

        handle = tk.Label(card, text="≡", bg=T["bg3"], fg=T["fg3"],
                          font=("Segoe UI", 16), padx=14, cursor="fleur", width=2)
        handle.pack(side="left", fill="y")
        Tooltip(handle, "Drag to reorder  •  drop ON another card to swap")

        body = tk.Frame(card, bg=card_bg)
        body.pack(side="left", fill="both", expand=True, padx=14, pady=10)

        row1 = tk.Frame(body, bg=card_bg); row1.pack(fill="x")
        tk.Label(row1, text=f"{i+1}.", width=4, bg=card_bg,
                 fg=T["fg3"] if enabled else T["bg4"],
                 font=T["font_b"]).pack(side="left")
        lbl_text = f"⊘ {lbl}" if not enabled else f"{ico}  {lbl}"
        tk.Label(row1, text=lbl_text, bg=card_bg, fg=color,
                 font=("Segoe UI Semibold", 11)).pack(side="left", padx=4)
        if summary:
            tk.Label(row1, text=summary, bg=card_bg,
                     fg=T["fg2"] if enabled else T["fg3"],
                     font=("Consolas", 10)).pack(side="left", padx=10)

        if note:
            row2 = tk.Frame(body, bg=card_bg); row2.pack(fill="x")
            tk.Label(row2, text=f"// {note}", bg=card_bg,
                     fg=T["fg3"], font=T["font_s"]).pack(side="left", padx=28)

        acts = tk.Frame(card, bg=card_bg); acts.pack(side="right", padx=10)
        eye_txt = "👁" if enabled else "🚫"
        for txt, tip, cmd in [
            (eye_txt, "Toggle enabled",  lambda i=i: self._toggle_enabled(i)),
            ("✏",     "Edit",            lambda i=i: self._edit(i)),
            ("⧉",     "Duplicate",       lambda i=i: self._dup(i)),
            ("▲",     "Move up",         lambda i=i: self._mv(i, -1)),
            ("▼",     "Move down",       lambda i=i: self._mv(i,  1)),
            ("✕",     "Delete",          lambda i=i: self._del(i)),
        ]:
            b = tk.Button(acts, text=txt, bg=card_bg, fg=T["fg3"],
                          font=("Segoe UI", 10), relief="flat", cursor="hand2",
                          padx=6, activebackground=T["bg3"], command=cmd)
            b.pack(side="left", pady=8)
            Tooltip(b, tip)

        all_bg = [card, body, acts, row1]

        def _enter(e):
            if not step.get("enabled", True): return
            for w in all_bg: w.configure(bg=T["bg3"])
            for ch in row1.winfo_children(): ch.configure(bg=T["bg3"])
            for ch in acts.winfo_children():
                if isinstance(ch, tk.Button): ch.configure(bg=T["bg3"])

        def _leave(e):
            if not step.get("enabled", True): return
            for w in all_bg: w.configure(bg=T["bg2"])
            for ch in row1.winfo_children(): ch.configure(bg=T["bg2"])
            for ch in acts.winfo_children():
                if isinstance(ch, tk.Button): ch.configure(bg=T["bg2"])

        for w in (card, body):
            w.bind("<Enter>", _enter); w.bind("<Leave>", _leave)
        for w in (card, body, row1):
            w.bind("<Double-Button-1>", lambda e, idx=i: self._edit(idx))

        handle.bind("<ButtonPress-1>",   lambda e, idx=i: self._drag_start(e, idx))
        handle.bind("<B1-Motion>",       lambda e, idx=i: self._drag_motion(e, idx))
        handle.bind("<ButtonRelease-1>", lambda e, idx=i: self._drag_end(e, idx))

    # ── Drag-drop-replace ─────────────────────────────────────────────────────

    def _drag_start(self, event, idx: int):
        self._drag_src = idx
        step  = self._steps[idx]
        ico, lbl, _, _ = step_human_label(step)
        color = STEP_COLORS.get(step["type"], T["fg2"])
        g = tk.Toplevel(self); g.overrideredirect(True)
        g.attributes("-alpha", 0.85); g.attributes("-topmost", True)
        gf = tk.Frame(g, bg=color); gf.pack()
        tk.Label(gf, text=f"  {ico}  {lbl}  ",
                 bg=color, fg="white",
                 font=("Segoe UI Semibold", 10), padx=14, pady=8).pack()
        self._drag_ghost = g
        self._drag_motion(event, idx)

    def _drag_motion(self, event, idx: int):
        if self._drag_ghost:
            rx = event.widget.winfo_rootx() + event.x + 12
            ry = event.widget.winfo_rooty() + event.y + 12
            self._drag_ghost.geometry(f"+{rx}+{ry}")
        cy  = self._canvas.canvasy(
            event.widget.winfo_rooty() + event.y - self._canvas.winfo_rooty())
        tgt = self._y_to_index(cy)
        self._show_drop_indicator(tgt)

    def _drag_end(self, event, idx: int):
        if self._drag_ghost:
            try: self._drag_ghost.destroy()
            except Exception: pass
            self._drag_ghost = None
        if self._drop_line:
            try: self._drop_line.destroy()
            except Exception: pass
            self._drop_line = None

        cy  = self._canvas.canvasy(
            event.widget.winfo_rooty() + event.y - self._canvas.winfo_rooty())
        tgt = self._y_to_index(cy)
        src = self._drag_src; self._drag_src = None

        if src is None or tgt is None: return
        tgt = max(0, min(tgt, len(self._steps) - 1))
        if src == tgt: return

        self._save_undo()
        self._steps[src], self._steps[tgt] = self._steps[tgt], self._steps[src]
        self._refresh()

    def _y_to_index(self, canvas_y: float) -> int:
        children = [w for w in self._frame.winfo_children() if hasattr(w, "_step_index")]
        if not children: return 0
        for w in children:
            mid = w.winfo_y() + w.winfo_height() / 2
            if canvas_y < mid:
                return w._step_index
        return children[-1]._step_index

    def _show_drop_indicator(self, tgt_idx: int):
        if self._drop_line:
            try: self._drop_line.destroy()
            except Exception: pass
            self._drop_line = None
        children = [w for w in self._frame.winfo_children() if hasattr(w, "_step_index")]
        tgt_w = next((w for w in children if w._step_index == tgt_idx), None)
        if not tgt_w: return
        overlay = tk.Frame(self._frame, bg=T["red"], height=4)
        overlay.place(in_=tgt_w, relx=0, rely=0, relwidth=1)
        self._drop_line = overlay

    # ── Step actions ──────────────────────────────────────────────────────────

    def _add_step(self):
        def on_pick(t):
            d = {"type": t, **copy.deepcopy(STEP_DEFAULTS[t])}
            StepEditor(self, step=d, on_save=self._append)
        StepPickerDialog(self, on_pick)

    def _append(self, s):   self._save_undo(); self._steps.append(s);            self._refresh()
    def _edit(self, i):     StepEditor(self, step=self._steps[i],
                                       on_save=lambda s, i=i: self._replace(i, s))
    def _replace(self, i, s): self._save_undo(); self._steps[i] = s;             self._refresh()
    def _del(self, i):      self._save_undo(); self._steps.pop(i);               self._refresh()
    def _dup(self, i):
        self._save_undo()
        self._steps.insert(i+1, copy.deepcopy(self._steps[i]))
        self._refresh()
    def _dup_last(self):
        if self._steps: self._dup(len(self._steps) - 1)
    def _mv(self, i, d):
        j = i + d
        if 0 <= j < len(self._steps):
            self._save_undo()
            self._steps[i], self._steps[j] = self._steps[j], self._steps[i]
            self._refresh()
    def _toggle_enabled(self, i):
        self._save_undo()
        self._steps[i]["enabled"] = not self._steps[i].get("enabled", True)
        self._refresh()
    def _clear(self):
        if not self._steps: return
        if messagebox.askyesno("Clear steps", f"Remove all {len(self._steps)} steps?"):
            self._save_undo(); self._steps.clear(); self._refresh()
    def _find_replace(self):
        FindReplaceDialog(self, self._steps, self._refresh)

    def _apply_close(self):
        self._panel._save_undo()
        self._panel.steps = copy.deepcopy(self._steps)
        self._panel._refresh()
        self.destroy()

    def _on_close(self):
        if self._steps != self._panel.steps:
            if messagebox.askyesno("Discard changes?",
                                   "You have unsaved changes.\nClose without applying?"):
                self.destroy()
        else:
            self.destroy()


# ── Name list panel ───────────────────────────────────────────────────────────

class NameListPanel(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=T["bg"], **kw)
        self._names  = []
        self._recent = load_json_file(RECENT_FILE, [])
        self._build()

    def _build(self):
        tk.Label(self, text=L("paste_names"),
                 bg=T["bg"], fg=T["fg2"], font=T["font_b"]
                 ).pack(anchor="w", pady=(0, 4))

        tf = tk.Frame(self, bg=T["bg"]); tf.pack(fill="both", expand=True)
        self._text = tk.Text(tf, width=36, height=12,
                             bg=T["bg3"], fg=T["fg"],
                             insertbackground=T["fg"], font=T["font_m"],
                             relief="flat", padx=8, pady=6)
        tsb = ttk.Scrollbar(tf, orient="vertical", command=self._text.yview)
        self._text.configure(yscrollcommand=tsb.set)
        tsb.pack(side="right", fill="y")
        self._text.pack(side="left", fill="both", expand=True)
        self._text.bind("<KeyRelease>", lambda e: self._sync_from_text())

        br = tk.Frame(self, bg=T["bg"]); br.pack(fill="x", pady=8)
        tk.Button(br, text=L("browse"),
                  bg=T["acc"], fg="white",
                  font=T["font_b"], relief="flat", cursor="hand2",
                  padx=8, pady=4, command=self._browse).pack(side="left")
        tk.Button(br, text="Clear",
                  bg=T["bg3"], fg=T["fg2"],
                  font=T["font_s"], relief="flat", cursor="hand2",
                  padx=6, command=self._clear).pack(side="left", padx=6)
        self._count_lbl = tk.Label(br, text="", bg=T["bg"],
                                   fg=T["green"],
                                   font=("Segoe UI Semibold", 9))
        self._count_lbl.pack(side="left", padx=4)

        # Recent files row (rebuilt dynamically)
        self._recent_frame = tk.Frame(self, bg=T["bg"])
        self._recent_frame.pack(fill="x", pady=(0, 4))
        self._build_recent_row()

        tk.Label(self,
                 text=("Tip: {name} in your steps is replaced with each name from this list.\n"
                       "You can also use {varname} for custom variables (define in Variables)."),
                 bg=T["bg"], fg=T["fg3"], font=T["font_s"],
                 justify="left").pack(anchor="w", pady=(4, 0))

    def _build_recent_row(self):
        for w in self._recent_frame.winfo_children(): w.destroy()
        if not self._recent: return
        tk.Label(self._recent_frame, text="Recent:", bg=T["bg"],
                 fg=T["fg3"], font=T["font_s"]).pack(side="left")
        for path in self._recent[:5]:
            tk.Button(self._recent_frame, text=os.path.basename(path),
                      bg=T["bg"], fg=T["acc"], font=T["font_s"],
                      relief="flat", cursor="hand2",
                      command=lambda p=path: self._load_file(p)
                      ).pack(side="left", padx=4)

    def _sync_from_text(self):
        raw = self._text.get("1.0", "end-1c")
        self._names = [n.strip() for n in raw.splitlines() if n.strip()]
        self._count_lbl.config(
            text=(f"✔ {len(self._names)} {'name' if len(self._names)==1 else 'names'}"
                  if self._names else ""))

    def _browse(self):
        path = filedialog.askopenfilename(
            filetypes=[("Excel / CSV", "*.xlsx *.xls *.csv"), ("All", "*.*")])
        if path:
            self._load_file(path)

    def _load_file(self, path: str):
        try:
            ext = os.path.splitext(path)[1].lower()
            if ext in (".xlsx", ".xls"):
                df = pd.read_excel(path, dtype=str)
            elif ext == ".csv":
                df = pd.read_csv(path, dtype=str)
            else:
                raise ValueError(f"Unsupported file type: {ext}")
            df.dropna(how="all", inplace=True)
            cols = list(df.columns); col = cols[0]
            if len(cols) > 1:
                from .dialogs import ColumnChooser
                dlg = ColumnChooser(self, cols)
                self.wait_window(dlg)
                if dlg.chosen:
                    col = dlg.chosen
            names = [n.strip() for n in df[col].dropna().astype(str) if n.strip()]
            self._text.delete("1.0", "end")
            self._text.insert("1.0", "\n".join(names))
            self._sync_from_text()
            # Update recent list
            if path in self._recent: self._recent.remove(path)
            self._recent.insert(0, path)
            self._recent = self._recent[:5]
            save_json_file(RECENT_FILE, self._recent)
            self._build_recent_row()
        except Exception as e:
            messagebox.showerror("Load Error", str(e))

    def _clear(self):
        self._text.delete("1.0", "end")
        self._names = []
        self._count_lbl.config(text="")

    def get_names(self) -> list:
        return list(self._names)


# ── Run status panel ──────────────────────────────────────────────────────────

class RunStatusPanel(tk.Frame):
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=T["bg"], **kw)
        self._build()
        # Callbacks set by App
        self.on_start_cb       = None
        self.on_pause_cb       = None
        self.on_stop_cb        = None
        self.on_test_single_cb = None

    def _build(self):
        cr = tk.Frame(self, bg=T["bg"]); cr.pack(fill="x", pady=(0, 10))

        self._run_btn = tk.Button(cr, text=L("start"),
                                  bg=T["green"], fg=T["bg"],
                                  font=("Segoe UI Semibold", 12),
                                  relief="flat", cursor="hand2",
                                  padx=20, pady=10,
                                  command=lambda: self.on_start_cb and self.on_start_cb())
        self._run_btn.pack(side="left")
        Tooltip(self._run_btn, "Start running your flow for all names. F10 = stop.")

        self._pause_btn = tk.Button(cr, text=L("pause"),
                                    bg=T["yellow_bg"], fg=T["yellow"],
                                    font=("Segoe UI Semibold", 9),
                                    relief="flat", cursor="hand2",
                                    padx=14, pady=10, state="disabled",
                                    command=lambda: self.on_pause_cb and self.on_pause_cb())
        self._pause_btn.pack(side="left", padx=8)

        self._stop_btn = tk.Button(cr, text=L("stop"),
                                   bg=T["red_bg"], fg=T["red"],
                                   font=("Segoe UI Semibold", 9),
                                   relief="flat", cursor="hand2",
                                   padx=14, pady=10, state="disabled",
                                   command=lambda: self.on_stop_cb and self.on_stop_cb())
        self._stop_btn.pack(side="left")

        self._timer_lbl = tk.Label(cr, text="", bg=T["bg"],
                                   fg=T["fg3"], font=T["font_s"])
        self._timer_lbl.pack(side="left", padx=10)
        self._eta_lbl = tk.Label(cr, text="", bg=T["bg"],
                                 fg=T["cyan"], font=T["font_s"])
        self._eta_lbl.pack(side="left", padx=4)
        self._status_lbl = tk.Label(cr, text=L("ready"), bg=T["bg"],
                                    fg=T["fg2"], font=("Segoe UI", 9, "italic"))
        self._status_lbl.pack(side="left", padx=8)

        # Test single name
        ts = tk.Frame(self, bg=T["bg"]); ts.pack(fill="x", pady=(0, 8))
        tk.Label(ts, text=L("test_single") + ":",
                 bg=T["bg"], fg=T["fg3"], font=T["font_s"]).pack(side="left")
        self._test_var = tk.StringVar()
        tk.Entry(ts, textvariable=self._test_var, width=18,
                 bg=T["bg3"], fg=T["fg"], insertbackground=T["fg"],
                 font=T["font_m"], relief="flat").pack(side="left", padx=8)
        tb = tk.Button(ts, text="▶ Run", bg=T["bg3"], fg=T["fg2"],
                       font=T["font_s"], relief="flat", cursor="hand2",
                       command=self._on_test_single)
        tb.pack(side="left")
        Tooltip(tb, "Test your flow with this single name")

        # Progress
        self._progress = ttk.Progressbar(self, orient="horizontal", mode="determinate")
        self._progress.pack(fill="x", pady=(0, 10))

        # Settings (collapsible)
        self._settings_expanded = False
        self._settings_btn = tk.Button(self, text="⚙  Settings  ▾",
                                       bg=T["bg2"], fg=T["fg2"],
                                       font=T["font_s"], relief="flat",
                                       cursor="hand2", anchor="w",
                                       command=self._toggle_settings)
        self._settings_btn.pack(fill="x", pady=(0, 2))
        self._settings_frame = tk.Frame(self, bg=T["bg2"])
        self._build_settings()

        # Log
        lhdr = tk.Frame(self, bg=T["bg"]); lhdr.pack(fill="x", pady=(8, 0))
        tk.Label(lhdr, text="Log", bg=T["bg"], fg=T["fg2"],
                 font=("Segoe UI Semibold", 9)).pack(side="left")
        for txt, cmd in [("Clear", self._clear_log), ("Export", self._export_log)]:
            tk.Button(lhdr, text=txt, bg=T["bg"], fg=T["fg3"],
                      font=T["font_s"], relief="flat", cursor="hand2",
                      command=cmd).pack(side="right", padx=4)

        self._log_box = tk.Text(self, height=12, bg="#0a0e14", fg=T["fg2"],
                                font=("Consolas", 8), state="disabled",
                                relief="flat", padx=8, pady=6)
        self._log_box.pack(fill="both", expand=True, pady=(4, 0))
        self._log_box.tag_config("ok",   foreground=T["green"])
        self._log_box.tag_config("err",  foreground=T["red"])
        self._log_box.tag_config("warn", foreground=T["yellow"])
        self._log_box.tag_config("dim",  foreground=T["fg3"])
        self._log_box.tag_config("head", foreground=T["acc"])

    def _build_settings(self):
        sf = self._settings_frame
        r1 = tk.Frame(sf, bg=T["bg2"]); r1.pack(fill="x", padx=12, pady=8)
        self._svars = {}
        defs = [
            ("countdown", L("countdown_lbl"), str(_prefs["countdown"]),
             "Seconds before automation starts"),
            ("between",   L("between"),       str(_prefs["between"]),
             "Seconds to wait after each name"),
            ("retries",   L("retries"),       str(_prefs["retries"]),
             "How many times to retry a failed name (0 = no retry)"),
        ]
        for key, lbl, dflt, tip in defs:
            fc = tk.Frame(r1, bg=T["bg2"]); fc.pack(side="left", padx=12)
            tk.Label(fc, text=lbl, bg=T["bg2"], fg=T["fg2"],
                     font=T["font_s"]).pack(anchor="w")
            v = tk.StringVar(value=dflt); self._svars[key] = v
            e = tk.Entry(fc, textvariable=v, width=6, bg=T["bg3"],
                         fg=T["yellow"], insertbackground=T["fg"],
                         font=T["font_m"], relief="flat")
            e.pack(anchor="w", pady=2)
            v.trace_add("write", lambda *a, k=key, var=v: self._pref_changed(k, var))
            Tooltip(e, tip)

        self._dry_run = tk.BooleanVar(value=_prefs["dry_run"])
        self._fail_ss = tk.BooleanVar(value=_prefs["fail_ss"])
        for var, txt, tip, key in [
            (self._dry_run, L("dry_run"),         "Log steps without executing", "dry_run"),
            (self._fail_ss, "Screenshot on fail", "Capture screenshot on name failure","fail_ss"),
        ]:
            cb = tk.Checkbutton(r1, text=txt, variable=var,
                                bg=T["bg2"], fg=T["fg2"], selectcolor=T["bg3"],
                                font=T["font_s"], activebackground=T["bg2"],
                                command=lambda k=key, v=var: self._pref_bool(k, v))
            cb.pack(side="left", padx=10)
            Tooltip(cb, tip)

        tk.Label(sf,
                 text="F10 = Stop instantly   F11 = Pause / Resume",
                 bg=T["bg2"], fg=T["fg3"], font=T["font_s"]
                 ).pack(padx=12, pady=(0, 8), anchor="w")

    def _pref_changed(self, key: str, var):
        try:
            val = var.get()
            if key == "between": _prefs[key] = float(val or 0)
            else:                _prefs[key] = int(float(val or 0))
            from core.constants import save_prefs
            save_prefs()
        except Exception:
            pass

    def _pref_bool(self, key: str, var):
        _prefs[key] = var.get()
        from core.constants import save_prefs
        save_prefs()

    def _toggle_settings(self):
        self._settings_expanded = not self._settings_expanded
        if self._settings_expanded:
            self._settings_frame.pack(fill="x", after=self._settings_btn, pady=(0, 8))
            self._settings_btn.config(text="⚙  Settings  ▴")
        else:
            self._settings_frame.pack_forget()
            self._settings_btn.config(text="⚙  Settings  ▾")

    def get_settings(self) -> dict:
        return {
            "countdown": int(float(self._svars["countdown"].get() or 5)),
            "between":   float(self._svars["between"].get() or 1.0),
            "retries":   int(float(self._svars.get("retries",
                             tk.StringVar(value="0")).get() or 0)),
            "dry_run":   self._dry_run.get(),
            "fail_ss":   self._fail_ss.get(),
        }

    # ── Running state ─────────────────────────────────────────────────────────

    def set_running(self, running: bool, total: int = 0):
        if running:
            self._run_btn.config(state="disabled")
            self._pause_btn.config(state="normal", text=L("pause"))
            self._stop_btn.config(state="normal")
            self._progress.config(maximum=max(total, 1), value=0)
            self._status_lbl.config(text=L("running"), fg=T["yellow"])
        else:
            self._run_btn.config(state="normal")
            self._pause_btn.config(state="disabled")
            self._stop_btn.config(state="disabled")
            self._status_lbl.config(text=L("ready"), fg=T["fg2"])
            self._eta_lbl.config(text="")

    def update_progress(self, i: int, total: int, name: str):
        self._progress.config(value=i)
        self._status_lbl.config(text=f"{L('running')} [{i}/{total}]  {name}")

    def update_name_status(self, name: str, ok: bool):
        self.log(("  ✔  " if ok else "  ✘  ") + name, "ok" if ok else "err")

    def set_timer(self, text: str):  self._timer_lbl.config(text=text)
    def set_eta(self, text: str):    self._eta_lbl.config(text=text)

    def set_done(self, s: int, f: list, elapsed: float):
        self._status_lbl.config(
            text=f"{L('done')}  ✔{s}  ✘{len(f)}  ⏱{elapsed:.0f}s",
            fg=T["green"] if not f else T["yellow"])

    def toggle_pause_label(self, is_paused: bool):
        self._pause_btn.config(text=L("resume") if is_paused else L("pause"))

    # ── Log ───────────────────────────────────────────────────────────────────

    def log(self, msg: str, tag: str = None):
        def _do():
            self._log_box.config(state="normal")
            if not tag:
                t = None
                if "✔" in msg or "Done" in msg or "succeeded" in msg:  t = "ok"
                elif "✘" in msg or "failed" in msg.lower():            t = "err"
                elif "⚠" in msg or "⏸" in msg or "Practice" in msg:   t = "warn"
                elif msg.startswith("  ") or msg.startswith("   "):    t = "dim"
                elif "[" in msg and "/" in msg:                         t = "head"
            else:
                t = tag
            near_bottom = self._log_box.yview()[1] > 0.90
            self._log_box.insert("end", msg + "\n", t or "")
            if near_bottom:
                self._log_box.see("end")
            self._log_box.config(state="disabled")
        try:
            self.after(0, _do)
        except Exception:
            pass

    def _clear_log(self):
        self._log_box.config(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.config(state="disabled")

    def _export_log(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=f"swastik_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if not path: return
        content = self._log_box.get("1.0", "end")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        self.log(f"Log exported → {os.path.basename(path)}", "ok")

    def _on_test_single(self):
        if self.on_test_single_cb:
            self.on_test_single_cb(self._test_var.get().strip())
