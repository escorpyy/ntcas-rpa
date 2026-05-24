'''
ui/resume_dialog.py  — v9.5
============================
ResumeDialog — shown by App._run() when a checkpoint exists.
Called directly, no monkey-patching.
'''
from __future__ import annotations
import tkinter as tk
from tkinter import messagebox, ttk
from core.constants import T
from core.checkpoint import CheckpointManager

class ResumeDialog(tk.Toplevel):
    """
    Shows checkpoint info. User picks:
      "resume"  — skip already-done names
      "restart" — wipe checkpoint, fresh run
      "cancel"  — abort

    Read  dlg.choice  after wait_window().
    """
    def __init__(self, parent, info: dict):
        super().__init__(parent)
        self.title("Resume previous run?")
        self.configure(bg=T["bg"])
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.choice = "cancel"
        self._build(info)
        self.grab_set()

    def _build(self, info: dict):
        hdr = tk.Frame(self, bg=T["bg2"], pady=14); hdr.pack(fill="x")
        tk.Label(hdr, text="💾  Previous run found",
                 bg=T["bg2"], fg=T["acc"],
                 font=("Segoe UI Semibold", 13)).pack(side="left", padx=20)

        body = tk.Frame(self, bg=T["bg"]); body.pack(fill="x", padx=24, pady=16)

        def stat(label, value, color=None):
            r = tk.Frame(body, bg=T["bg"]); r.pack(fill="x", pady=3)
            tk.Label(r, text=label, bg=T["bg"], fg=T["fg2"],
                     font=T["font_b"], width=18, anchor="e").pack(side="left")
            tk.Label(r, text=str(value), bg=T["bg"],
                     fg=color or T["fg"],
                     font=("Segoe UI Semibold", 9)).pack(side="left", padx=8)

        saved_at = info.get("saved_at", "")[:16].replace("T", " at ")
        stat("Saved at:",     saved_at)
        stat("Total names:",  info.get("total", "?"))
        stat("Completed:",    info.get("completed", 0), T["green"])
        stat("Failed:",       info.get("failed", 0),
             T["red"] if info.get("failed") else T["fg3"])
        stat("Still to run:", info.get("remaining", "?"), T["yellow"])
        if info.get("flow_path"):
            stat("Flow:", info["flow_path"])

        tk.Frame(self, bg=T["bg4"], height=1).pack(fill="x", padx=20)

        bf = tk.Frame(self, bg=T["bg2"], pady=12); bf.pack(fill="x")
        tk.Button(bf, text="⏩  Resume from where it stopped",
                  bg=T["green"], fg=T["bg"],
                  font=("Segoe UI Semibold", 10), relief="flat", cursor="hand2",
                  padx=16, pady=8,
                  command=self._resume).pack(side="left", padx=16)
        tk.Button(bf, text="↺  Restart from the beginning",
                  bg=T["bg3"], fg=T["fg2"],
                  font=T["font_b"], relief="flat", cursor="hand2",
                  padx=12, pady=8,
                  command=self._restart).pack(side="left", padx=4)
        tk.Button(bf, text="Cancel",
                  bg=T["bg"], fg=T["fg3"],
                  font=T["font_s"], relief="flat", cursor="hand2",
                  command=self._cancel).pack(side="right", padx=16)

    def _resume(self):  self.choice = "resume";  self.destroy()
    def _restart(self): self.choice = "restart"; self.destroy()
    def _cancel(self):  self.choice = "cancel";  self.destroy()


def check_and_show_resume_dialog(parent, flow: list, names: list) -> str:
    """
    Called by App._run() before launching the executor.
    Returns "resume", "restart", or "cancel".
    Returns "restart" immediately when no checkpoint exists.
    """
    cp = CheckpointManager.load_for_flow(flow)
    if cp is None:
        return "restart"

    remaining = len(cp.get_remaining())
    if remaining == 0:
        cp.clear()
        return "restart"

    info = cp.summary()
    dlg  = ResumeDialog(parent, info)
    parent.wait_window(dlg)

    if dlg.choice == "restart":
        from core.checkpoint import flow_hash
        CheckpointManager.delete_by_hash(flow_hash(flow))

    return dlg.choice


class CheckpointManagerDialog(tk.Toplevel):
    """Browse and delete saved checkpoints — open from Settings/Agent tab."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Saved Checkpoints")
        self.configure(bg=T["bg"])
        self.geometry("660x420")
        self.minsize(500, 300)
        self._build()
        self._refresh()
        self.grab_set()

    def _build(self):
        hdr = tk.Frame(self, bg=T["bg2"], pady=10); hdr.pack(fill="x")
        tk.Label(hdr, text="💾  Saved Checkpoints",
                 bg=T["bg2"], fg=T["acc"],
                 font=("Segoe UI Semibold", 12)).pack(side="left", padx=16)
        tk.Button(hdr, text="🗑 Delete Selected",
                  bg=T["bg3"], fg=T["red"], font=T["font_s"],
                  relief="flat", cursor="hand2",
                  command=self._delete_selected).pack(side="right", padx=8)
        tk.Button(hdr, text="🗑 Delete All",
                  bg=T["bg3"], fg=T["red"], font=T["font_s"],
                  relief="flat", cursor="hand2",
                  command=self._delete_all).pack(side="right", padx=4)

        cols = ("Hash", "Saved at", "Done", "Failed", "Remaining", "Flow file")
        self._tree = ttk.Treeview(self, columns=cols, show="headings", height=12)
        for col, w in zip(cols, [80, 130, 60, 60, 80, 220]):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="w")
        sb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0, 8))
        self._tree.pack(fill="both", expand=True, padx=8, pady=8)

        tk.Button(self, text="Close", bg=T["bg3"], fg=T["fg2"],
                  font=T["font_b"], relief="flat", cursor="hand2",
                  command=self.destroy).pack(pady=8)

    def _refresh(self):
        for row in self._tree.get_children():
            self._tree.delete(row)
        for cp in CheckpointManager.list_all():
            self._tree.insert("", "end", iid=cp["fhash"],
                              values=(cp["fhash"],
                                      cp["saved_at"][:16].replace("T", " "),
                                      cp["completed"], cp["failed"],
                                      cp["remaining"], cp["flow_path"] or "—"))

    def _delete_selected(self):
        for fhash in self._tree.selection():
            CheckpointManager.delete_by_hash(fhash)
        self._refresh()

    def _delete_all(self):
        if not messagebox.askyesno("Delete all?",
                                   "Delete every saved checkpoint? Cannot be undone."):
            return
        for cp in CheckpointManager.list_all():
            CheckpointManager.delete_by_hash(cp["fhash"])
        self._refresh()