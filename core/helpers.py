"""
core/helpers.py
===============
Pure utility functions shared across the app:
  - step_summary / step_human_label
  - parse_hotkey
  - type_text_safe
  - apply_variables
"""

import time
import pyautogui

try:
    import pyperclip
    _CLIP_OK = True
except ImportError:
    _CLIP_OK = False

from .constants import STEP_FRIENDLY


def step_summary(step: dict) -> str:
    t = step["type"]
    if t in ("click", "double_click", "right_click", "mouse_move", "clear_field"):
        return f"at ({step.get('x', 0)}, {step.get('y', 0)})"
    if t == "scroll":
        return f"({step.get('x',0)},{step.get('y',0)}) {step.get('direction','down')} ×{step.get('clicks',3)}"
    if t == "hotkey":
        return step.get("keys", "")
    if t in ("type_text", "clip_type"):
        txt = step.get("text", "")
        return (txt[:28] + "…") if len(txt) > 28 else txt
    if t == "wait":
        return f"{step.get('seconds', 1)} seconds"
    if t in ("pagedown", "pageup"):
        return f"×{step.get('times', 1)}"
    if t == "key_repeat":
        return f"{step.get('key','tab')} × {step.get('times', 1)}"
    if t == "hold_key":
        return f"hold {step.get('key','?')} for {step.get('seconds', 1.0)}s"
    if t == "loop":
        return f"repeat {step.get('times',2)} times  ({len(step.get('steps', []))} steps inside)"
    if t == "screenshot":
        return step.get("folder", "screenshots")
    if t == "condition":
        return f"window contains: '{step.get('window_title', '')}'"
    if t == "comment":
        txt = step.get("text", "")
        return (txt[:30] + "…") if len(txt) > 30 else txt
    return ""


def step_human_label(step: dict) -> tuple:
    t    = step["type"]
    ico  = STEP_FRIENDLY[t][2] if t in STEP_FRIENDLY else "•"
    lbl  = STEP_FRIENDLY[t][0] if t in STEP_FRIENDLY else t
    s    = step_summary(step)
    note = f"  — {step['note']}" if step.get("note") else ""
    return ico, lbl, s, note


def parse_hotkey(keys_str: str) -> list:
    """Parse 'ctrl+shift+s' → ['ctrl','shift','s'], handles trailing '++'."""
    s = keys_str.strip()
    if s.endswith("++"):
        parts = [p.strip() for p in s[:-2].rstrip("+").split("+") if p.strip()]
        parts.append("+")
        return parts
    return [k.strip() for k in s.split("+") if k.strip()]


def type_text_safe(text: str) -> None:
    """Type text via clipboard so Unicode / Nepali / emoji all work."""
    if _CLIP_OK:
        old = ""
        try:
            old = pyperclip.paste()
        except Exception:
            pass
        pyperclip.copy(text)
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.1)
        try:
            pyperclip.copy(old)
        except Exception:
            pass
    else:
        pyautogui.typewrite(text, interval=0.05)


def apply_variables(text: str, variables: dict) -> str:
    """Replace {varname} tokens with values from variables dict."""
    for k, v in variables.items():
        text = text.replace("{" + k + "}", str(v))
    return text
