"""
agent/scheduler.py
==================
Built-in flow scheduler — run flows at specific times or intervals
without the user being present.

Features:
  - Daily at HH:MM  (e.g. every day at 09:00)
  - Interval        (e.g. every 30 minutes)
  - One-shot        (run once at a specific datetime)
  - Days-of-week filter (Mon–Fri only)
  - Max runs limit
  - Pre-run countdown notification
  - Missed-run detection (if computer was asleep)
  - Persistent schedule saved to ~/.swastik/schedules.json
  - Tkinter UI panel for managing schedules

Usage (programmatic):
    sch = Scheduler()
    sch.add(ScheduleEntry(
        name="Morning TDS",
        flow_path="flows/tds_flow.json",
        trigger="daily",
        time_str="09:00",
        days=["mon","tue","wed","thu","fri"],
    ))
    sch.start()
"""

from __future__ import annotations

import copy
import json
import os
import threading
import time
import datetime
from dataclasses import dataclass, field, asdict
from typing import Callable, Optional

import tkinter as tk
from tkinter import messagebox, ttk

from core.constants import T, _prefs, save_prefs, load_json_file, save_json_file

SCHEDULES_FILE = os.path.join(os.path.expanduser("~"), ".swastik", "schedules.json")

DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY_LABELS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ─────────────────────────────────────────────────────────────────────────────
#  ScheduleEntry
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ScheduleEntry:
    id:          str   = ""
    name:        str   = "Unnamed Schedule"
    flow_path:   str   = ""          # path to flow JSON
    names_path:  str   = ""          # path to Excel/CSV name list (optional)
    names_list:  list  = field(default_factory=list)  # inline names

    # Trigger settings
    trigger:     str   = "daily"     # "daily" | "interval" | "once"
    time_str:    str   = "09:00"     # HH:MM for daily / once
    date_str:    str   = ""          # YYYY-MM-DD for once
    interval_min: int  = 60          # minutes for interval trigger
    days:        list  = field(default_factory=lambda: list(DAY_NAMES[:5]))  # Mon-Fri

    # Control
    enabled:     bool  = True
    max_runs:    int   = 0           # 0 = unlimited
    run_count:   int   = 0
    last_run:    str   = ""          # ISO datetime of last execution
    next_run:    str   = ""          # ISO datetime of next scheduled run

    # Settings override
    countdown:   int   = 5
    between:     float = 1.0
    dry_run:     bool  = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ScheduleEntry":
        valid = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**valid)

    def compute_next_run(self, from_dt: Optional[datetime.datetime] = None) -> Optional[datetime.datetime]:
        """Compute next scheduled run datetime from now (or from_dt)."""
        now = from_dt or datetime.datetime.now()

        if self.trigger == "once":
            try:
                dt_str = f"{self.date_str} {self.time_str}"
                dt = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
                return dt if dt > now else None
            except ValueError:
                return None

        if self.trigger == "interval":
            return now + datetime.timedelta(minutes=self.interval_min)

        if self.trigger == "daily":
            try:
                h, m = map(int, self.time_str.split(":"))
            except ValueError:
                return None

            day_map = {d: i for i, d in enumerate(DAY_NAMES)}
            allowed = set(day_map[d] for d in self.days if d in day_map)
            if not allowed:
                return None

            candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if candidate <= now:
                candidate += datetime.timedelta(days=1)

            for _ in range(7):
                if candidate.weekday() in allowed:
                    return candidate
                candidate += datetime.timedelta(days=1)

        return None

    def is_due(self) -> bool:
        """True if this entry should run right now."""
        if not self.enabled:
            return False
        if self.max_runs > 0 and self.run_count >= self.max_runs:
            return False
        if not self.next_run:
            return False
        try:
            next_dt = datetime.datetime.fromisoformat(self.next_run)
            return datetime.datetime.now() >= next_dt
        except ValueError:
            return False


# ─────────────────────────────────────────────────────────────────────────────
#  Scheduler
# ─────────────────────────────────────────────────────────────────────────────

