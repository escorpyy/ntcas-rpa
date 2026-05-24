"""
main.py  —  Swastik RPA v9.5
=============================
Entry point.  Run with:   python main.py

NEW v9.5:
  Feature 2 — Resume-from-failure checkpoint system
  Feature 3 — Column-mapped variables (multi-column Excel/CSV)
  Feature 4 — If/else branching + label/goto step types

All three features are integrated directly into:
  core/executor.py      (checkpoint, row_vars, if_condition/_do)
  core/constants.py     (if_condition, label, goto step definitions)
  core/checkpoint.py    (CheckpointManager)
  core/column_mapper.py (ColumnMapper)
  ui/app.py             (resume dialog, column mapper dialog, row_vars launch)
  ui/panels.py          (NameListPanel callback, FlowPanel._edit routing)
  ui/dialogs.py         (_build_new_step_fields handles if_condition/label/goto)
  ui/resume_dialog.py   (ResumeDialog, check_and_show_resume_dialog)
  ui/if_editor.py       (IfConditionEditor — side-by-side branch editor)

No monkey-patching anywhere.

Dependencies:
    pip install pyautogui pyperclip pandas openpyxl Pillow pynput

Optional (Vision Agent):
    pip install ollama
    ollama pull llava
"""

import sys, os

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# ── Hard dependency check ─────────────────────────────────────────────────────

missing = []

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE    = 0.05
except ImportError:
    missing.append("pyautogui")

try:
    import pandas  # noqa: F401
except ImportError:
    missing.append("pandas openpyxl")

try:
    from PIL import Image  # noqa: F401
except ImportError:
    missing.append("Pillow")

if missing:
    print("❌  Missing packages.  Run:\n")
    print(f"    pip install {' '.join(missing)}\n")
    sys.exit(1)

# ── Optional hints ────────────────────────────────────────────────────────────

try:
    import pyperclip  # noqa: F401
except ImportError:
    print("[warn] pyperclip not installed — Clip Type steps fall back to typewrite.")

try:
    from pynput import keyboard  # noqa: F401
except ImportError:
    print("[warn] pynput not installed — F10/F11 hotkeys and Macro Recorder unavailable.")

# ── Launch ────────────────────────────────────────────────────────────────────

from ui.app import App

if __name__ == "__main__":
    app = App()
    app.mainloop()
