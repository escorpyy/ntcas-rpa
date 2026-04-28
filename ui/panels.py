"""
ui/panels.py  — v10.0 / Excel-style grid editor
================================================
NEW in v10.0 — FlowEditorWindow completely rebuilt as an Excel-like Treeview grid:
  • Sortable columns: #, Enabled, Type, Summary, Note  (click header to sort, click again to reverse)
  • Multi-row selection: click, Ctrl+click, Shift+click range, header checkbox = select-all
  • Cut / Copy / Paste rows  (toolbar + Ctrl+X/C/V)
  • Move Up / Down / To Top / To Bottom for selected rows
  • In-place Find & Replace panel (all text fields)
  • Per-column width resizing via ttk column stretch
  • Double-click any row to open StepEditor
  • Right-click context menu: Edit, Duplicate, Toggle, Cut, Copy, Paste, Delete
  • Keyboard: Del = delete, ↑↓ = move, Ctrl+Z/Y = undo/redo, Ctrl+A = select-all
  • Status bar: total steps, selection count, clipboard info, sort state
  • FlowPanel toolbar gains: Grid View button (opens FlowEditorWindow), Cut/Copy/Paste

All v9.5 scrollbar fixes are preserved unchanged.
"""

import copy, datetime, os, queue, random, time
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

    _SCROLL_ZONE  = 40
    _SCROLL_DELAY = 32

    def __init__(self, parent, panel_id: str = "main", other_panel_fn=None, **kw):
        super().__init__(parent, bg=T["bg"], **kw)
        self.panel_id       = panel_id
        self.other_panel_fn = other_panel_fn
        self.steps: list    = []
        self._undo          = deque(maxlen=self.MAX_UNDO)
        self._redo          = deque(maxlen=self.MAX_UNDO)
        self._clipboard: list = []
        self._cut_mode: bool  = False
        self._drag_src      = None
        self._drag_ghost    = None
        self._drop_line     = None
        self._drag_tgt      = None
        self._autoscroll_id = None
        self._autoscroll_speed = 0.0
        self._build()

    # ── Undo / Redo ───────────────────────────────────────────────────────────

    def _save_undo(self):
        self._undo.append(copy.deepcopy(self.steps))
        self._redo.clear()

    def undo(self):
        if not self._undo: return
        self._redo.append(copy.deepcopy(self.steps))
        self.steps = self._undo.pop()
        self._refresh()

    def redo(self):
        if not self._redo: return
        self._undo.append(copy.deepcopy(self.steps))
        self.steps = self._redo.pop()
        self._refresh()

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
        btn("✂ Cut",           T["bg3"],  T["fg2"],    self._cut_selected,  "Cut selected steps")
        btn("⧉ Copy",          T["bg3"],  T["fg2"],    self._copy_selected, "Copy selected steps")
        btn("📋 Paste",        T["bg3"],  T["fg2"],    self._paste_steps,   "Paste steps")
        btn("🔍 Find/Replace", T["bg3"],  T["fg2"],    self._find_replace,  "Find & Replace")
        btn("⧉ Copy Other",    T["bg3"],  T["fg2"],    self._copy_other,    "Copy steps from the other panel")
        btn("⊞ Grid Editor",   T["bg3"],  T["purple"], self._open_full_editor,
            "Open Excel-style grid editor")

        self._count_lbl = tk.Label(tb, text="", bg=T["bg"],
                                   fg=T["fg3"], font=T["font_s"])
        self._count_lbl.pack(side="right", padx=6)
        btn(L("clear_all"), T["bg3"], T["red"], self._clear, "Remove all steps", side="right")

        # ── Templates row — horizontal scrollable ─────────────────────────────
        tmpl_outer = tk.Frame(self, bg=T["bg2"]); tmpl_outer.pack(fill="x", pady=(0, 4))
        tk.Label(tmpl_outer, text="Templates:", bg=T["bg2"], fg=T["fg3"],
                 font=T["font_s"]).pack(side="left", padx=8)

        tmpl_canvas = tk.Canvas(tmpl_outer, bg=T["bg2"], height=32,
                                highlightthickness=0)
        tmpl_hsb = ttk.Scrollbar(tmpl_outer, orient="horizontal",
                                 command=tmpl_canvas.xview)
        tmpl_canvas.configure(xscrollcommand=tmpl_hsb.set)

        tmpl_inner = tk.Frame(tmpl_canvas, bg=T["bg2"])
        tmpl_canvas.create_window((0, 0), window=tmpl_inner, anchor="nw")
        tmpl_inner.bind("<Configure>",
            lambda e: tmpl_canvas.configure(scrollregion=tmpl_canvas.bbox("all")))

        for name, tdata in TEMPLATES.items():
            tk.Button(tmpl_inner, text=f"{tdata['icon']} {name}",
                      bg=T["bg3"], fg=T["fg2"], font=T["font_s"],
                      relief="flat", cursor="hand2", padx=6, pady=2,
                      command=lambda d=tdata: self._load_template(d)
                      ).pack(side="left", padx=2, pady=3)

        tmpl_canvas.pack(side="left", fill="x", expand=True)
        # Only show horizontal scrollbar when content overflows
        tmpl_inner.update_idletasks()
        tmpl_canvas.bind("<Configure>",
            lambda e, c=tmpl_canvas, i=tmpl_inner:
                tmpl_hsb.pack(fill="x") if i.winfo_reqwidth() > e.width
                else tmpl_hsb.pack_forget())

        # Mouse-wheel horizontal scroll on template row
        tmpl_canvas.bind("<Shift-MouseWheel>",
            lambda e: tmpl_canvas.xview_scroll(-1*(e.delta//120), "units"))

        # Scrollable canvas — vertical + horizontal
        outer = tk.Frame(self, bg=T["bg"]); outer.pack(fill="both", expand=True)
        self._canvas = tk.Canvas(outer, bg=T["bg"], highlightthickness=0, height=420)
        vsb = ttk.Scrollbar(outer, orient="vertical",   command=self._canvas.yview)
        hsb = ttk.Scrollbar(outer, orient="horizontal", command=self._canvas.xview)
        self._canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._frame = tk.Frame(self._canvas, bg=T["bg"])
        self._win   = self._canvas.create_window((0, 0), window=self._frame, anchor="nw")
        self._frame.bind("<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>", lambda e, c=self._canvas, w=self._win: c.itemconfig(w, width=e.width))
        self._canvas.bind("<MouseWheel>", lambda e: self._canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        self._canvas.bind("<Shift-MouseWheel>", lambda e: self._canvas.xview_scroll(-1*(e.delta//120), "units"))
        self._frame.bind("<MouseWheel>", lambda e: self._canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        self._refresh()

    # ── Render ────────────────────────────────────────────────────────────────

    def _refresh(self):
        self._stop_autoscroll()

        if self._drop_line:
            try: self._drop_line.destroy()
            except Exception: pass
            self._drop_line = None

        if self._drag_ghost:
            try: self._drag_ghost.destroy()
            except Exception: pass
            self._drag_ghost = None

        self._drag_src  = None
        self._drag_tgt  = None

        for w in self._frame.winfo_children():
            try: w.destroy()
            except Exception: pass

        query = self._search.get().lower().strip() if hasattr(self, "_search") else ""
        n     = len(self.steps)

        if _prefs.get("show_step_count", True):
            self._count_lbl.config(text=f"{n} step{'s' if n != 1 else ''}")
        else:
            self._count_lbl.config(text="")

        if not self.steps:
            ef = tk.Frame(self._frame, bg=T["bg"]); ef.pack(fill="x", pady=30)
            tk.Label(ef, text="No steps yet",
                     font=("Segoe UI Semibold", 11), bg=T["bg"], fg=T["fg3"]).pack()
            tk.Label(ef, text="Click  + Add Step  or pick a template above.",
                     font=T["font_s"], bg=T["bg"], fg=T["fg3"]).pack(pady=4)
            return

        visible = [(i, s) for i, s in enumerate(self.steps)
                   if not query
                   or query in STEP_FRIENDLY.get(s.get("type",""), ("","",""))[0].lower()
                   or query in step_summary(s).lower()
                   or query in s.get("note", "").lower()
                   or query in s.get("type", "").lower()]

        if query and not visible:
            tk.Label(self._frame, text=f'No steps match "{query}"',
                     bg=T["bg"], fg=T["fg3"], font=T["font_s"]).pack(pady=12)
            return

        for i, step in visible:
            self._step_card(i, step)

    def _step_card(self, i: int, step: dict):
        t       = step.get("type", "comment")
        enabled = step.get("enabled", True)
        color   = STEP_COLORS.get(t, T["fg2"]) if enabled else T["fg3"]
        card_bg = T["bg2"] if enabled else T["bg"]

        ico, lbl, summary, _ = step_human_label(step)
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

        def _enter(e, hover_bg=T["bg3"], nbg=card_bg):
            if not step.get("enabled", True): return
            for w in all_bg: w.configure(bg=hover_bg)
            for ch in top.winfo_children():  ch.configure(bg=hover_bg)
            for ch in acts.winfo_children():
                if isinstance(ch, tk.Button): ch.configure(bg=hover_bg)

        def _leave(e, hover_bg=T["bg3"], nbg=card_bg):
            if not step.get("enabled", True): return
            for w in all_bg: w.configure(bg=nbg)
            for ch in top.winfo_children():  ch.configure(bg=nbg)
            for ch in acts.winfo_children():
                if isinstance(ch, tk.Button): ch.configure(bg=nbg)

        # Bind mousewheel on cards so scrolling still works
        for w in (card, body, top, acts):
            w.bind("<MouseWheel>",
                lambda e: self._canvas.yview_scroll(-1*(e.delta//120), "units"))
            w.bind("<Enter>", _enter)
            w.bind("<Leave>", _leave)
        for w in (card, body, top):
            w.bind("<Double-Button-1>", lambda e, idx=i: self._edit(idx))

        handle.bind("<ButtonPress-1>",   lambda e, idx=i: self._drag_start(e, idx))
        handle.bind("<B1-Motion>",       lambda e, idx=i: self._drag_motion(e, idx))
        handle.bind("<ButtonRelease-1>", lambda e, idx=i: self._drag_end(e, idx))

    # ── Drag reorder ──────────────────────────────────────────────────────────

    def _drag_start(self, event, idx: int):
        self._drag_src = idx
        self._drag_tgt = idx
        step  = self.steps[idx]
        ico, lbl, _, _ = step_human_label(step)
        color = STEP_COLORS.get(step.get("type",""), T["fg2"])
        g = tk.Toplevel(self); g.overrideredirect(True)
        g.attributes("-alpha", 0.80); g.attributes("-topmost", True)
        gf = tk.Frame(g, bg=color); gf.pack()
        tk.Label(gf, text=f"  {ico} {lbl}  ", bg=color, fg="white",
                 font=("Segoe UI Semibold", 9), padx=10, pady=6).pack()
        self._drag_ghost = g
        self._drag_motion(event, idx)

    def _drag_motion(self, event, idx: int):
        if self._drag_ghost:
            try:
                rx = event.widget.winfo_rootx() + event.x + 12
                ry = event.widget.winfo_rooty() + event.y + 12
                self._drag_ghost.geometry(f"+{rx}+{ry}")
            except Exception:
                pass

        try:
            widget_root_y = event.widget.winfo_rooty()
            canvas_root_y = self._canvas.winfo_rooty()
            canvas_h      = self._canvas.winfo_height()
            cursor_canvas_y_abs = widget_root_y + event.y - canvas_root_y

            self._start_autoscroll(cursor_canvas_y_abs, canvas_h)

            cy  = self._canvas.canvasy(cursor_canvas_y_abs)
            tgt = self._y_to_step_index(cy)
            if tgt != self._drag_tgt:
                self._drag_tgt = tgt
                self._show_drop_indicator(tgt)
        except Exception:
            pass

    def _drag_end(self, event, idx: int):
        self._stop_autoscroll()

        if self._drag_ghost:
            try: self._drag_ghost.destroy()
            except Exception: pass
            self._drag_ghost = None
        if self._drop_line:
            try: self._drop_line.destroy()
            except Exception: pass
            self._drop_line = None

        tgt = self._drag_tgt
        src = self._drag_src
        self._drag_src = None
        self._drag_tgt = None

        if src is None or tgt is None: return
        tgt = max(0, min(tgt, len(self.steps) - 1))
        if src == tgt: return

        self._save_undo()
        step = self.steps.pop(src)
        self.steps.insert(tgt, step)
        self._refresh()

    # ── Autoscroll helpers ────────────────────────────────────────────────────

    def _start_autoscroll(self, cursor_y_in_viewport: float, canvas_h: float):
        zone  = self._SCROLL_ZONE
        speed = 0.0

        if cursor_y_in_viewport < zone and cursor_y_in_viewport >= 0:
            ratio = 1.0 - (cursor_y_in_viewport / zone)
            speed = -max(0.2, ratio * 1.0)
        elif cursor_y_in_viewport > canvas_h - zone and cursor_y_in_viewport <= canvas_h:
            ratio = (cursor_y_in_viewport - (canvas_h - zone)) / zone
            speed = max(0.2, ratio * 1.0)

        if speed == 0.0:
            self._stop_autoscroll()
            return

        self._autoscroll_speed = speed
        if self._autoscroll_id is None:
            self._autoscroll_loop()

    def _autoscroll_loop(self):
        spd = self._autoscroll_speed
        if spd == 0.0:
            self._autoscroll_id = None
            return
        try:
            self._canvas.yview_scroll(int(spd) or (1 if spd > 0 else -1), "units")
        except Exception:
            pass
        self._autoscroll_id = self.after(self._SCROLL_DELAY, self._autoscroll_loop)

    def _stop_autoscroll(self):
        if self._autoscroll_id:
            try: self.after_cancel(self._autoscroll_id)
            except Exception: pass
            self._autoscroll_id = None
        self._autoscroll_speed = 0.0

    # ── Drop indicator ────────────────────────────────────────────────────────

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
            d = {"type": t, **copy.deepcopy(STEP_DEFAULTS.get(t, {}))}
            StepEditor(self, step=d, on_save=self._append)
        StepPickerDialog(self, on_pick)

    def _append(self, s: dict):
        self._save_undo()
        auto_wait      = s.pop("auto_wait", False)
        auto_wait_secs = s.pop("auto_wait_secs", 1.0)
        self.steps.append(s)
        if auto_wait:
            self.steps.append({"type": "wait", "seconds": float(auto_wait_secs),
                                "note": "auto", "enabled": True})
        self._refresh()
        self.after(50, lambda: self._canvas.yview_moveto(1.0))

    def _edit(self, i: int):
        StepEditor(self, step=self.steps[i],
                   on_save=lambda s, i=i: self._replace(i, s))

    def _replace(self, i, s):
        self._save_undo()
        auto_wait = s.pop("auto_wait", False)
        auto_wait_secs = s.pop("auto_wait_secs", 1.0)
        self.steps[i] = s
        # Auto-insert Wait after this step if requested
        if auto_wait:
            wait_step = {"type": "wait", "seconds": float(auto_wait_secs),
                         "note": "auto", "enabled": True}
            # Only insert if next step isn't already this auto-wait
            next_i = i + 1
            if (next_i >= len(self.steps) or
                    not (self.steps[next_i].get("type") == "wait" and
                         self.steps[next_i].get("note") == "auto")):
                self.steps.insert(next_i, wait_step)
        self._refresh()

    def _del(self, i: int):
        self._save_undo()
        self.steps.pop(i)
        self._refresh()

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
        if _prefs.get("confirm_clear", True):
            if not messagebox.askyesno("Clear steps", f"Remove all {len(self.steps)} steps?"):
                return
        self._save_undo()
        self.steps.clear()
        self._refresh()

    def _cut_selected(self):
        """Cut: copy to clipboard then mark for removal on paste."""
        if not self.steps:
            return
        # In card view there is no multi-selection; copy all as fallback
        self._clipboard = copy.deepcopy(self.steps)
        self._cut_mode  = True
        messagebox.showinfo("Cut",
            f"{len(self._clipboard)} step(s) copied to clipboard.\n"
            "Paste with the Paste button or use the Grid Editor for row-level cut/paste.")

    def _copy_selected(self):
        """Copy all steps to the panel clipboard."""
        if not self.steps:
            return
        self._clipboard = copy.deepcopy(self.steps)
        self._cut_mode  = False
        messagebox.showinfo("Copied", f"{len(self._clipboard)} step(s) copied to clipboard.")

    def _paste_steps(self):
        """Paste clipboard steps at the end (or use Grid Editor for positional paste)."""
        if not self._clipboard:
            messagebox.showinfo("Paste", "Clipboard is empty.")
            return
        self._save_undo()
        new_steps = copy.deepcopy(self._clipboard)
        if self._cut_mode:
            self.steps.clear()
            self._cut_mode = False
        self.steps.extend(new_steps)
        self._refresh()

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



# ── Excel-style Grid Flow Editor Window ───────────────────────────────────────

class FlowEditorWindow(tk.Toplevel):
    """Full-screen Excel-style step editor with Treeview grid, sorting,
    multi-select, cut/copy/paste, find/replace and keyboard shortcuts."""

    _COL_DEFS = [
        ("#",        60,  "e"),
        ("Enabled",  64,  "center"),
        ("Type",    110,  "w"),
        ("Summary", 260,  "w"),
        ("Note",    200,  "w"),
    ]

    def __init__(self, parent, flow_panel: "FlowPanel", title: str = "Flow Editor"):
        super().__init__(parent)
        self.title(f"Swastik RPA  ·  {title}")
        self.configure(bg=T["bg"])
        self.state("zoomed")
        self.minsize(860, 560)

        self._panel      = flow_panel
        self._steps      = copy.deepcopy(flow_panel.steps)
        self._undo       = deque(maxlen=40)
        self._redo       = deque(maxlen=40)
        self._clipboard: list = []
        self._cut_ids:   set  = set()          # iids currently cut
        self._sort_col   = "#"
        self._sort_rev   = False
        self._fr_open    = False

        self._build()
        self._refresh()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Keyboard shortcuts
        self.bind("<Control-z>",         lambda e: self.undo())
        self.bind("<Control-y>",         lambda e: self.redo())
        self.bind("<Control-a>",         lambda e: self._select_all())
        self.bind("<Control-x>",         lambda e: self._cut_sel())
        self.bind("<Control-c>",         lambda e: self._copy_sel())
        self.bind("<Control-v>",         lambda e: self._paste_steps())
        self.bind("<Delete>",            lambda e: self._del_selected())
        self.bind("<Control-d>",         lambda e: self._dup_selected())
        self.bind("<Control-f>",         lambda e: self._toggle_fr())
        self.bind("<Up>",                lambda e: self._move_sel(-1))
        self.bind("<Down>",              lambda e: self._move_sel(1))
        self.grab_set()

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build(self):
        # ── Top toolbar ───────────────────────────────────────────────────────
        tb = tk.Frame(self, bg=T["bg2"], pady=6)
        tb.pack(fill="x")

        def btn(text, bg, fg, cmd, tip="", side="left"):
            b = tk.Button(tb, text=text, bg=bg, fg=fg, font=T["font_b"],
                          relief="flat", cursor="hand2", padx=9, pady=4, command=cmd)
            b.pack(side=side, padx=3)
            if tip: Tooltip(b, tip)
            return b

        btn("+ Add Step",     T["acc"],  "white",      self._add_step,      "Add a new step")
        btn("✏ Edit",         T["bg3"],  T["fg2"],     self._edit_selected, "Edit selected (double-click)")
        btn("⧉ Dup",          T["bg3"],  T["fg2"],     self._dup_selected,  "Duplicate selected  Ctrl+D")

        tk.Frame(tb, bg=T["fg3"], width=1, relief="flat").pack(side="left", fill="y", padx=4)

        btn("✂ Cut",          T["bg3"],  T["fg2"],     self._cut_sel,       "Cut selected  Ctrl+X")
        btn("⧉ Copy",         T["bg3"],  T["fg2"],     self._copy_sel,      "Copy selected  Ctrl+C")
        btn("📋 Paste",       T["bg3"],  T["fg2"],     self._paste_steps,   "Paste after selection  Ctrl+V")

        tk.Frame(tb, bg=T["fg3"], width=1, relief="flat").pack(side="left", fill="y", padx=4)

        btn("▲ Up",           T["bg3"],  T["fg2"],     lambda: self._move_sel(-1),   "Move up  ↑")
        btn("▼ Down",         T["bg3"],  T["fg2"],     lambda: self._move_sel(1),    "Move down  ↓")
        btn("⇈ Top",          T["bg3"],  T["fg2"],     lambda: self._move_to_edge(0),"Move to top")
        btn("⇊ Bottom",       T["bg3"],  T["fg2"],     lambda: self._move_to_edge(1),"Move to bottom")

        tk.Frame(tb, bg=T["fg3"], width=1, relief="flat").pack(side="left", fill="y", padx=4)

        btn("👁 Toggle",      T["bg3"],  T["fg2"],     self._toggle_selected, "Toggle enabled/disabled")
        btn("↩ Undo",         T["bg3"],  T["fg2"],     self.undo,             "Undo  Ctrl+Z")
        btn("↪ Redo",         T["bg3"],  T["fg2"],     self.redo,             "Redo  Ctrl+Y")
        btn("🔍 Find/Replace",T["bg3"],  T["fg2"],     self._toggle_fr,       "Find & Replace  Ctrl+F")

        tk.Frame(tb, bg=T["fg3"], width=1, relief="flat").pack(side="left", fill="y", padx=4)

        btn("Clear All",      T["bg3"],  T["red"],     self._clear,           "Remove all steps")

        self._count_lbl = tk.Label(tb, text="", bg=T["bg2"], fg=T["fg3"], font=T["font_s"])
        self._count_lbl.pack(side="left", padx=10)

        btn("✔ Apply & Close", T["green"], T["bg"],   self._apply_close, "Apply and close", side="right")
        btn("Cancel",          T["bg3"],   T["fg2"],  self.destroy,       "",               side="right")

        # ── Find / Replace bar (hidden by default) ────────────────────────────
        self._fr_frame = tk.Frame(self, bg=T["bg3"], pady=5)
        # (packed only when open)

        self._fr_find    = tk.StringVar()
        self._fr_replace = tk.StringVar()
        self._fr_status  = tk.StringVar()

        fr = self._fr_frame
        tk.Label(fr, text="Find:",    bg=T["bg3"], fg=T["fg2"], font=T["font_s"]).pack(side="left", padx=(10,2))
        tk.Entry(fr, textvariable=self._fr_find,    bg=T["bg"],  fg=T["fg"],
                 insertbackground=T["fg"], font=T["font_s"], width=22,
                 relief="flat").pack(side="left", padx=2)
        tk.Label(fr, text="Replace:", bg=T["bg3"], fg=T["fg2"], font=T["font_s"]).pack(side="left", padx=(8,2))
        tk.Entry(fr, textvariable=self._fr_replace, bg=T["bg"],  fg=T["fg"],
                 insertbackground=T["fg"], font=T["font_s"], width=22,
                 relief="flat").pack(side="left", padx=2)
        tk.Button(fr, text="Next",     bg=T["bg"],  fg=T["fg2"], font=T["font_s"], relief="flat",
                  cursor="hand2", padx=6, command=lambda: self._do_replace(False)).pack(side="left", padx=3)
        tk.Button(fr, text="All",      bg=T["bg"],  fg=T["fg2"], font=T["font_s"], relief="flat",
                  cursor="hand2", padx=6, command=lambda: self._do_replace(True)).pack(side="left", padx=2)
        tk.Button(fr, text="✕",        bg=T["bg3"], fg=T["fg3"], font=T["font_s"], relief="flat",
                  cursor="hand2", padx=4, command=self._toggle_fr).pack(side="left", padx=4)
        tk.Label(fr, textvariable=self._fr_status, bg=T["bg3"], fg=T["yellow"],
                 font=T["font_s"]).pack(side="left", padx=6)

        # ── Treeview grid ─────────────────────────────────────────────────────
        grid_outer = tk.Frame(self, bg=T["bg"])
        grid_outer.pack(fill="both", expand=True)

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Grid.Treeview",
                        background=T["bg2"], fieldbackground=T["bg2"],
                        foreground=T["fg"],  rowheight=28,
                        font=T["font_m"])
        style.configure("Grid.Treeview.Heading",
                        background=T["bg3"], foreground=T["fg2"],
                        font=T["font_b"],    relief="flat",
                        borderwidth=1)
        style.map("Grid.Treeview",
                  background=[("selected", T["acc"])],
                  foreground=[("selected", "white")])
        style.map("Grid.Treeview.Heading",
                  background=[("active", T["bg4"] if "bg4" in T else T["bg3"])])

        cols = [c[0] for c in self._COL_DEFS]
        self._tree = ttk.Treeview(grid_outer, columns=cols, show="headings",
                                   selectmode="extended", style="Grid.Treeview")

        for col, width, anchor in self._COL_DEFS:
            self._tree.heading(col, text=col,
                               command=lambda c=col: self._sort_by(c))
            self._tree.column(col, width=width, anchor=anchor,
                              stretch=(col == "Summary"))

        vsb = ttk.Scrollbar(grid_outer, orient="vertical",   command=self._tree.yview)
        hsb = ttk.Scrollbar(grid_outer, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        self._tree.pack(side="left", fill="both", expand=True)

        # Row tags for visual styling
        self._tree.tag_configure("enabled",  background=T["bg2"])
        self._tree.tag_configure("disabled", background=T["bg"],  foreground=T["fg3"])
        self._tree.tag_configure("cut",      background=T["bg3"], foreground=T["fg3"])

        # Events
        self._tree.bind("<Double-Button-1>",  self._on_dbl_click)
        self._tree.bind("<Button-3>",         self._on_right_click)
        self._tree.bind("<ButtonRelease-1>",  lambda e: self._update_status())

        # ── Status bar ────────────────────────────────────────────────────────
        sb = tk.Frame(self, bg=T["bg2"], pady=4)
        sb.pack(fill="x", side="bottom")
        self._sb_total  = tk.Label(sb, text="", bg=T["bg2"], fg=T["fg3"], font=T["font_s"])
        self._sb_sel    = tk.Label(sb, text="", bg=T["bg2"], fg=T["fg2"], font=T["font_s"])
        self._sb_clip   = tk.Label(sb, text="", bg=T["bg2"], fg=T["yellow"], font=T["font_s"])
        self._sb_sort   = tk.Label(sb, text="", bg=T["bg2"], fg=T["fg3"], font=T["font_s"])
        self._sb_hint   = tk.Label(sb, text="Dbl-click=edit  |  Ctrl+X/C/V  |  Del=delete  |  ↑↓=move",
                                   bg=T["bg2"], fg=T["bg4"] if "bg4" in T else T["fg3"],
                                   font=T["font_s"])
        for w in (self._sb_total, self._sb_sel, self._sb_clip, self._sb_sort):
            w.pack(side="left", padx=10)
        self._sb_hint.pack(side="right", padx=12)

    # ── Undo / Redo ───────────────────────────────────────────────────────────

    def _save_undo(self):
        self._undo.append(copy.deepcopy(self._steps))
        self._redo.clear()

    def undo(self):
        if not self._undo: return
        self._redo.append(copy.deepcopy(self._steps))
        self._steps = self._undo.pop()
        self._refresh()

    def redo(self):
        if not self._redo: return
        self._undo.append(copy.deepcopy(self._steps))
        self._steps = self._redo.pop()
        self._refresh()

    # ── Data helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _step_summary(s: dict) -> str:
        from core.helpers import step_summary
        return step_summary(s)

    @staticmethod
    def _step_display(s: dict) -> tuple:
        from core.helpers import step_human_label
        ico, lbl, summary, _ = step_human_label(s)
        return ico, lbl, summary

    def _iid(self, idx: int) -> str:
        """Treeview iid = string index into self._steps list."""
        return str(idx)

    def _sel_indices(self) -> list:
        """Return sorted list of integer indices currently selected."""
        iids = self._tree.selection()
        return sorted(int(i) for i in iids)

    # ── Render / Refresh ─────────────────────────────────────────────────────

    def _refresh(self):
        sel_iids = set(self._tree.selection())
        self._tree.delete(*self._tree.get_children())

        n = len(self._steps)
        self._count_lbl.config(text=f"{n} step{'s' if n != 1 else ''}")

        for i, s in enumerate(self._steps):
            ico, lbl, summary = self._step_display(s)
            enabled  = s.get("enabled", True)
            note     = s.get("note", "") or ""
            tag      = "enabled" if enabled else "disabled"
            en_txt   = "✔ on" if enabled else "✘ off"
            type_txt = f"{ico}  {s.get('type','?')}"
            values   = (i + 1, en_txt, type_txt, summary, note)
            iid      = self._iid(i)
            self._tree.insert("", "end", iid=iid, values=values, tags=(tag,))

        # Restore selection (if iids still valid)
        valid = [i for i in sel_iids if self._tree.exists(i)]
        if valid:
            self._tree.selection_set(valid)
            self._tree.see(valid[0])

        self._update_status()
        self._update_sort_indicator()

    def _update_status(self):
        n   = len(self._steps)
        sel = len(self._tree.selection())
        clip = len(self._clipboard)
        self._sb_total.config(text=f"Total: {n}")
        self._sb_sel.config(  text=f"Selected: {sel}" if sel else "")
        self._sb_clip.config( text=f"{'Cut' if self._cut_ids else 'Copied'}: {clip}" if clip else "")
        sort_txt = f"Sort: {self._sort_col} {'↑' if not self._sort_rev else '↓'}" if self._sort_col != "#" else ""
        self._sb_sort.config( text=sort_txt)

    def _update_sort_indicator(self):
        for col, _, _ in self._COL_DEFS:
            heading = self._sort_col if self._sort_col else ""
            if col == heading and col != "#":
                arrow = " ↑" if not self._sort_rev else " ↓"
                self._tree.heading(col, text=col + arrow)
            else:
                self._tree.heading(col, text=col)

    # ── Sorting ───────────────────────────────────────────────────────────────

    def _sort_by(self, col: str):
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = False

        if col == "#":
            # Reset to natural order
            self._sort_col = "#"
            self._sort_rev = False
            self._refresh()
            return

        key_map = {
            "Enabled": lambda s: (0 if s.get("enabled", True) else 1),
            "Type":    lambda s: s.get("type", ""),
            "Summary": lambda s: self._step_summary(s).lower(),
            "Note":    lambda s: (s.get("note") or "").lower(),
        }
        keyfn = key_map.get(col, lambda s: "")
        self._steps.sort(key=keyfn, reverse=self._sort_rev)
        self._refresh()

    # ── Selection helpers ─────────────────────────────────────────────────────

    def _select_all(self):
        self._tree.selection_set(self._tree.get_children())
        self._update_status()

    # ── Find / Replace ────────────────────────────────────────────────────────

    def _toggle_fr(self):
        self._fr_open = not self._fr_open
        if self._fr_open:
            self._fr_frame.pack(fill="x", after=self.nametowidget(self.pack_slaves()[0]))
            self._fr_find_entry = self._fr_frame.winfo_children()[1]
            try: self._fr_find_entry.focus_set()
            except Exception: pass
        else:
            self._fr_frame.pack_forget()
        self._fr_status.set("")

    def _do_replace(self, replace_all: bool):
        find_txt = self._fr_find.get()
        repl_txt = self._fr_replace.get()
        if not find_txt:
            self._fr_status.set("Enter text to find.")
            return
        self._save_undo()
        fields   = ["url", "text", "selector", "note", "key", "condition", "filename", "value"]
        count    = 0
        for s in self._steps:
            for fld in fields:
                v = s.get(fld)
                if isinstance(v, str) and find_txt in v:
                    if replace_all:
                        s[fld] = v.replace(find_txt, repl_txt)
                        count += v.count(find_txt)
                    else:
                        if count == 0:
                            s[fld] = v.replace(find_txt, repl_txt, 1)
                            count  = 1
        self._fr_status.set(f"{count} replacement(s)" if count else "No matches found.")
        self._refresh()

    # ── Step CRUD ─────────────────────────────────────────────────────────────

    def _add_step(self):
        def on_pick(t):
            d = {"type": t, **copy.deepcopy(STEP_DEFAULTS.get(t, {}))}
            StepEditor(self, step=d, on_save=self._append)
        StepPickerDialog(self, on_pick)

    def _append(self, s: dict):
        self._save_undo()
        s.pop("auto_wait", None)
        s.pop("auto_wait_secs", None)
        self._steps.append(s)
        self._refresh()
        # Select the new row
        new_iid = self._iid(len(self._steps) - 1)
        if self._tree.exists(new_iid):
            self._tree.selection_set([new_iid])
            self._tree.see(new_iid)

    def _edit_selected(self):
        sel = self._sel_indices()
        if not sel:
            messagebox.showinfo("Edit", "Select a step to edit.")
            return
        self._edit(sel[0])

    def _edit(self, i: int):
        StepEditor(self, step=self._steps[i],
                   on_save=lambda s, i=i: self._replace(i, s))

    def _replace(self, i: int, s: dict):
        self._save_undo()
        s.pop("auto_wait", None)
        s.pop("auto_wait_secs", None)
        self._steps[i] = s
        self._refresh()

    def _del_selected(self):
        sel = self._sel_indices()
        if not sel: return
        self._save_undo()
        for i in reversed(sel):
            self._steps.pop(i)
        self._cut_ids.clear()
        self._refresh()

    def _dup_selected(self):
        sel = self._sel_indices()
        if not sel: return
        self._save_undo()
        insert_after = max(sel)
        dupes = [copy.deepcopy(self._steps[i]) for i in sel]
        for j, d in enumerate(dupes):
            self._steps.insert(insert_after + 1 + j, d)
        self._refresh()

    def _toggle_selected(self):
        sel = self._sel_indices()
        if not sel: return
        self._save_undo()
        for i in sel:
            self._steps[i]["enabled"] = not self._steps[i].get("enabled", True)
        self._refresh()

    def _clear(self):
        if not self._steps: return
        if messagebox.askyesno("Clear steps", f"Remove all {len(self._steps)} steps?"):
            self._save_undo()
            self._steps.clear()
            self._cut_ids.clear()
            self._refresh()

    # ── Cut / Copy / Paste ────────────────────────────────────────────────────

    def _cut_sel(self):
        sel = self._sel_indices()
        if not sel: return
        self._clipboard = [copy.deepcopy(self._steps[i]) for i in sel]
        self._cut_ids   = set(sel)
        # Visually mark cut rows
        for iid in self._tree.get_children():
            idx = int(iid)
            if idx in self._cut_ids:
                self._tree.item(iid, tags=("cut",))
        self._update_status()

    def _copy_sel(self):
        sel = self._sel_indices()
        if not sel: return
        self._clipboard = [copy.deepcopy(self._steps[i]) for i in sel]
        self._cut_ids   = set()
        self._update_status()

    def _paste_steps(self):
        if not self._clipboard: return
        self._save_undo()
        new_steps = copy.deepcopy(self._clipboard)

        # Remove cut source rows first
        if self._cut_ids:
            for i in sorted(self._cut_ids, reverse=True):
                self._steps.pop(i)
            self._cut_ids.clear()

        # Insert after last selected, or at end
        sel = self._sel_indices()
        insert_at = (max(sel) + 1) if sel else len(self._steps)
        insert_at = min(insert_at, len(self._steps))
        for j, s in enumerate(new_steps):
            self._steps.insert(insert_at + j, s)
        self._refresh()
        # Select pasted rows
        new_iids = [self._iid(insert_at + j) for j in range(len(new_steps))
                    if self._tree.exists(self._iid(insert_at + j))]
        if new_iids:
            self._tree.selection_set(new_iids)
            self._tree.see(new_iids[0])

    # ── Move ─────────────────────────────────────────────────────────────────

    def _move_sel(self, direction: int):
        """Move selected rows up (-1) or down (+1)."""
        sel = self._sel_indices()
        if not sel: return
        if direction == -1 and sel[0] == 0: return
        if direction ==  1 and sel[-1] == len(self._steps) - 1: return
        self._save_undo()
        if direction == -1:
            for i in sel:
                self._steps[i], self._steps[i-1] = self._steps[i-1], self._steps[i]
            new_sel = [i - 1 for i in sel]
        else:
            for i in reversed(sel):
                self._steps[i], self._steps[i+1] = self._steps[i+1], self._steps[i]
            new_sel = [i + 1 for i in sel]
        self._refresh()
        new_iids = [self._iid(i) for i in new_sel if self._tree.exists(self._iid(i))]
        if new_iids:
            self._tree.selection_set(new_iids)
            self._tree.see(new_iids[0])

    def _move_to_edge(self, edge: int):
        """Move selected rows to top (edge=0) or bottom (edge=1)."""
        sel = self._sel_indices()
        if not sel: return
        self._save_undo()
        moving = [self._steps[i] for i in sel]
        rest   = [s for i, s in enumerate(self._steps) if i not in set(sel)]
        if edge == 0:
            self._steps = moving + rest
            new_start = 0
        else:
            self._steps = rest + moving
            new_start = len(rest)
        self._refresh()
        new_iids = [self._iid(new_start + j) for j in range(len(moving))
                    if self._tree.exists(self._iid(new_start + j))]
        if new_iids:
            self._tree.selection_set(new_iids)
            self._tree.see(new_iids[0])

    # ── Events ────────────────────────────────────────────────────────────────

    def _on_dbl_click(self, event):
        item = self._tree.identify_row(event.y)
        if item:
            self._edit(int(item))

    def _on_right_click(self, event):
        item = self._tree.identify_row(event.y)
        if item:
            if item not in self._tree.selection():
                self._tree.selection_set([item])
            self._update_status()
        menu = tk.Menu(self, tearoff=False, bg=T["bg3"], fg=T["fg"],
                       activebackground=T["acc"], activeforeground="white",
                       font=T["font_s"], relief="flat", bd=0)
        menu.add_command(label="✏  Edit",            command=self._edit_selected)
        menu.add_command(label="⧉  Duplicate",        command=self._dup_selected)
        menu.add_command(label="👁  Toggle enabled",  command=self._toggle_selected)
        menu.add_separator()
        menu.add_command(label="✂  Cut       Ctrl+X", command=self._cut_sel)
        menu.add_command(label="⧉  Copy      Ctrl+C", command=self._copy_sel)
        menu.add_command(label="📋  Paste     Ctrl+V", command=self._paste_steps)
        menu.add_separator()
        menu.add_command(label="▲  Move Up",           command=lambda: self._move_sel(-1))
        menu.add_command(label="▼  Move Down",         command=lambda: self._move_sel(1))
        menu.add_command(label="⇈  Move to Top",       command=lambda: self._move_to_edge(0))
        menu.add_command(label="⇊  Move to Bottom",    command=lambda: self._move_to_edge(1))
        menu.add_separator()
        menu.add_command(label="✕  Delete     Del",    command=self._del_selected)
        menu.post(event.x_root, event.y_root)

    # ── Apply / Close ─────────────────────────────────────────────────────────

    def _apply_close(self):
        self._panel._save_undo()
        self._panel.steps = copy.deepcopy(self._steps)
        self._panel._refresh()
        self.destroy()

    def _on_close(self):
        import json as _json
        try:
            changed = _json.dumps(self._steps, sort_keys=True) != \
                      _json.dumps(self._panel.steps, sort_keys=True)
        except Exception:
            changed = True
        if changed:
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

        # Text widget with BOTH scrollbars
        tf = tk.Frame(self, bg=T["bg"]); tf.pack(fill="both", expand=True)
        self._text = tk.Text(tf, width=36, height=12,
                             bg=T["bg3"], fg=T["fg"],
                             insertbackground=T["fg"], font=T["font_m"],
                             relief="flat", padx=8, pady=6,
                             wrap="none")   # wrap=none enables horizontal scroll

        tsb_v = ttk.Scrollbar(tf, orient="vertical",   command=self._text.yview)
        tsb_h = ttk.Scrollbar(tf, orient="horizontal", command=self._text.xview)
        self._text.configure(yscrollcommand=tsb_v.set, xscrollcommand=tsb_h.set)

        tsb_v.pack(side="right",  fill="y")
        tsb_h.pack(side="bottom", fill="x")
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

        tk.Button(br, text="A→Z",
                  bg=T["bg3"], fg=T["fg2"],
                  font=T["font_s"], relief="flat", cursor="hand2",
                  padx=5, command=lambda: self._sort_names(False)
                  ).pack(side="left", padx=2)
        Tooltip(br.winfo_children()[-1], "Sort names A → Z")

        tk.Button(br, text="Z→A",
                  bg=T["bg3"], fg=T["fg2"],
                  font=T["font_s"], relief="flat", cursor="hand2",
                  padx=5, command=lambda: self._sort_names(True)
                  ).pack(side="left", padx=2)
        Tooltip(br.winfo_children()[-1], "Sort names Z → A")

        tk.Button(br, text="🔀",
                  bg=T["bg3"], fg=T["fg2"],
                  font=T["font_s"], relief="flat", cursor="hand2",
                  padx=5, command=self._shuffle_names
                  ).pack(side="left", padx=2)
        Tooltip(br.winfo_children()[-1], "Shuffle names randomly")

        tk.Button(br, text="⊘ Dedup",
                  bg=T["bg3"], fg=T["fg2"],
                  font=T["font_s"], relief="flat", cursor="hand2",
                  padx=5, command=self._dedup_names
                  ).pack(side="left", padx=2)
        Tooltip(br.winfo_children()[-1], "Remove duplicate names")

        self._count_lbl = tk.Label(br, text="", bg=T["bg"],
                                   fg=T["green"],
                                   font=("Segoe UI Semibold", 9))
        self._count_lbl.pack(side="left", padx=4)

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

        # Horizontally scrollable recent buttons
        rc = tk.Canvas(self._recent_frame, bg=T["bg"], height=24,
                       highlightthickness=0)
        rc_hsb = ttk.Scrollbar(self._recent_frame, orient="horizontal",
                               command=rc.xview)
        rc.configure(xscrollcommand=rc_hsb.set)
        rc_inner = tk.Frame(rc, bg=T["bg"])
        rc.create_window((0, 0), window=rc_inner, anchor="nw")
        rc_inner.bind("<Configure>",
            lambda e: rc.configure(scrollregion=rc.bbox("all")))
        rc.pack(side="left", fill="x", expand=True)

        has_any = False
        for path in self._recent[:5]:
            if not os.path.exists(path): continue
            has_any = True
            tk.Button(rc_inner, text=os.path.basename(path),
                      bg=T["bg"], fg=T["acc"], font=T["font_s"],
                      relief="flat", cursor="hand2",
                      command=lambda p=path: self._load_file(p)
                      ).pack(side="left", padx=4)

        if has_any:
            rc_inner.update_idletasks()
            if rc_inner.winfo_reqwidth() > rc.winfo_width():
                rc_hsb.pack(side="left", fill="x")

    def _sync_from_text(self):
        raw = self._text.get("1.0", "end-1c")
        self._names = [n.strip() for n in raw.splitlines() if n.strip()]
        n = len(self._names)
        self._count_lbl.config(
            text=(f"✔ {n} {'name' if n == 1 else 'names'}" if self._names else ""))

    def _sort_names(self, reverse: bool):
        self._names.sort(key=lambda x: x.lower(), reverse=reverse)
        self._text.delete("1.0", "end")
        self._text.insert("1.0", "\n".join(self._names))
        self._sync_from_text()

    def _shuffle_names(self):
        random.shuffle(self._names)
        self._text.delete("1.0", "end")
        self._text.insert("1.0", "\n".join(self._names))
        self._sync_from_text()

    def _dedup_names(self):
        seen = set()
        deduped = []
        for n in self._names:
            key = n.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(n)
        removed = len(self._names) - len(deduped)
        self._names = deduped
        self._text.delete("1.0", "end")
        self._text.insert("1.0", "\n".join(self._names))
        self._sync_from_text()
        if removed:
            self._count_lbl.config(text=f"✔ {len(self._names)} names  (-{removed} dupes)")

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
            cols = list(df.columns)
            col  = cols[0]

            if len(cols) > 1:
                from .dialogs import ColumnChooser
                dlg = ColumnChooser(self, cols)
                try:
                    self.wait_window(dlg)
                except Exception:
                    pass
                if hasattr(dlg, "chosen") and dlg.chosen and dlg.chosen in df.columns:
                    col = dlg.chosen

            names = [n.strip() for n in df[col].dropna().astype(str) if n.strip()]
            self._text.delete("1.0", "end")
            self._text.insert("1.0", "\n".join(names))
            self._sync_from_text()
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

        ts = tk.Frame(self, bg=T["bg"]); ts.pack(fill="x", pady=(0, 8))
        tk.Label(ts, text=L("test_single") + ":",
                 bg=T["bg"], fg=T["fg3"], font=T["font_s"]).pack(side="left")
        self._test_var = tk.StringVar()
        te = tk.Entry(ts, textvariable=self._test_var, width=18,
                 bg=T["bg3"], fg=T["fg"], insertbackground=T["fg"],
                 font=T["font_m"], relief="flat")
        te.pack(side="left", padx=8)
        Tooltip(te, "Type a name here to test the flow with just one entry")
        tb = tk.Button(ts, text="▶ Run", bg=T["bg3"], fg=T["fg2"],
                       font=T["font_s"], relief="flat", cursor="hand2",
                       command=self._on_test_single)
        tb.pack(side="left")
        Tooltip(tb, "Test your flow with this single name")

        self._progress = ttk.Progressbar(self, orient="horizontal", mode="determinate")
        self._progress.pack(fill="x", pady=(0, 10))

        # Name status frame — scrollable when many names run
        ns_outer = tk.Frame(self, bg=T["bg"]); ns_outer.pack(fill="x", pady=(0, 4))
        ns_canvas = tk.Canvas(ns_outer, bg=T["bg"], height=48, highlightthickness=0)
        ns_vsb = ttk.Scrollbar(ns_outer, orient="vertical",   command=ns_canvas.yview)
        ns_hsb = ttk.Scrollbar(ns_outer, orient="horizontal", command=ns_canvas.xview)
        ns_canvas.configure(yscrollcommand=ns_vsb.set, xscrollcommand=ns_hsb.set)
        ns_vsb.pack(side="right",  fill="y")
        ns_hsb.pack(side="bottom", fill="x")
        ns_canvas.pack(side="left", fill="both", expand=True)
        self._name_status_frame = tk.Frame(ns_canvas, bg=T["bg"])
        ns_win = ns_canvas.create_window((0, 0), window=self._name_status_frame, anchor="nw")
        self._name_status_frame.bind("<Configure>",
            lambda e: ns_canvas.configure(scrollregion=ns_canvas.bbox("all")))
        ns_canvas.bind("<Configure>",
            lambda e: ns_canvas.itemconfig(ns_win, width=e.width))
        ns_canvas.bind("<MouseWheel>",
            lambda e: ns_canvas.yview_scroll(-1*(e.delta//120), "units"))
        self._ns_canvas = ns_canvas

        self._settings_expanded = False
        self._settings_btn = tk.Button(self, text="⚙  Settings  ▾",
                                       bg=T["bg2"], fg=T["fg2"],
                                       font=T["font_s"], relief="flat",
                                       cursor="hand2", anchor="w",
                                       command=self._toggle_settings)
        self._settings_btn.pack(fill="x", pady=(0, 2))
        self._settings_frame = tk.Frame(self, bg=T["bg2"])
        self._build_settings()

        lhdr = tk.Frame(self, bg=T["bg"]); lhdr.pack(fill="x", pady=(8, 0))
        tk.Label(lhdr, text="Log", bg=T["bg"], fg=T["fg2"],
                 font=("Segoe UI Semibold", 9)).pack(side="left")
        for txt, cmd in [
            ("Clear",   self._clear_log),
            ("Copy",    self._copy_log),
            ("Export",  self._export_log),
        ]:
            tk.Button(lhdr, text=txt, bg=T["bg"], fg=T["fg3"],
                      font=T["font_s"], relief="flat", cursor="hand2",
                      command=cmd).pack(side="right", padx=4)

        # Log box with BOTH scrollbars
        log_outer = tk.Frame(self, bg=T["bg"]); log_outer.pack(fill="both", expand=True, pady=(4, 0))
        self._log_box = tk.Text(log_outer, height=12, bg="#0a0e14", fg=T["fg2"],
                                font=("Consolas", 8), state="disabled",
                                relief="flat", padx=8, pady=6,
                                wrap="none")   # wrap=none for horizontal scroll

        log_vsb = ttk.Scrollbar(log_outer, orient="vertical",   command=self._log_box.yview)
        log_hsb = ttk.Scrollbar(log_outer, orient="horizontal", command=self._log_box.xview)
        self._log_box.configure(yscrollcommand=log_vsb.set, xscrollcommand=log_hsb.set)

        log_vsb.pack(side="right",  fill="y")
        log_hsb.pack(side="bottom", fill="x")
        self._log_box.pack(side="left", fill="both", expand=True)

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
            ("countdown", L("countdown_lbl"), str(_prefs.get("countdown", 5)),
             "Seconds before automation starts"),
            ("between",   L("between"),       str(_prefs.get("between", 1.0)),
             "Seconds to wait after each name"),
            ("retries",   L("retries"),       str(_prefs.get("retries", 0)),
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

        self._dry_run = tk.BooleanVar(value=_prefs.get("dry_run", False))
        self._fail_ss = tk.BooleanVar(value=_prefs.get("fail_ss", False))
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
        except (ValueError, Exception):
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
        def _int(key, fallback):
            try:   return int(float(self._svars[key].get() or fallback))
            except: return fallback

        def _float(key, fallback):
            try:   return float(self._svars[key].get() or fallback)
            except: return fallback

        return {
            "countdown": _int("countdown", 5),
            "between":   _float("between", 1.0),
            "retries":   _int("retries", 0),
            "dry_run":   self._dry_run.get(),
            "fail_ss":   self._fail_ss.get(),
        }

    def set_running(self, running: bool, total: int = 0):
        if running:
            self._run_btn.config(state="disabled")
            self._pause_btn.config(state="normal", text=L("pause"))
            self._stop_btn.config(state="normal")
            self._progress.config(maximum=max(total, 1), value=0)
            self._status_lbl.config(text=L("running"), fg=T["yellow"])
            for w in self._name_status_frame.winfo_children():
                try: w.destroy()
                except Exception: pass
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
        # Also add a badge in the scrollable name status area
        badge = tk.Label(self._name_status_frame,
                         text=("✔ " if ok else "✘ ") + name,
                         bg=T["bg"], fg=T["green"] if ok else T["red"],
                         font=T["font_s"], padx=4)
        badge.pack(side="left", padx=2, pady=2)
        self._ns_canvas.configure(scrollregion=self._ns_canvas.bbox("all"))
        self._ns_canvas.xview_moveto(1.0)

    def set_timer(self, text: str):  self._timer_lbl.config(text=text)
    def set_eta(self, text: str):    self._eta_lbl.config(text=text)

    def set_done(self, s: int, f: list, elapsed: float):
        self._status_lbl.config(
            text=f"{L('done')}  ✔{s}  ✘{len(f)}  ⏱{elapsed:.0f}s",
            fg=T["green"] if not f else T["yellow"])

    def toggle_pause_label(self, is_paused: bool):
        self._pause_btn.config(text=L("resume") if is_paused else L("pause"))

    def log(self, msg: str, tag: str = None):
        def _do():
            try:
                self._log_box.config(state="normal")
                if not tag:
                    t = None
                    msg_str = str(msg)
                    if any(x in msg_str for x in ("✔", "Done", "succeeded", "ok")):
                        t = "ok"
                    elif any(x in msg_str for x in ("✘", "Error", "failed", "Failed")):
                        t = "err"
                    elif any(x in msg_str for x in ("⚠", "⏸", "Practice", "Stopped")):
                        t = "warn"
                    elif msg_str.startswith("  ") or msg_str.startswith("   "):
                        t = "dim"
                    elif "[" in msg_str and "/" in msg_str:
                        t = "head"
                else:
                    t = tag
                near_bottom = self._log_box.yview()[1] > 0.90
                self._log_box.insert("end", str(msg) + "\n", t or "")
                if near_bottom:
                    self._log_box.see("end")
                self._log_box.config(state="disabled")
            except Exception:
                pass

        try:
            self.after(0, _do)
        except Exception:
            pass

    def _clear_log(self):
        self._log_box.config(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.config(state="disabled")

    def _copy_log(self):
        try:
            content = self._log_box.get("1.0", "end")
            self.clipboard_clear()
            self.clipboard_append(content)
        except Exception as e:
            messagebox.showerror("Copy Error", str(e))

    def _export_log(self):
        init_dir = _prefs.get("export_folder", "")
        path = filedialog.asksaveasfilename(
            initialdir=init_dir or None,
            defaultextension=".txt",
            initialfile=f"swastik_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if not path: return
        _prefs["export_folder"] = os.path.dirname(path)
        content = self._log_box.get("1.0", "end")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.log(f"Log exported → {os.path.basename(path)}", "ok")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _on_test_single(self):
        if self.on_test_single_cb:
            self.on_test_single_cb(self._test_var.get().strip())
