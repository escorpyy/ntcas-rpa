"""
ui/if_editor.py
===============
IfConditionEditor — side-by-side THEN/ELSE branch editor.

Called directly from FlowPanel._edit() with a simple type check:

    if step.get("type") == "if_condition":
        from ui.if_editor import IfConditionEditor
        IfConditionEditor(self, step, on_save=lambda s: self._replace(i, s))
        return

No monkey-patching. The call site in panels.py is a 4-line addition.
"""

from __future__ import annotations

import copy
import tkinter as tk
from tkinter import ttk

from core.constants import T


class IfConditionEditor(tk.Toplevel):
    """
    Two side-by-side FlowPanel instances for editing then_steps / else_steps.
    A read-only condition summary is shown at the top so the user always
    knows what they are branching on.
    """

    def __init__(self, parent, step: dict, on_save):
        super().__init__(parent)
        self.title("✏  Edit If / Else Branches")
        self.configure(bg=T["bg"])
        self.geometry("1100x720")
        self.minsize(820, 560)
        self.resizable(True, True)
        self.attributes("-topmost", True)

        self._step    = copy.deepcopy(step)
        self._on_save = on_save

        self._build()
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        # ── Header: condition summary ─────────────────────────────────────────
        hdr = tk.Frame(self, bg=T["cyan"])
        hdr.pack(fill="x")
        tk.Label(hdr, text="  🔀  If / Else Branch Editor",
                 bg=T["cyan"], fg=T["bg"],
                 font=("Segoe UI Semibold", 12),
                 pady=10).pack(side="left", padx=12)
        tk.Label(hdr, text=self._condition_summary(),
                 bg=T["cyan"], fg=T["bg"],
                 font=T["font_b"]).pack(side="left", padx=8)

        # ── Two-panel split ───────────────────────────────────────────────────
        pane = tk.PanedWindow(self, orient="horizontal",
                              bg=T["bg4"], sashwidth=6, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        # THEN (left)
        then_outer = tk.Frame(pane, bg=T["bg"])
        pane.add(then_outer, stretch="always")
        tk.Frame(then_outer, bg=T["green"]).pack(fill="x", ipady=4)
        tk.Label(then_outer,
                 text="  ✔  THEN  — steps when condition is TRUE",
                 bg=T["green"], fg="white",
                 font=("Segoe UI Semibold", 10)
                 ).place(in_=then_outer.winfo_children()[-2],
                         relx=0, rely=0, relwidth=1)

        # rebuild label properly
        for w in then_outer.winfo_children():
            w.destroy()
        then_hdr = tk.Frame(then_outer, bg=T["green"]); then_hdr.pack(fill="x")
        tk.Label(then_hdr, text="  ✔  THEN  — steps when condition is TRUE",
                 bg=T["green"], fg="white",
                 font=("Segoe UI Semibold", 10), pady=6
                 ).pack(side="left", padx=8)

        # ELSE (right)
        else_outer = tk.Frame(pane, bg=T["bg"])
        pane.add(else_outer, stretch="always")
        else_hdr = tk.Frame(else_outer, bg=T["red"]); else_hdr.pack(fill="x")
        tk.Label(else_hdr, text="  ✘  ELSE  — steps when condition is FALSE",
                 bg=T["red"], fg="white",
                 font=("Segoe UI Semibold", 10), pady=6
                 ).pack(side="left", padx=8)

        # Embed FlowPanel in each side
        from ui.panels import FlowPanel

        self._then_panel = FlowPanel(then_outer, "then")
        self._then_panel.pack(fill="both", expand=True)
        self._then_panel.load(self._step.get("then_steps", []))

        self._else_panel = FlowPanel(else_outer, "else")
        self._else_panel.pack(fill="both", expand=True)
        self._else_panel.load(self._step.get("else_steps", []))

        # ── Bottom toolbar ────────────────────────────────────────────────────
        bf = tk.Frame(self, bg=T["bg2"], pady=10)
        bf.pack(fill="x", side="bottom")

        tk.Button(bf, text="  ✔  Save Branches  ",
                  bg=T["acc"], fg="white",
                  font=("Segoe UI Semibold", 11), relief="flat", cursor="hand2",
                  padx=18, pady=8, command=self._save).pack(side="left", padx=16)
        tk.Button(bf, text="Cancel",
                  bg=T["bg3"], fg=T["fg2"],
                  font=T["font_b"], relief="flat", cursor="hand2",
                  padx=10, pady=8, command=self.destroy).pack(side="left")
        tk.Label(bf,
                 text="Changes apply only when you click Save Branches.",
                 bg=T["bg2"], fg=T["fg3"],
                 font=T["font_s"]).pack(side="left", padx=16)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _condition_summary(self) -> str:
        s        = self._step
        source   = s.get("source", "variable")
        cond     = s.get("condition", "contains")
        value    = s.get("value", "")
        variable = s.get("variable", "{name}")

        if source == "variable":
            subject = variable
        elif source == "ocr":
            subject = f"OCR({s.get('x',0)},{s.get('y',0)},{s.get('w',300)},{s.get('h',60)})"
        elif source == "window_title":
            subject = "window title"
        else:
            subject = source

        if cond in ("empty", "not_empty", "always_true"):
            return f"if  {subject}  {cond}"
        return f"if  {subject}  {cond}  '{value}'"

    # ── Save ─────────────────────────────────────────────────────────────────

    def _save(self):
        result                = copy.deepcopy(self._step)
        result["then_steps"]  = self._then_panel.get()
        result["else_steps"]  = self._else_panel.get()
        self._on_save(result)
        self.destroy()
