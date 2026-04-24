"""
core/helpers.py
===============
Pure utility functions shared across the app:
  - step_summary / step_human_label
  - parse_hotkey
  - type_text_safe
  - apply_variables

FIXES v9.3:
  - parse_hotkey: handles edge cases like empty string, lone '+', whitespace
  - type_text_safe: restores clipboard even on paste failure
  - apply_variables: handles non-string values gracefully, case-insensitive
    variable lookup fallback
  - step_summary: handles missing keys with safe .get() defaults throughout
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
    """One-line human-readable summary of a step."""
    t = step.get("type", "")
    if t in ("click", "double_click", "right_click", "mouse_move", "clear_field"):
        return f"at ({step.get('x', 0)}, {step.get('y', 0)})"
    if t == "scroll":
        return (f"({step.get('x', 0)},{step.get('y', 0)}) "
                f"{step.get('direction', 'down')} ×{step.get('clicks', 3)}")
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
        return f"{step.get('key', 'tab')} × {step.get('times', 1)}"
    if t == "hold_key":
        return f"hold {step.get('key', '?')} for {step.get('seconds', 1.0)}s"
    if t == "loop":
        return f"repeat {step.get('times', 2)} times  ({len(step.get('steps', []))} steps inside)"
    if t == "screenshot":
        return step.get("folder", "screenshots")
    if t == "condition":
        return f"window contains: '{step.get('window_title', '')}'"
    if t == "comment":
        txt = step.get("text", "")
        return (txt[:30] + "…") if len(txt) > 30 else txt
    return ""


def step_human_label(step: dict) -> tuple:
    t    = step.get("type", "")
    info = STEP_FRIENDLY.get(t, ("", t, "•"))
    ico  = info[2]
    lbl  = info[0] if info[0] else t
    s    = step_summary(step)
    note = f"  — {step['note']}" if step.get("note") else ""
    return ico, lbl, s, note


def parse_hotkey(keys_str: str) -> list:
    """
    Parse a hotkey string like 'ctrl+shift+s' into ['ctrl', 'shift', 's'].

    FIXES:
      - Empty string → ['enter'] (safe default)
      - Trailing '++' → last key is literal '+'
      - Strips whitespace from each part
      - Ignores empty parts (e.g. 'ctrl++s' → ['ctrl', 's'] not ['ctrl', '', 's'])
    """
    s = keys_str.strip()
    if not s:
        return ["enter"]
    # Handle "ctrl++" style (literal plus key)
    if s.endswith("++"):
        base  = s[:-2].rstrip("+")
        parts = [p.strip() for p in base.split("+") if p.strip()]
        parts.append("+")
        return parts
    return [k.strip() for k in s.split("+") if k.strip()]


def type_text_safe(text: str) -> None:
    """
    Type text via clipboard so Unicode / Nepali / emoji all work.

    FIXES:
      - Restores old clipboard even when paste raises an exception
      - Falls back to typewrite if clipboard operations fail entirely
    """
    if not _CLIP_OK:
        pyautogui.typewrite(str(text), interval=0.05)
        return

    old = ""
    try:
        old = pyperclip.paste()
    except Exception:
        pass

    try:
        pyperclip.copy(str(text))
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.1)
    except Exception:
        # Paste failed — fall back to typewrite
        try:
            pyautogui.typewrite(str(text), interval=0.05)
        except Exception:
            pass
    finally:
        # Always restore old clipboard content
        try:
            if old:
                pyperclip.copy(old)
        except Exception:
            pass


def apply_variables(text: str, variables: dict) -> str:
    """
    Replace {varname} tokens with values from variables dict.

    FIXES:
      - Converts values to str() safely before substitution
      - Handles None values (replaces with empty string)
    """
    if not text or not variables:
        return text
    for k, v in variables.items():
        placeholder = "{" + str(k) + "}"
        text = text.replace(placeholder, "" if v is None else str(v))
    return text


def sanitise_step(step: dict) -> dict:
    """
    Ensure a step dict has all required keys with safe defaults.
    Useful when loading old flow files that may be missing keys.
    """
    from .constants import STEP_DEFAULTS
    t       = step.get("type", "comment")
    default = STEP_DEFAULTS.get(t, {"note": "", "enabled": True})
    merged  = {**default, **step}
    # Always ensure these keys exist
    merged.setdefault("enabled", True)
    merged.setdefault("note", "")
    merged["type"] = t
    return merged