class Scheduler:
    """
    Background scheduler that triggers RPA flows.
    Thread-safe, persists to disk.
    """

    POLL_INTERVAL = 30   # seconds between due-checks

    def __init__(self, run_flow_fn: Optional[Callable] = None):
        """
        Args:
            run_flow_fn: callback(entry: ScheduleEntry) called when a schedule fires.
                         If None, scheduler just logs and marks the run.
        """
        self._entries: list[ScheduleEntry] = []
        self._lock    = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._stop_event = threading.Event()
        self._run_flow_fn = run_flow_fn
        self._log_callbacks: list[Callable[[str], None]] = []
        self._load()

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        """Start the background scheduling thread."""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._log("📅 Scheduler started")

    def stop(self):
        """Stop the background thread."""
        self._running = False
        self._stop_event.set()
        self._log("📅 Scheduler stopped")

    def add(self, entry: ScheduleEntry) -> ScheduleEntry:
        """Add or update a schedule entry. Auto-assigns ID if empty."""
        import uuid
        if not entry.id:
            entry.id = str(uuid.uuid4())[:8]
        # Compute initial next_run
        next_dt = entry.compute_next_run()
        entry.next_run = next_dt.isoformat() if next_dt else ""

        with self._lock:
            # Replace if same ID exists
            self._entries = [e for e in self._entries if e.id != entry.id]
            self._entries.append(entry)

        self._save()
        self._log(f"📅 Added schedule '{entry.name}' → next: {entry.next_run[:16]}")
        return entry

    def remove(self, entry_id: str):
        with self._lock:
            self._entries = [e for e in self._entries if e.id != entry_id]
        self._save()
        self._log(f"📅 Removed schedule {entry_id}")

    def get_all(self) -> list[ScheduleEntry]:
        with self._lock:
            return list(self._entries)

    def on_log(self, callback: Callable[[str], None]):
        self._log_callbacks.append(callback)

    # ── Background loop ───────────────────────────────────────────────────────

    def _loop(self):
        while not self._stop_event.is_set():
            self._check_due()
            self._stop_event.wait(timeout=self.POLL_INTERVAL)

    def _check_due(self):
        with self._lock:
            entries_snapshot = list(self._entries)

        for entry in entries_snapshot:
            if not entry.is_due():
                continue

            self._log(f"⏰ Running scheduled: '{entry.name}'")

            # Mark as run before executing to prevent double-fire
            entry.last_run  = datetime.datetime.now().isoformat()
            entry.run_count += 1
            next_dt = entry.compute_next_run()
            entry.next_run = next_dt.isoformat() if next_dt else ""

            # Disable once-triggers after firing
            if entry.trigger == "once":
                entry.enabled = False

            with self._lock:
                for i, e in enumerate(self._entries):
                    if e.id == entry.id:
                        self._entries[i] = entry
                        break

            self._save()

            # Fire the callback
            if self._run_flow_fn:
                try:
                    self._run_flow_fn(entry)
                except Exception as ex:
                    self._log(f"⚠ Schedule '{entry.name}' run failed: {ex}")
            else:
                self._log(f"[dry] Would run: {entry.flow_path}")

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save(self):
        with self._lock:
            data = [e.to_dict() for e in self._entries]
        save_json_file(SCHEDULES_FILE, data)

    def _load(self):
        raw = load_json_file(SCHEDULES_FILE, [])
        entries = []
        for d in raw:
            try:
                entries.append(ScheduleEntry.from_dict(d))
            except Exception:
                pass
        with self._lock:
            self._entries = entries

    def _log(self, msg: str):
        for cb in self._log_callbacks:
            try:
                cb(msg)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
#  SchedulerPanel  — Tkinter UI
# ─────────────────────────────────────────────────────────────────────────────

