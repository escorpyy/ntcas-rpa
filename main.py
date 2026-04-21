"""
main.py  –  Swastik RPA v9.2
=============================
Entry point. Run with:
    python main.py

Dependencies:
    pip install pyautogui pyperclip pandas openpyxl Pillow pynput

Optional (Vision Agent):
    pip install ollama
    ollama pull llava
"""

import sys, os

# Ensure project root is on sys.path so 'core', 'ui', 'agent' imports work.
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

# ── Optional dependency hints (non-fatal) ─────────────────────────────────────

try:
    import pyperclip  # noqa: F401
except ImportError:
    print("[warn] pyperclip not installed — Clip Type steps will fall back to typewrite.")

try:
    from pynput import keyboard  # noqa: F401
except ImportError:
    print("[warn] pynput not installed — F10/F11 hotkeys and Macro Recorder unavailable.")

# ── Launch ────────────────────────────────────────────────────────────────────

from ui.app import App

if __name__ == "__main__":
    app = App()
    app.mainloop()
