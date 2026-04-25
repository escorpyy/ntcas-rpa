"""
core/constants.py  — v9.4
==========================
All static data: APP_VERSION, LANG, theme (T), step types,
step friendly labels, step defaults, step colors, templates,
prefs helpers.

CHANGES v9.4:
  - New step types: wait_window, wait_window_close, wait_window_change,
    focus_window, assert_window
  - Relative coordinate support added to click step defaults
  - _PREFS_DEFAULTS includes overlay position + new window-step prefs
  - STEP_CATEGORIES updated with Window Actions group
"""

import os, json, shutil, tempfile

APP_VERSION = "9.4"
_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── User prefs directory ──────────────────────────────────────────────────────

_PREFS_DIR  = os.path.join(os.path.expanduser("~"), ".swastik")
os.makedirs(_PREFS_DIR, exist_ok=True)
RECENT_FILE = os.path.join(_PREFS_DIR, "recent.json")
PREFS_FILE  = os.path.join(_PREFS_DIR, "prefs.json")

# ── Language strings ──────────────────────────────────────────────────────────

LANG = {
    "en": {
        "title":         "Swastik RPA",
        "subtitle":      "Automation Flow Builder",
        "names_tab":     "Name List",
        "flow_tab":      "Build Flow",
        "run_tab":       "Run",
        "help_tab":      "Help",
        "agent_tab":     "Agent",
        "add_step":      "+ Add Step",
        "start":         "▶  Start Automation",
        "stop":          "■  Stop",
        "pause":         "⏸  Pause",
        "resume":        "▶  Resume",
        "browse":        "Load from Excel / CSV",
        "paste_names":   "Or paste names here (one per line):",
        "templates":     "Start from a template",
        "names_loaded":  "names loaded",
        "ready":         "Ready to run",
        "running":       "Running…",
        "done":          "Finished",
        "countdown":     "Starting in",
        "seconds":       "seconds — switch to your app!",
        "between":       "Wait between each name (seconds)",
        "countdown_lbl": "Startup delay (seconds)",
        "dry_run":       "Practice mode (no actual clicks)",
        "save_flow":     "Save Flow",
        "load_flow":     "Load Flow",
        "clear_log":     "Clear",
        "export_log":    "Export Log",
        "test_single":   "Test with one name",
        "no_names_warn": "Please add some names first.",
        "no_steps_warn": "Please add steps to your flow first.",
        "step_search":   "Search steps…",
        "undo":          "Undo",
        "redo":          "Redo",
        "duplicate":     "Duplicate",
        "delete":        "Delete",
        "move_up":       "Move Up",
        "move_down":     "Move Down",
        "edit":          "Edit",
        "copy_flow":     "Copy other panel's steps",
        "clear_all":     "Clear All",
        "find_replace":  "Find & Replace",
        "variables":     "Variables",
        "retries":       "Retries on failure",
        "recorder":      "🎙 Macro Recorder",
        "vision_agent":  "🚀 Vision Agent",
        "debugger":      "🐛 Flow Debugger",
    },
    "np": {
        "title":         "Swastik RPA",
        "subtitle":      "स्वचालन फ्लो बिल्डर",
        "names_tab":     "नाम सूची",
        "flow_tab":      "फ्लो बनाउनुहोस्",
        "run_tab":       "चलाउनुहोस्",
        "help_tab":      "सहायता",
        "agent_tab":     "एजेन्ट",
        "add_step":      "+ चरण थप्नुहोस्",
        "start":         "▶  स्वचालन सुरु गर्नुहोस्",
        "stop":          "■  रोक्नुहोस्",
        "pause":         "⏸  पज",
        "resume":        "▶  जारी राख्नुहोस्",
        "browse":        "Excel / CSV बाट लोड गर्नुहोस्",
        "paste_names":   "वा यहाँ नाम टाँस्नुहोस् (एक प्रति लाइन):",
        "templates":     "टेम्प्लेटबाट सुरु गर्नुहोस्",
        "names_loaded":  "नाम लोड भयो",
        "ready":         "चलाउन तयार",
        "running":       "चलिरहेको छ…",
        "done":          "सकियो",
        "countdown":     "सुरु हुँदैछ",
        "seconds":       "सेकेन्डमा — आफ्नो एपमा जानुहोस्!",
        "between":       "प्रत्येक नाम बीच प्रतीक्षा (सेकेन्ड)",
        "countdown_lbl": "सुरु हुनु अघिको समय (सेकेन्ड)",
        "dry_run":       "अभ्यास मोड (कुनै क्लिक हुँदैन)",
        "save_flow":     "फ्लो सेभ गर्नुहोस्",
        "load_flow":     "फ्लो लोड गर्नुहोस्",
        "clear_log":     "मेटाउनुहोस्",
        "export_log":    "लग निर्यात",
        "test_single":   "एक नामले परीक्षण गर्नुहोस्",
        "no_names_warn": "कृपया पहिले केही नाम थप्नुहोस्।",
        "no_steps_warn": "कृपया पहिले चरणहरू थप्नुहोस्।",
        "step_search":   "चरण खोज्नुहोस्…",
        "undo":          "पूर्ववत",
        "redo":          "फेरि गर्नुहोस्",
        "duplicate":     "नक्कल",
        "delete":        "मेटाउनुहोस्",
        "move_up":       "माथि जानुहोस्",
        "move_down":     "तल जानुहोस्",
        "edit":          "सम्पादन",
        "copy_flow":     "अर्को प्यानलका चरणहरू नक्कल गर्नुहोस्",
        "clear_all":     "सबै हटाउनुहोस्",
        "find_replace":  "खोज र बदल्नुहोस्",
        "variables":     "चल",
        "retries":       "असफलमा पुनः प्रयास",
        "recorder":      "🎙 म्याक्रो रेकर्डर",
        "vision_agent":  "🚀 भिजन एजेन्ट",
        "debugger":      "🐛 फ्लो डिबगर",
    },
}