class SchedulerPanel(tk.Toplevel):
    """
    Full-featured scheduler management window.
    Open from the Agent tab.
    """

    def __init__(self, parent, scheduler: Scheduler,
                 available_flows: list[str] = None):
        super().__init__(parent)
        self.title("📅 Flow Scheduler")
        self.configure(bg=T["bg"])
        self.geometry("860x620")
        self.minsize(700, 500)
        self._scheduler       = scheduler
        self._available_flows = available_flows or []
        self._selected_id: Optional[str] = None
        self._build()
        self._refresh_list()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _build(self):
        # Header
        hdr = tk.Frame(self, bg=T["bg2"], pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="📅 Flow Scheduler",
                 bg=T["bg2"], fg=T["acc"],
                 font=("Segoe UI Semibold", 13)).pack(side="left", padx=16)
        self._status_lbl = tk.Label(hdr, text="",
                                    bg=T["bg2"], fg=T["green"],
                                    font=T["font_s"])
        self._status_lbl.pack(side="right", padx=16)

        # Toolbar
        tb = tk.Frame(self, bg=T["bg"], pady=6)
        tb.pack(fill="x", padx=12)
        for text, fg, cmd in [
            ("+ New Schedule",  T["green"],  self._new_entry),
            ("✏ Edit",          T["acc"],    self._edit_selected),
            ("🗑 Delete",        T["red"],    self._delete_selected),
            ("▶ Run Now",        T["yellow"], self._run_now),
        ]:
            tk.Button(tb, text=text, bg=T["bg3"], fg=fg,
                      font=T["font_b"], relief="flat", cursor="hand2",
                      padx=10, pady=5, command=cmd).pack(side="left", padx=3)

        # Schedule list
        cols = ("Name", "Trigger", "Next Run", "Last Run", "Runs", "Status")
        self._tree = ttk.Treeview(self, columns=cols, show="headings", height=12)
        widths = [180, 120, 140, 140, 60, 80]
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="w")
        sb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0, 8))
        self._tree.pack(fill="both", expand=True, padx=8, pady=4)
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-Button-1>", lambda e: self._edit_selected())

        # Log
        tk.Label(self, text="Log", bg=T["bg"], fg=T["fg3"],
                 font=T["font_s"]).pack(anchor="w", padx=12)
        self._log_box = tk.Text(self, height=5, bg=T["bg3"], fg=T["fg2"],
                                font=("Consolas", 8), state="disabled",
                                relief="flat", padx=8)
        self._log_box.pack(fill="x", padx=8, pady=(0, 8))

        self._scheduler.on_log(self._append_log)

        # Auto-refresh
        self._auto_refresh()

    def _refresh_list(self):
        for row in self._tree.get_children():
            self._tree.delete(row)

        for entry in self._scheduler.get_all():
            trigger_str = self._trigger_label(entry)
            next_str    = entry.next_run[:16] if entry.next_run else "—"
            last_str    = entry.last_run[:16] if entry.last_run else "never"
            status      = "✔ On" if entry.enabled else "⊘ Off"
            if entry.max_runs > 0 and entry.run_count >= entry.max_runs:
                status = "✓ Done"
            self._tree.insert("", "end", iid=entry.id,
                              values=(entry.name, trigger_str, next_str,
                                      last_str, entry.run_count, status))

    def _trigger_label(self, entry: ScheduleEntry) -> str:
        if entry.trigger == "daily":
            days = "+".join(d[:2].capitalize() for d in entry.days[:3])
            if len(entry.days) > 3:
                days += f"+{len(entry.days)-3} more"
            return f"Daily {entry.time_str} ({days})"
        elif entry.trigger == "interval":
            return f"Every {entry.interval_min}min"
        elif entry.trigger == "once":
            return f"Once {entry.date_str} {entry.time_str}"
        return entry.trigger

    def _on_select(self, e=None):
        sel = self._tree.selection()
        self._selected_id = sel[0] if sel else None

    def _new_entry(self):
        entry = ScheduleEntry()
        ScheduleEntryEditor(self, entry, self._available_flows,
                            on_save=self._on_save_entry)

    def _edit_selected(self):
        if not self._selected_id:
            messagebox.showinfo("Select", "Select a schedule to edit.")
            return
        entries = {e.id: e for e in self._scheduler.get_all()}
        entry = entries.get(self._selected_id)
        if entry:
            ScheduleEntryEditor(self, copy.deepcopy(entry), self._available_flows,
                                on_save=self._on_save_entry)

    def _on_save_entry(self, entry: ScheduleEntry):
        self._scheduler.add(entry)
        self._refresh_list()

    def _delete_selected(self):
        if not self._selected_id:
            return
        if messagebox.askyesno("Delete", "Delete this schedule?"):
            self._scheduler.remove(self._selected_id)
            self._selected_id = None
            self._refresh_list()

    def _run_now(self):
        if not self._selected_id:
            messagebox.showinfo("Select", "Select a schedule to run.")
            return
        entries = {e.id: e for e in self._scheduler.get_all()}
        entry = entries.get(self._selected_id)
        if entry and self._scheduler._run_flow_fn:
            threading.Thread(
                target=self._scheduler._run_flow_fn,
                args=(entry,), daemon=True).start()
            self._append_log(f"▶ Manually triggered: '{entry.name}'")

    def _append_log(self, msg: str):
        def _do():
            try:
                self._log_box.config(state="normal")
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                self._log_box.insert("end", f"[{ts}] {msg}\n")
                self._log_box.see("end")
                self._log_box.config(state="disabled")
            except Exception:
                pass
        try:
            self.after(0, _do)
        except Exception:
            pass

    def _auto_refresh(self):
        if self.winfo_exists():
            self._refresh_list()
            self.after(15_000, self._auto_refresh)


# ─────────────────────────────────────────────────────────────────────────────
#  ScheduleEntryEditor
# ─────────────────────────────────────────────────────────────────────────────

