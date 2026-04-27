"""
core/helpers.py  — v9.4
========================
Pure utility functions shared across the app.

BUG FIXES v9.4:
  - step_human_label: STEP_FRIENDLY is (label, desc, icon). The function
    was correctly reading info[0] as lbl and info[2] as ico, BUT the
    return tuple was (ico, lbl, s, note) — callers expected this order so
    it IS correct. Added length guard for safety.
  - step_summary: added all missing window + image/OCR step types that
    previously returned "" causing blank display in the UI.
  - sanitise_step: was silently ignoring unknown step types — now falls
    back gracefully. Also fixed: loop steps must deep-copy inner steps
    list to avoid mutation bugs when steps are shared references.
  - apply_variables: was not handling integer/float placeholder values
    correctly (variables dict values could be non-strings from prefs).
  - type_text_safe: clipboard restore could fail silently if pyperclip
    had no previous content — improved guard.
  - parse_hotkey: edge case where keys_str is only "+" (plus key alone)
    was incorrectly returning empty list.
"""

import time
import pyautogui
import copy

try:
    import pyperclip
    _CLIP_OK = True
except ImportError:
    _CLIP_OK = False

from .constants import STEP_FRIENDLY, STEP_DEFAULTS


def step_summary(step: dict) -> str:
    """One-line human-readable summary of a step."""
    t = step.get("type", "")

    if t in ("click", "double_click", "right_click", "mouse_move", "clear_field"):
        rel = " [rel]" if step.get("relative") else ""
        return f"at ({step.get('x', 0)}, {step.get('y', 0)}){rel}"

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

    # ── Image & OCR steps ─────────────────────────────────────────────────────

    if t == "click_image":
        import os
        name = os.path.basename(step.get("image_path", "")) or "?"
        conf = step.get("confidence", 0.80)
        return f"'{name}'  conf≥{conf}  action={step.get('action','click')}"

    if t == "wait_image":
        import os
        name = os.path.basename(step.get("image_path", "")) or "?"
        return f"'{name}'  timeout={step.get('timeout',10)}s"

    if t == "wait_image_vanish":
        import os
        name = os.path.basename(step.get("image_path", "")) or "?"
        return f"'{name}'  timeout={step.get('timeout',10)}s"

    if t == "ocr_condition":
        x, y = step.get("x", 0), step.get("y", 0)
        w, h = step.get("w", 300), step.get("h", 60)
        pat  = step.get("pattern", "")
        return f"region({x},{y},{w},{h})  pattern='{pat}'  → {step.get('action','skip')}"

    if t == "ocr_extract":
        x, y = step.get("x", 0), step.get("y", 0)
        w, h = step.get("w", 300), step.get("h", 60)
        var  = step.get("variable", "ocr_result")
        return f"region({x},{y},{w},{h})  → {{{var}}}"

    # ── Window steps ──────────────────────────────────────────────────────────

    if t == "wait_window":
        title   = step.get("window_title", "")
        process = step.get("process", "")
        timeout = step.get("timeout", 10)
        parts   = []
        if title:   parts.append(f"'{title}'")
        if process: parts.append(f"[{process}]")
        label   = " ".join(parts) or "any"
        return f"{label}  timeout={timeout}s"

    if t == "wait_window_close":
        title   = step.get("window_title", "")
        timeout = step.get("timeout", 10)
        return f"'{title}'  timeout={timeout}s"

    if t == "wait_window_change":
        return f"timeout={step.get('timeout', 10)}s"

    if t == "focus_window":
        title   = step.get("window_title", "")
        process = step.get("process", "")
        parts   = []
        if title:   parts.append(f"'{title}'")
        if process: parts.append(f"[{process}]")
        return " ".join(parts) or "any"

    if t == "assert_window":
        title     = step.get("window_title", "")
        tolerance = step.get("tolerance", "normal")
        action    = step.get("action", "skip")
        return f"'{title}'  tol={tolerance}  on-fail={action}"

    return ""