_lang = "en"

def L(key: str) -> str:
    return LANG.get(_lang, LANG["en"]).get(key, LANG["en"].get(key, key))

def set_lang(lang: str) -> None:
    global _lang
    if lang in LANG:
        _lang = lang

# ── Preferences helpers ───────────────────────────────────────────────────────

_PREFS_DEFAULTS: dict = {
    # Run
    "countdown":    5,
    "between":      1.0,
    "dry_run":      False,
    "fail_ss":      False,
    "retries":      0,
    # Appearance / language
    "lang":         "en",
    "ui_font":      "Segoe UI",
    "ui_font_size": 9,
    "theme_overrides": {},
    # Behaviour
    "auto_minimise":    True,
    "confirm_clear":    True,
    "warn_zero_coords": True,
    "show_step_count":  True,
    "undo_depth":       40,
    # Paths
    "screenshot_folder": "",
    "flow_folder":       "",
    "export_folder":     "",
    # Shortcuts
    "shortcuts": {},
    "recorder_shortcuts": {},
    # Automation advanced
    "type_interval":    0.05,
    "pyautogui_pause":  0.05,
    "failsafe":         True,
    "failsafe_corner":  "top-left",
    # Macro recorder
    "recorder_auto_wait_threshold": 1.5,
    "recorder_dbl_click_window":    0.35,
    "recorder_wait_default":        1.0,
    "recorder_auto_wait_on":        True,
    "recorder_topmost":             True,
    # Overlay position
    "overlay_x": None,
    "overlay_y": None,
    # Vision agent
    "agent_model":      "llava",
    "agent_max_steps":  30,
    "agent_confidence": 0.35,
    "agent_settle_time":0.6,
    "agent_show_log":   True,
    # Window step defaults
    "window_match_timeout": 10,
    "window_validate_actions": False,
    # Recent
    "recent_steps": [],
}


def load_json_file(path: str, default):
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except json.JSONDecodeError as e:
        print(f"[prefs] JSON parse error in {path}: {e}")
    except OSError as e:
        print(f"[prefs] Could not read {path}: {e}")
    except Exception as e:
        print(f"[prefs] Unexpected error loading {path}: {e}")
    return default