class ScheduleEntryEditor(tk.Toplevel):
    """Dialog to create or edit a single ScheduleEntry."""

    def __init__(self, parent, entry: ScheduleEntry,
                 available_flows: list[str],
                 on_save: Callable):
        super().__init__(parent)
        self.title("Schedule Entry")
        self.configure(bg=T["bg"])
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self._entry          = entry
        self._available_flows = available_flows
        self._on_save        = on_save
        self._build()
        self.grab_set()

    def _build(self):
        pad = dict(padx=20, pady=6)

        tk.Label(self, text="Schedule Name:", bg=T["bg"], fg=T["fg2"],
                 font=T["font_b"]).pack(anchor="w", **pad)
        self._name_v = tk.StringVar(value=self._entry.name)
        tk.Entry(self, textvariable=self._name_v, width=36,
                 bg=T["bg3"], fg=T["fg"], insertbackground=T["fg"],
                 font=T["font_m"], relief="flat").pack(anchor="w", padx=20)

        # Flow path
        tk.Label(self, text="Flow file (.json):", bg=T["bg"], fg=T["fg2"],
                 font=T["font_b"]).pack(anchor="w", **pad)
        fp_row = tk.Frame(self, bg=T["bg"]); fp_row.pack(anchor="w", padx=20)
        self._flow_v = tk.StringVar(value=self._entry.flow_path)
        tk.Entry(fp_row, textvariable=self._flow_v, width=32,
                 bg=T["bg3"], fg=T["fg"], insertbackground=T["fg"],
                 font=T["font_m"], relief="flat").pack(side="left")
        tk.Button(fp_row, text="Browse…", bg=T["bg3"], fg=T["fg2"],
                  font=T["font_s"], relief="flat", cursor="hand2",
                  command=self._browse_flow).pack(side="left", padx=6)

        # Trigger type
        tk.Label(self, text="Trigger:", bg=T["bg"], fg=T["fg2"],
                 font=T["font_b"]).pack(anchor="w", **pad)
        self._trigger_v = tk.StringVar(value=self._entry.trigger)
        trig_row = tk.Frame(self, bg=T["bg"]); trig_row.pack(anchor="w", padx=20)
        for val, lbl in [("daily","Daily"), ("interval","Interval"), ("once","One-time")]:
            tk.Radiobutton(trig_row, text=lbl, variable=self._trigger_v,
                           value=val, bg=T["bg"], fg=T["fg2"],
                           selectcolor=T["bg3"], activebackground=T["bg"],
                           font=T["font_b"],
                           command=self._on_trigger_change).pack(side="left", padx=8)

        # Dynamic fields frame
        self._dyn_frame = tk.Frame(self, bg=T["bg"])
        self._dyn_frame.pack(fill="x", padx=20, pady=4)
        self._build_daily_fields()

        # Days of week
        self._days_frame = tk.Frame(self, bg=T["bg"])
        self._days_frame.pack(anchor="w", padx=20, pady=4)
        self._day_vars: dict[str, tk.BooleanVar] = {}
        for i, (d, lbl) in enumerate(zip(DAY_NAMES, DAY_LABELS)):
            v = tk.BooleanVar(value=d in self._entry.days)
            self._day_vars[d] = v
            tk.Checkbutton(self._days_frame, text=lbl[:3], variable=v,
                           bg=T["bg"], fg=T["fg2"], selectcolor=T["bg3"],
                           activebackground=T["bg"], font=T["font_s"]
                           ).pack(side="left", padx=3)

        # Max runs
        mr_row = tk.Frame(self, bg=T["bg"]); mr_row.pack(anchor="w", padx=20, pady=6)
        tk.Label(mr_row, text="Max runs (0=unlimited):", bg=T["bg"],
                 fg=T["fg2"], font=T["font_s"]).pack(side="left")
        self._maxruns_v = tk.StringVar(value=str(self._entry.max_runs))
        tk.Entry(mr_row, textvariable=self._maxruns_v, width=6,
                 bg=T["bg3"], fg=T["yellow"], font=T["font_s"],
                 relief="flat").pack(side="left", padx=8)

        # Enabled
        self._enabled_v = tk.BooleanVar(value=self._entry.enabled)
        tk.Checkbutton(self, text="Enabled", variable=self._enabled_v,
                       bg=T["bg"], fg=T["fg2"], selectcolor=T["bg3"],
                       activebackground=T["bg"], font=T["font_b"]
                       ).pack(anchor="w", padx=20)

        bf = tk.Frame(self, bg=T["bg2"], pady=10); bf.pack(fill="x", side="bottom")
        tk.Button(bf, text="  Save  ", bg=T["acc"], fg="white",
                  font=("Segoe UI Semibold", 9), relief="flat", cursor="hand2",
                  command=self._save).pack(side="left", padx=16)
        tk.Button(bf, text="Cancel", bg=T["bg3"], fg=T["fg2"],
                  font=T["font_b"], relief="flat", cursor="hand2",
                  command=self.destroy).pack(side="left")

        self._on_trigger_change()

    def _on_trigger_change(self):
        for w in self._dyn_frame.winfo_children():
            w.destroy()
        t = self._trigger_v.get()
        if t == "daily":
            self._build_daily_fields()
            self._days_frame.pack(anchor="w", padx=20, pady=4)
        elif t == "interval":
            self._build_interval_fields()
            self._days_frame.pack_forget()
        elif t == "once":
            self._build_once_fields()
            self._days_frame.pack_forget()

    def _build_daily_fields(self):
        r = tk.Frame(self._dyn_frame, bg=T["bg"]); r.pack(anchor="w")
        tk.Label(r, text="Time (HH:MM):", bg=T["bg"], fg=T["fg2"],
                 font=T["font_s"]).pack(side="left")
        self._time_v = tk.StringVar(value=self._entry.time_str)
        tk.Entry(r, textvariable=self._time_v, width=8,
                 bg=T["bg3"], fg=T["yellow"], font=T["font_m"],
                 relief="flat").pack(side="left", padx=8)

    def _build_interval_fields(self):
        r = tk.Frame(self._dyn_frame, bg=T["bg"]); r.pack(anchor="w")
        tk.Label(r, text="Every (minutes):", bg=T["bg"], fg=T["fg2"],
                 font=T["font_s"]).pack(side="left")
        self._interval_v = tk.StringVar(value=str(self._entry.interval_min))
        tk.Entry(r, textvariable=self._interval_v, width=6,
                 bg=T["bg3"], fg=T["yellow"], font=T["font_m"],
                 relief="flat").pack(side="left", padx=8)

    def _build_once_fields(self):
        r = tk.Frame(self._dyn_frame, bg=T["bg"]); r.pack(anchor="w")
        tk.Label(r, text="Date (YYYY-MM-DD):", bg=T["bg"],
                 fg=T["fg2"], font=T["font_s"]).pack(side="left")
        today = datetime.date.today().isoformat()
        self._date_v = tk.StringVar(value=self._entry.date_str or today)
        tk.Entry(r, textvariable=self._date_v, width=12,
                 bg=T["bg3"], fg=T["yellow"], font=T["font_m"],
                 relief="flat").pack(side="left", padx=6)
        tk.Label(r, text="Time:", bg=T["bg"], fg=T["fg2"],
                 font=T["font_s"]).pack(side="left")
        self._time_v = tk.StringVar(value=self._entry.time_str)
        tk.Entry(r, textvariable=self._time_v, width=6,
                 bg=T["bg3"], fg=T["yellow"], font=T["font_m"],
                 relief="flat").pack(side="left", padx=4)

    def _browse_flow(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            filetypes=[("Flow JSON", "*.json"), ("All", "*.*")])
        if path:
            self._flow_v.set(path)

    def _save(self):
        e = self._entry
        e.name       = self._name_v.get().strip() or "Unnamed"
        e.flow_path  = self._flow_v.get().strip()
        e.trigger    = self._trigger_v.get()
        e.enabled    = self._enabled_v.get()
        e.days       = [d for d, v in self._day_vars.items() if v.get()]

        try:
            e.max_runs = int(self._maxruns_v.get() or 0)
        except ValueError:
            e.max_runs = 0

        if e.trigger == "daily":
            e.time_str = getattr(self, "_time_v", tk.StringVar()).get()
        elif e.trigger == "interval":
            try:
                e.interval_min = int(getattr(self, "_interval_v",
                                              tk.StringVar(value="60")).get())
            except ValueError:
                e.interval_min = 60
        elif e.trigger == "once":
            e.date_str = getattr(self, "_date_v", tk.StringVar()).get()
            e.time_str = getattr(self, "_time_v", tk.StringVar()).get()

        if not e.flow_path:
            messagebox.showwarning("Missing", "Select a flow file.")
            return

        self._on_save(e)
        self.destroy()


# ── Module-level singleton ────────────────────────────────────────────────────

_scheduler: Optional[Scheduler] = None


def get_scheduler(run_flow_fn: Optional[Callable] = None) -> Scheduler:
    """Get or create the global Scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler(run_flow_fn=run_flow_fn)
    elif run_flow_fn and _scheduler._run_flow_fn is None:
        _scheduler._run_flow_fn = run_flow_fn
    return _scheduler