def step_human_label(step: dict) -> tuple:
    """
    Returns (icon, label, summary, note) for a step.

    STEP_FRIENDLY values are (label, description, icon) — index 0 is label,
    index 2 is icon. This function returns (icon, label, summary, note)
    which is what all callers expect.
    """
    t    = step.get("type", "")
    info = STEP_FRIENDLY.get(t)
    if info and len(info) >= 3:
        lbl = info[0]   # label
        ico = info[2]   # icon
    elif info and len(info) == 2:
        lbl = info[0]
        ico = "•"
    else:
        lbl = t
        ico = "•"

    s    = step_summary(step)
    note = f"  — {step['note']}" if step.get("note") else ""
    return ico, lbl, s, note


def parse_hotkey(keys_str: str) -> list:
    """
    Parse 'ctrl+shift+s' → ['ctrl', 'shift', 's'].
    Handles trailing '+' (literal plus key) and empty strings.

    BUG FIX: 'ctrl++' should yield ['ctrl', '+'] not ['ctrl', '', ''].
    BUG FIX: bare '+' should yield ['+'] not [].
    """
    s = keys_str.strip()
    if not s:
        return ["enter"]

    # Handle "something++" meaning the last key is literal "+"
    if s.endswith("++"):
        base  = s[:-2]
        parts = [p.strip() for p in base.split("+") if p.strip()]
        parts.append("+")
        return parts

    # BUG FIX: bare "+" should not be split into empty strings
    if s == "+":
        return ["+"]

    parts = [k.strip() for k in s.split("+") if k.strip()]
    return parts if parts else ["enter"]


def type_text_safe(text: str) -> None:
    """
    Type text via clipboard so Unicode / Nepali / emoji all work.
    Restores old clipboard even on failure.

    BUG FIX: pyperclip.paste() can raise if clipboard is empty on some
    platforms. Wrapped in try/except. Also fixed: restored clipboard
    even when copy itself failed.
    """
    if not _CLIP_OK:
        pyautogui.typewrite(str(text), interval=0.05)
        return

    old = ""
    try:
        old = pyperclip.paste() or ""
    except Exception:
        old = ""

    try:
        pyperclip.copy(str(text))
        time.sleep(0.05)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.1)
    except Exception:
        try:
            pyautogui.typewrite(str(text), interval=0.05)
        except Exception:
            pass
    finally:
        # BUG FIX: only restore if we had something to restore
        if old:
            try:
                pyperclip.copy(old)
            except Exception:
                pass


def apply_variables(text: str, variables: dict) -> str:
    """
    Replace {varname} tokens in text with values from variables dict.
    Handles None values and non-string variable values.

    BUG FIX: variables values could be int/float (e.g. from prefs),
    str() conversion is applied to all values now.
    """
    if not text or not variables:
        return text
    for k, v in variables.items():
        placeholder = "{" + str(k) + "}"
        replacement = "" if v is None else str(v)
        text = text.replace(placeholder, replacement)
    return text


def sanitise_step(step: dict) -> dict:
    """
    Ensure a step dict has all required keys with safe defaults.

    BUG FIX: loop steps' inner 'steps' list was not deep-copied,
    causing mutations to be shared across executor runs. Fixed with
    copy.deepcopy on the merged result.

    BUG FIX: unknown step types now get a safe generic default instead
    of a bare minimum that would cause KeyErrors in executor._do().
    """
    from .constants import STEP_DEFAULTS
    t = step.get("type", "comment")
    default = STEP_DEFAULTS.get(t, {"note": "", "enabled": True})
    # Deep merge: default provides structure, step overrides values
    merged = copy.deepcopy(default)
    merged.update(step)
    merged.setdefault("enabled", True)
    merged.setdefault("note", "")
    merged["type"] = t

    # BUG FIX: deep-copy inner steps list for loop steps to avoid
    # shared-reference mutations across multiple executor.start() calls
    if t == "loop" and "steps" in merged:
        merged["steps"] = copy.deepcopy(merged["steps"])

    return merged