def save_json_file(path: str, data) -> None:
    try:
        dir_  = os.path.dirname(path) or "."
        fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            shutil.move(tmp, path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except Exception as e:
        print(f"[prefs] Could not save {path}: {e}")


_prefs: dict = {**_PREFS_DEFAULTS, **load_json_file(PREFS_FILE, {})}


def save_prefs() -> None:
    save_json_file(PREFS_FILE, _prefs)


# ── Theme ─────────────────────────────────────────────────────────────────────

T: dict = {
    "bg":        "#0d1117",
    "bg2":       "#161b22",
    "bg3":       "#21262d",
    "bg4":       "#30363d",
    "border":    "#30363d",
    "fg":        "#e6edf3",
    "fg2":       "#8b949e",
    "fg3":       "#484f58",
    "acc":       "#388bfd",
    "acc_dark":  "#1f6feb",
    "green":     "#3fb950",
    "green_bg":  "#1a2e1a",
    "red":       "#f85149",
    "red_bg":    "#2e1a1a",
    "yellow":    "#d29922",
    "yellow_bg": "#2e2000",
    "purple":    "#bc8cff",
    "cyan":      "#39c5cf",
    "orange":    "#e3b341",
    "disabled":  "#30363d",
    "font_h":    ("Segoe UI Semibold", 11),
    "font_b":    ("Segoe UI", 9),
    "font_s":    ("Segoe UI", 8),
    "font_m":    ("Consolas", 9),
}

for _k, _v in _prefs.get("theme_overrides", {}).items():
    if _k in T:
        T[_k] = _v

# ── Step colors ───────────────────────────────────────────────────────────────

STEP_COLORS: dict = {
    "click":              "#388bfd",
    "double_click":       "#388bfd",
    "right_click":        "#bc8cff",
    "mouse_move":         "#39c5cf",
    "hotkey":             "#f78166",
    "type_text":          "#3fb950",
    "clip_type":          "#3fb950",
    "clear_field":        "#d29922",
    "wait":               "#8b949e",
    "pagedown":           "#8b949e",
    "pageup":             "#8b949e",
    "scroll":             "#8b949e",
    "key_repeat":         "#f78166",
    "hold_key":           "#ff9966",
    "loop":               "#e3b341",
    "screenshot":         "#bc8cff",
    "condition":          "#39c5cf",
    "comment":            "#484f58",
    # New window steps
    "wait_window":        "#39c5cf",
    "wait_window_close":  "#f78166",
    "wait_window_change": "#d29922",
    "focus_window":       "#388bfd",
    "assert_window":      "#3fb950",
}

# ── Step definitions ──────────────────────────────────────────────────────────

STEP_TYPES: list = [
    "click", "double_click", "right_click", "mouse_move",
    "hotkey", "type_text", "clip_type", "clear_field",
    "wait", "pagedown", "pageup", "scroll", "key_repeat", "hold_key",
    "loop", "screenshot", "condition", "comment",
    # Window steps
    "wait_window", "wait_window_close", "wait_window_change",
    "focus_window", "assert_window",
]

STEP_FRIENDLY: dict = {
    "click":        ("Mouse Click",              "Click anywhere on the screen",                        "🖱"),
    "double_click": ("Double Click",             "Double-click to open files or folders",               "🖱"),
    "right_click":  ("Right Click",              "Right-click to open a context menu",                  "🖱"),
    "mouse_move":   ("Move Mouse",               "Move mouse to a position without clicking",           "➤"),
    "hotkey":       ("Press Keys",               "Press a keyboard shortcut (Ctrl+S, Enter…)",          "⌨"),
    "type_text":    ("Type Text (English)",      "Type English text into any field",                    "⌨"),
    "clip_type":    ("Type Text (Any language)", "Type text including Nepali, numbers, emoji",          "📋"),
    "clear_field":  ("Clear a Field",            "Click a field and erase everything in it",            "⌫"),
    "wait":         ("Wait / Pause",             "Wait for the app to load before continuing",          "⏳"),
    "pagedown":     ("Scroll Down (Page)",       "Press Page Down to scroll",                           "⬇"),
    "pageup":       ("Scroll Up (Page)",         "Press Page Up to scroll",                             "⬆"),
    "scroll":       ("Mouse Scroll",             "Scroll up or down at a specific position",            "↕"),
    "key_repeat":   ("Repeat a Key",             "Press Tab, Enter etc. multiple times",                "🔁"),
    "hold_key":     ("Hold a Key",               "Press and hold a key for N seconds",                  "⏱"),
    "loop":         ("Repeat a Group",           "Repeat a set of steps N times",                       "🔄"),
    "screenshot":   ("Take Screenshot",          "Save a screenshot to a folder",                       "📸"),
    "condition":    ("Check Window (title)",     "Skip steps if wrong window title is active",          "❓"),
    "comment":      ("Add a Note",               "Label a section of your flow",                        "💬"),
    # Window steps
    "wait_window":        ("Wait for Window",        "Pause until a specific window becomes active",    "🪟"),
    "wait_window_close":  ("Wait for Window Close",  "Pause until a specific window closes",            "🚪"),
    "wait_window_change": ("Wait for Window Change", "Pause until the active window changes",           "🔄"),
    "focus_window":       ("Focus / Bring Window",   "Bring a window to the foreground",               "🎯"),
    "assert_window":      ("Assert Window",          "Fail if the wrong window is active",              "✅"),
}

STEP_DEFAULTS: dict = {
    "click":        {"x": 0, "y": 0, "relative": False, "note": "", "enabled": True},
    "double_click": {"x": 0, "y": 0, "relative": False, "note": "", "enabled": True},
    "right_click":  {"x": 0, "y": 0, "relative": False, "note": "", "enabled": True},
    "mouse_move":   {"x": 0, "y": 0, "relative": False, "note": "", "enabled": True},
    "hotkey":       {"keys": "enter", "note": "", "enabled": True},
    "type_text":    {"text": "{name}", "note": "", "enabled": True},
    "clip_type":    {"text": "{name}", "note": "", "enabled": True},
    "clear_field":  {"x": 0, "y": 0, "note": "", "enabled": True},
    "wait":         {"seconds": 1.0, "note": "", "enabled": True},
    "pagedown":     {"times": 1, "note": "", "enabled": True},
    "pageup":       {"times": 1, "note": "", "enabled": True},
    "scroll":       {"x": 0, "y": 0, "direction": "down", "clicks": 3, "note": "", "enabled": True},
    "key_repeat":   {"key": "tab", "times": 1, "note": "", "enabled": True},
    "hold_key":     {"key": "space", "seconds": 1.0, "note": "", "enabled": True},
    "loop":         {"times": 2, "steps": [], "note": "", "enabled": True},
    "screenshot":   {"folder": "screenshots", "note": "", "enabled": True},
    "condition":    {"window_title": "", "action": "skip", "note": "", "enabled": True},
    "comment":      {"text": "", "note": "", "enabled": True},
    # Window steps
    "wait_window":        {"window_title": "", "process": "", "hwnd": 0,
                           "timeout": 10, "note": "", "enabled": True},
    "wait_window_close":  {"window_title": "", "process": "", "hwnd": 0,
                           "timeout": 10, "note": "", "enabled": True},
    "wait_window_change": {"timeout": 10, "note": "", "enabled": True},
    "focus_window":       {"window_title": "", "process": "", "hwnd": 0,
                           "restore_minimized": True, "note": "", "enabled": True},
    "assert_window":      {"window_title": "", "process": "", "hwnd": 0,
                           "tolerance": "normal", "action": "skip",
                           "note": "", "enabled": True},
}

# ── Step categories ───────────────────────────────────────────────────────────

STEP_CATEGORIES: dict = {
    "🖱  Mouse Actions": [
        "click", "double_click", "right_click", "mouse_move", "scroll", "clear_field",
    ],
    "⌨  Keyboard": [
        "hotkey", "type_text", "clip_type", "key_repeat", "hold_key",
    ],
    "⏱  Timing & Flow": [
        "wait", "pagedown", "pageup", "loop",
    ],
    "🪟  Window Control": [
        "wait_window", "wait_window_close", "wait_window_change",
        "focus_window", "assert_window",
    ],
    "🔧  Utilities": [
        "screenshot", "condition", "comment",
    ],
}

# ── Templates ─────────────────────────────────────────────────────────────────

TEMPLATES: dict = {
    "WhatsApp Message": {
        "desc": "Type a message and send it on WhatsApp Web",
        "icon": "💬",
        "steps": [
            {"type": "click",    "x": 0, "y": 0, "relative": False, "note": "Click message box", "enabled": True},
            {"type": "clip_type","text": "{name}", "note": "Type the message", "enabled": True},
            {"type": "hotkey",   "keys": "enter",  "note": "Send",             "enabled": True},
            {"type": "wait",     "seconds": 1.0,   "note": "Wait for delivery","enabled": True},
        ],
    },
    "Fill & Save Form": {
        "desc": "Click a field, clear it, type a name, then save",
        "icon": "📝",
        "steps": [
            {"type": "focus_window",  "window_title": "", "process": "", "hwnd": 0, "note": "Ensure correct window", "enabled": True},
            {"type": "click",         "x": 0, "y": 0, "relative": False, "note": "Click the field", "enabled": True},
            {"type": "clear_field",   "x": 0, "y": 0, "note": "Clear old value", "enabled": True},
            {"type": "clip_type",     "text": "{name}",   "note": "Type new value",  "enabled": True},
            {"type": "hotkey",        "keys": "ctrl+s",   "note": "Save",            "enabled": True},
            {"type": "wait",          "seconds": 1.5,     "note": "Wait for save",   "enabled": True},
        ],
    },
    "Open & Search": {
        "desc": "Click a search box, type a name, press Enter",
        "icon": "🔍",
        "steps": [
            {"type": "click",       "x": 0, "y": 0, "relative": False, "note": "Click search box","enabled": True},
            {"type": "clear_field", "x": 0, "y": 0,    "note": "Clear old search","enabled": True},
            {"type": "clip_type",   "text": "{name}",   "note": "Type name",       "enabled": True},
            {"type": "hotkey",      "keys": "enter",    "note": "Search",          "enabled": True},
            {"type": "wait",        "seconds": 1.5,     "note": "Wait for results","enabled": True},
        ],
    },
    "Open & Print": {
        "desc": "Open each item and print it",
        "icon": "🖨",
        "steps": [
            {"type": "click",  "x": 0, "y": 0, "relative": False, "note": "Click item",  "enabled": True},
            {"type": "wait",   "seconds": 1.0,  "note": "Wait to open",      "enabled": True},
            {"type": "hotkey", "keys": "ctrl+p", "note": "Print",            "enabled": True},
            {"type": "hotkey", "keys": "enter",  "note": "Confirm print",    "enabled": True},
            {"type": "wait",   "seconds": 2.0,   "note": "Wait for print",   "enabled": True},
        ],
    },
    "Login Flow": {
        "desc": "Focus window, enter credentials, submit",
        "icon": "🔐",
        "steps": [
            {"type": "focus_window",  "window_title": "", "process": "", "hwnd": 0,
             "note": "Bring login window to front", "enabled": True},
            {"type": "click",    "x": 0, "y": 0, "relative": False, "note": "Click username", "enabled": True},
            {"type": "clip_type","text": "{name}",     "note": "Type username",  "enabled": True},
            {"type": "hotkey",   "keys": "tab",        "note": "Go to password", "enabled": True},
            {"type": "clip_type","text": "{password}", "note": "Type password",  "enabled": True},
            {"type": "hotkey",   "keys": "enter",      "note": "Submit login",   "enabled": True},
            {"type": "wait_window", "window_title": "", "process": "", "hwnd": 0,
             "timeout": 10, "note": "Wait for dashboard", "enabled": True},
        ],
    },
    "Copy & Paste": {
        "desc": "Select all in a field, copy, click target, paste",
        "icon": "📋",
        "steps": [
            {"type": "click",  "x": 0, "y": 0, "relative": False, "note": "Click source",  "enabled": True},
            {"type": "hotkey", "keys": "ctrl+a",   "note": "Select all", "enabled": True},
            {"type": "hotkey", "keys": "ctrl+c",   "note": "Copy",       "enabled": True},
            {"type": "click",  "x": 0, "y": 0, "relative": False, "note": "Click target",  "enabled": True},
            {"type": "hotkey", "keys": "ctrl+v",   "note": "Paste",      "enabled": True},
        ],
    },
}
