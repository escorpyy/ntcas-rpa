"""
core/constants.py  — v9.5
==========================
All static data. v9.5 adds if_condition, label, goto step types directly.
"""

import os, json, shutil, tempfile, copy

APP_VERSION = "9.5"
_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_PREFS_DIR  = os.path.join(os.path.expanduser("~"), ".swastik")
os.makedirs(_PREFS_DIR, exist_ok=True)
RECENT_FILE = os.path.join(_PREFS_DIR, "recent.json")
PREFS_FILE  = os.path.join(_PREFS_DIR, "prefs.json")

LANG = {
    "en": {
        "title":"Swastik RPA","subtitle":"Automation Flow Builder",
        "names_tab":"Name List","flow_tab":"Build Flow","run_tab":"Run",
        "help_tab":"Help","agent_tab":"Agent","add_step":"+ Add Step",
        "start":"\u25b6  Start Automation","stop":"\u25a0  Stop",
        "pause":"\u23f8  Pause","resume":"\u25b6  Resume",
        "browse":"Load from Excel / CSV",
        "paste_names":"Or paste names here (one per line):",
        "templates":"Start from a template","names_loaded":"names loaded",
        "ready":"Ready to run","running":"Running\u2026","done":"Finished",
        "countdown":"Starting in","seconds":"seconds \u2014 switch to your app!",
        "between":"Wait between each name (seconds)",
        "countdown_lbl":"Startup delay (seconds)",
        "dry_run":"Practice mode (no actual clicks)",
        "save_flow":"Save Flow","load_flow":"Load Flow",
        "clear_log":"Clear","export_log":"Export Log",
        "test_single":"Test with one name",
        "no_names_warn":"Please add some names first.",
        "no_steps_warn":"Please add steps to your flow first.",
        "step_search":"Search steps\u2026","undo":"Undo","redo":"Redo",
        "duplicate":"Duplicate","delete":"Delete","move_up":"Move Up",
        "move_down":"Move Down","edit":"Edit",
        "copy_flow":"Copy other panel\u2019s steps","clear_all":"Clear All",
        "find_replace":"Find & Replace","variables":"Variables",
        "retries":"Retries on failure","recorder":"\U0001f399 Macro Recorder",
        "vision_agent":"\U0001f680 Vision Agent","debugger":"\U0001f41b Flow Debugger",
    },
    "np": {
        "title":"Swastik RPA","subtitle":"\u0938\u094d\u0935\u091a\u093e\u0932\u0928 \u092b\u094d\u0932\u094b \u092c\u093f\u0932\u094d\u0921\u0930",
        "names_tab":"\u0928\u093e\u092e \u0938\u0942\u091a\u0940",
        "flow_tab":"\u092b\u094d\u0932\u094b \u092c\u0928\u093e\u0909\u0928\u0941\u0939\u094b\u0938\u094d",
        "run_tab":"\u091a\u0932\u093e\u0909\u0928\u0941\u0939\u094b\u0938\u094d",
        "help_tab":"\u0938\u0939\u093e\u092f\u0924\u093e","agent_tab":"\u090f\u091c\u0947\u0928\u094d\u091f",
        "add_step":"+ \u091a\u0930\u0923 \u0925\u092a\u094d\u0928\u0941\u0939\u094b\u0938\u094d",
        "start":"\u25b6  \u0938\u094d\u0935\u091a\u093e\u0932\u0928 \u0938\u0941\u0930\u0941 \u0917\u0930\u094d\u0928\u0941\u0939\u094b\u0938\u094d",
        "stop":"\u25a0  \u0930\u094b\u0915\u094d\u0928\u0941\u0939\u094b\u0938\u094d",
        "pause":"\u23f8  \u092a\u091c","resume":"\u25b6  \u091c\u093e\u0930\u0940 \u0930\u093e\u0916\u094d\u0928\u0941\u0939\u094b\u0938\u094d",
        "browse":"Excel / CSV \u092c\u093e\u091f \u0932\u094b\u0921 \u0917\u0930\u094d\u0928\u0941\u0939\u094b\u0938\u094d",
        "paste_names":"\u0935\u093e \u092f\u0939\u093e\u0901 \u0928\u093e\u092e \u091f\u093e\u0901\u0938\u094d\u0928\u0941\u0939\u094b\u0938\u094d (\u090f\u0915 \u092a\u094d\u0930\u0924\u093f \u0932\u093e\u0907\u0928):",
        "templates":"\u091f\u0947\u092e\u094d\u092a\u094d\u0932\u0947\u091f\u092c\u093e\u091f \u0938\u0941\u0930\u0941 \u0917\u0930\u094d\u0928\u0941\u0939\u094b\u0938\u094d",
        "names_loaded":"\u0928\u093e\u092e \u0932\u094b\u0921 \u092d\u092f\u094b",
        "ready":"\u091a\u0932\u093e\u0909\u0928 \u0924\u092f\u093e\u0930",
        "running":"\u091a\u0932\u093f\u0930\u0939\u0947\u0915\u094b \u091b\u094d\u200d\u0964",
        "done":"\u0938\u0915\u093f\u092f\u094b","countdown":"\u0938\u0941\u0930\u0941 \u0939\u0941\u0901\u0926\u0948\u091b",
        "seconds":"\u0938\u0947\u0915\u0947\u0928\u094d\u0921\u092e\u093e \u2014 \u0906\u092b\u094d\u0928\u094b \u090f\u092a\u092e\u093e \u091c\u093e\u0928\u0941\u0939\u094b\u0938\u094d!",
        "between":"\u092a\u094d\u0930\u0924\u094d\u092f\u0947\u0915 \u0928\u093e\u092e \u092c\u0940\u091a \u092a\u094d\u0930\u0924\u0940\u0915\u094d\u0937\u093e (\u0938\u0947\u0915\u0947\u0928\u094d\u0921)",
        "countdown_lbl":"\u0938\u0941\u0930\u0941 \u0939\u0941\u0928\u0941 \u0905\u0918\u093f\u0915\u094b \u0938\u092e\u092f (\u0938\u0947\u0915\u0947\u0928\u094d\u0921)",
        "dry_run":"\u0905\u092d\u094d\u092f\u093e\u0938 \u092e\u094b\u0921 (\u0915\u0941\u0928\u0948 \u0915\u094d\u0932\u093f\u0915 \u0939\u0941\u0901\u0926\u0948\u0928)",
        "save_flow":"\u092b\u094d\u0932\u094b \u0938\u0947\u092d \u0917\u0930\u094d\u0928\u0941\u0939\u094b\u0938\u094d",
        "load_flow":"\u092b\u094d\u0932\u094b \u0932\u094b\u0921 \u0917\u0930\u094d\u0928\u0941\u0939\u094b\u0938\u094d",
        "clear_log":"\u092e\u0947\u091f\u093e\u0909\u0928\u0941\u0939\u094b\u0938\u094d","export_log":"\u0932\u0917 \u0928\u093f\u0930\u094d\u092f\u093e\u0924",
        "test_single":"\u090f\u0915 \u0928\u093e\u092e\u0932\u0947 \u092a\u0930\u0940\u0915\u094d\u0937\u0923 \u0917\u0930\u094d\u0928\u0941\u0939\u094b\u0938\u094d",
        "no_names_warn":"\u0915\u0943\u092a\u092f\u093e \u092a\u0939\u093f\u0932\u0947 \u0915\u0947\u0939\u0940 \u0928\u093e\u092e \u0925\u092a\u094d\u0928\u0941\u0939\u094b\u0938\u094d\u0964",
        "no_steps_warn":"\u0915\u0943\u092a\u092f\u093e \u092a\u0939\u093f\u0932\u0947 \u091a\u0930\u0923\u0939\u0930\u0942 \u0925\u092a\u094d\u0928\u0941\u0939\u094b\u0938\u094d\u0964",
        "step_search":"\u091a\u0930\u0923 \u0916\u094b\u091c\u094d\u0928\u0941\u0939\u094b\u0938\u094d\u2026",
        "undo":"\u092a\u0942\u0930\u094d\u0935\u0935\u0924","redo":"\u092b\u0947\u0930\u093f \u0917\u0930\u094d\u0928\u0941\u0939\u094b\u0938\u094d",
        "duplicate":"\u0928\u0915\u094d\u0915\u0932","delete":"\u092e\u0947\u091f\u093e\u0909\u0928\u0941\u0939\u094b\u0938\u094d",
        "move_up":"\u092e\u093e\u0925\u093f \u091c\u093e\u0928\u0941\u0939\u094b\u0938\u094d",
        "move_down":"\u0924\u0932 \u091c\u093e\u0928\u0941\u0939\u094b\u0938\u094d",
        "edit":"\u0938\u092e\u094d\u092a\u093e\u0926\u0928",
        "copy_flow":"\u0905\u0930\u094d\u0915\u094b \u092a\u094d\u092f\u093e\u0928\u0932\u0915\u093e \u091a\u0930\u0923\u0939\u0930\u0942 \u0928\u0915\u094d\u0915\u0932 \u0917\u0930\u094d\u0928\u0941\u0939\u094b\u0938\u094d",
        "clear_all":"\u0938\u092c\u0948 \u0939\u091f\u093e\u0909\u0928\u0941\u0939\u094b\u0938\u094d",
        "find_replace":"\u0916\u094b\u091c \u0930 \u092c\u0926\u0932\u094d\u0928\u0941\u0939\u094b\u0938\u094d",
        "variables":"\u091a\u0932","retries":"\u0905\u0938\u092b\u0932\u092e\u093e \u092a\u0941\u0928\u0903 \u092a\u094d\u0930\u092f\u093e\u0938",
        "recorder":"\U0001f399 \u092e\u094d\u092f\u093e\u0915\u094d\u0930\u094b \u0930\u0947\u0915\u0930\u094d\u0921\u0930",
        "vision_agent":"\U0001f680 \u092d\u093f\u091c\u0928 \u090f\u091c\u0947\u0928\u094d\u091f",
        "debugger":"\U0001f41b \u092b\u094d\u0932\u094b \u0921\u093f\u092c\u0917\u0930",
    },
}

_lang = "en"

def L(key: str) -> str:
    return LANG.get(_lang, LANG["en"]).get(key, LANG["en"].get(key, key))

def set_lang(lang: str) -> None:
    global _lang
    if lang in LANG:
        _lang = lang

def load_json_file(path: str, default):
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[prefs] error loading {path}: {e}")
    return default

def save_json_file(path: str, data) -> None:
    try:
        dir_ = os.path.dirname(path) or "."
        os.makedirs(dir_, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            shutil.move(tmp, path)
        except Exception:
            try: os.unlink(tmp)
            except OSError: pass
            raise
    except Exception as e:
        print(f"[prefs] could not save {path}: {e}")

_PREFS_DEFAULTS: dict = {
    "countdown":5,"between":1.0,"dry_run":False,"fail_ss":False,"retries":0,
    "lang":"en","ui_font":"Segoe UI","ui_font_size":9,"theme_overrides":{},
    "auto_minimise":True,"confirm_clear":True,"warn_zero_coords":True,
    "show_step_count":True,"undo_depth":40,
    "screenshot_folder":"","flow_folder":"","export_folder":"",
    "shortcuts":{},"recorder_shortcuts":{},
    "type_interval":0.05,"pyautogui_pause":0.05,"failsafe":True,
    "failsafe_corner":"top-left",
    "recorder_auto_wait_threshold":1.5,"recorder_dbl_click_window":0.35,
    "recorder_wait_default":1.0,"recorder_auto_wait_on":True,
    "recorder_topmost":True,"overlay_x":None,"overlay_y":None,
    "agent_model":"llava","agent_max_steps":30,"agent_confidence":0.35,
    "agent_settle_time":0.6,"agent_show_log":True,
    "window_match_timeout":10,"window_validate_actions":False,"recent_steps":[],
}

def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result

_prefs: dict = _deep_merge(_PREFS_DEFAULTS, load_json_file(PREFS_FILE, {}))

def save_prefs() -> None:
    save_json_file(PREFS_FILE, _prefs)

T: dict = {
    "bg":"#0d1117","bg2":"#161b22","bg3":"#21262d","bg4":"#30363d",
    "border":"#30363d","fg":"#e6edf3","fg2":"#8b949e","fg3":"#484f58",
    "acc":"#388bfd","acc_dark":"#1f6feb","green":"#3fb950","green_bg":"#1a2e1a",
    "red":"#f85149","red_bg":"#2e1a1a","yellow":"#d29922","yellow_bg":"#2e2000",
    "purple":"#bc8cff","cyan":"#39c5cf","orange":"#e3b341","disabled":"#30363d",
    "font_h":("Segoe UI Semibold",11),"font_b":("Segoe UI",9),
    "font_s":("Segoe UI",8),"font_m":("Consolas",9),
}
for _k, _v in _prefs.get("theme_overrides", {}).items():
    if _k in T:
        T[_k] = _v

STEP_COLORS: dict = {
    "click":"#388bfd","double_click":"#388bfd","right_click":"#bc8cff",
    "mouse_move":"#39c5cf","hotkey":"#f78166","type_text":"#3fb950",
    "clip_type":"#3fb950","clear_field":"#d29922","wait":"#8b949e",
    "pagedown":"#8b949e","pageup":"#8b949e","scroll":"#8b949e",
    "key_repeat":"#f78166","hold_key":"#ff9966","loop":"#e3b341",
    "screenshot":"#bc8cff","condition":"#39c5cf","comment":"#484f58",
    "wait_window":"#39c5cf","wait_window_close":"#f78166",
    "wait_window_change":"#d29922","focus_window":"#388bfd","assert_window":"#3fb950",
    "click_image":"#ff9966","wait_image":"#39c5cf","wait_image_vanish":"#f78166",
    "ocr_condition":"#bc8cff","ocr_extract":"#3fb950",
    "if_condition":"#39c5cf","label":"#bc8cff","goto":"#bc8cff",
}

STEP_TYPES: list = [
    "click","double_click","right_click","mouse_move",
    "hotkey","type_text","clip_type","clear_field",
    "wait","pagedown","pageup","scroll","key_repeat","hold_key",
    "loop","screenshot","condition","comment",
    "wait_window","wait_window_close","wait_window_change","focus_window","assert_window",
    "click_image","wait_image","wait_image_vanish","ocr_condition","ocr_extract",
    "if_condition","label","goto",
]

STEP_FRIENDLY: dict = {
    "click":("Mouse Click","Click anywhere on the screen","\U0001f5b1"),
    "double_click":("Double Click","Double-click to open files or folders","\U0001f5b1"),
    "right_click":("Right Click","Right-click to open a context menu","\U0001f5b1"),
    "mouse_move":("Move Mouse","Move mouse to a position without clicking","\u27a4"),
    "hotkey":("Press Keys","Press a keyboard shortcut (Ctrl+S, Enter\u2026)","\u2328"),
    "type_text":("Type Text (English)","Type English text into any field","\u2328"),
    "clip_type":("Type Text (Any language)","Type text including Nepali, numbers, emoji","\U0001f4cb"),
    "clear_field":("Clear a Field","Click a field and erase everything in it","\u232b"),
    "wait":("Wait / Pause","Wait for the app to load before continuing","\u23f3"),
    "pagedown":("Scroll Down (Page)","Press Page Down to scroll","\u2b07"),
    "pageup":("Scroll Up (Page)","Press Page Up to scroll","\u2b06"),
    "scroll":("Mouse Scroll","Scroll up or down at a specific position","\u2195"),
    "key_repeat":("Repeat a Key","Press Tab, Enter etc. multiple times","\U0001f501"),
    "hold_key":("Hold a Key","Press and hold a key for N seconds","\u23f1"),
    "loop":("Repeat a Group","Repeat a set of steps N times","\U0001f504"),
    "screenshot":("Take Screenshot","Save a screenshot to a folder","\U0001f4f8"),
    "condition":("Check Window (title)","Skip steps if wrong window title is active","\u2753"),
    "comment":("Add a Note","Label a section of your flow","\U0001f4ac"),
    "wait_window":("Wait for Window","Pause until a specific window becomes active","\U0001fa9f"),
    "wait_window_close":("Wait for Window Close","Pause until a specific window closes","\U0001f6aa"),
    "wait_window_change":("Wait for Window Change","Pause until the active window changes","\U0001f504"),
    "focus_window":("Focus / Bring Window","Bring a window to the foreground","\U0001f3af"),
    "assert_window":("Assert Window","Fail if the wrong window is active","\u2705"),
    "click_image":("Click Image","Find an image on screen and click it","\U0001f5bc"),
    "wait_image":("Wait for Image","Wait until an image appears on screen","\U0001f441"),
    "wait_image_vanish":("Wait Image to Vanish","Wait until an image disappears from screen","\U0001f6ab"),
    "ocr_condition":("OCR Condition","Branch based on text read from screen","\U0001f524"),
    "ocr_extract":("OCR Extract","Read text from a screen region into a variable","\U0001f4d6"),
    "if_condition":("If / Else Condition","Branch flow based on a variable, OCR, or window title","\U0001f500"),
    "label":("Label","Mark a position that a Goto step can jump to","\U0001f3f7"),
    "goto":("Go To Label","Jump to a label step in the flow","\u21a9"),
}

STEP_DEFAULTS: dict = {
    "click":{"x":0,"y":0,"relative":False,"note":"","enabled":True},
    "double_click":{"x":0,"y":0,"relative":False,"note":"","enabled":True},
    "right_click":{"x":0,"y":0,"relative":False,"note":"","enabled":True},
    "mouse_move":{"x":0,"y":0,"relative":False,"note":"","enabled":True},
    "hotkey":{"keys":"enter","note":"","enabled":True},
    "type_text":{"text":"{name}","note":"","enabled":True},
    "clip_type":{"text":"{name}","note":"","enabled":True},
    "clear_field":{"x":0,"y":0,"note":"","enabled":True},
    "wait":{"seconds":1.0,"note":"","enabled":True},
    "pagedown":{"times":1,"note":"","enabled":True},
    "pageup":{"times":1,"note":"","enabled":True},
    "scroll":{"x":0,"y":0,"direction":"down","clicks":3,"note":"","enabled":True},
    "key_repeat":{"key":"tab","times":1,"note":"","enabled":True},
    "hold_key":{"key":"space","seconds":1.0,"note":"","enabled":True},
    "loop":{"times":2,"steps":[],"note":"","enabled":True},
    "screenshot":{"folder":"screenshots","note":"","enabled":True},
    "condition":{"window_title":"","action":"skip","note":"","enabled":True},
    "comment":{"text":"","note":"","enabled":True},
    "wait_window":{"window_title":"","process":"","hwnd":0,"timeout":10,"note":"","enabled":True},
    "wait_window_close":{"window_title":"","process":"","hwnd":0,"timeout":10,"note":"","enabled":True},
    "wait_window_change":{"timeout":10,"note":"","enabled":True},
    "focus_window":{"window_title":"","process":"","hwnd":0,"restore_minimized":True,"note":"","enabled":True},
    "assert_window":{"window_title":"","process":"","hwnd":0,"tolerance":"normal","action":"skip","note":"","enabled":True},
    "click_image":{"image_path":"","confidence":0.80,"timeout":10,"offset_x":0,"offset_y":0,"action":"click","grayscale":True,"note":"","enabled":True},
    "wait_image":{"image_path":"","confidence":0.80,"timeout":10,"note":"","enabled":True},
    "wait_image_vanish":{"image_path":"","confidence":0.80,"timeout":10,"note":"","enabled":True},
    "ocr_condition":{"x":0,"y":0,"w":300,"h":60,"pattern":"","case_sensitive":False,"action":"skip","note":"","enabled":True},
    "ocr_extract":{"x":0,"y":0,"w":300,"h":60,"variable":"ocr_result","note":"","enabled":True},
    "if_condition":{"condition":"contains","source":"variable","variable":"{name}","value":"","case_sensitive":False,"then_steps":[],"else_steps":[],"x":0,"y":0,"w":300,"h":60,"note":"","enabled":True},
    "label":{"label_name":"my_label","note":"","enabled":True},
    "goto":{"label_name":"my_label","note":"","enabled":True},
}

STEP_CATEGORIES: dict = {
    "\U0001f5b1  Mouse Actions":["click","double_click","right_click","mouse_move","scroll","clear_field"],
    "\u2328  Keyboard":["hotkey","type_text","clip_type","key_repeat","hold_key"],
    "\u23f1  Timing & Flow":["wait","pagedown","pageup","loop"],
    "\U0001f500  Branching":["if_condition","label","goto"],
    "\U0001fa9f  Window Control":["wait_window","wait_window_close","wait_window_change","focus_window","assert_window"],
    "\U0001f5bc  Image & OCR":["click_image","wait_image","wait_image_vanish","ocr_condition","ocr_extract"],
    "\U0001f527  Utilities":["screenshot","condition","comment"],
}

TEMPLATES: dict = {
    "WhatsApp Message":{"desc":"Type a message and send it on WhatsApp Web","icon":"\U0001f4ac","steps":[{"type":"click","x":0,"y":0,"relative":False,"note":"Click message box","enabled":True},{"type":"clip_type","text":"{name}","note":"Type the message","enabled":True},{"type":"hotkey","keys":"enter","note":"Send","enabled":True},{"type":"wait","seconds":1.0,"note":"Wait for delivery","enabled":True}]},
    "Fill & Save Form":{"desc":"Click a field, clear it, type a name, then save","icon":"\U0001f4dd","steps":[{"type":"focus_window","window_title":"","process":"","hwnd":0,"note":"Ensure correct window","enabled":True},{"type":"click","x":0,"y":0,"relative":False,"note":"Click the field","enabled":True},{"type":"clear_field","x":0,"y":0,"note":"Clear old value","enabled":True},{"type":"clip_type","text":"{name}","note":"Type new value","enabled":True},{"type":"hotkey","keys":"ctrl+s","note":"Save","enabled":True},{"type":"wait","seconds":1.5,"note":"Wait for save","enabled":True}]},
    "Open & Search":{"desc":"Click a search box, type a name, press Enter","icon":"\U0001f50d","steps":[{"type":"click","x":0,"y":0,"relative":False,"note":"Click search box","enabled":True},{"type":"clear_field","x":0,"y":0,"note":"Clear old search","enabled":True},{"type":"clip_type","text":"{name}","note":"Type name","enabled":True},{"type":"hotkey","keys":"enter","note":"Search","enabled":True},{"type":"wait","seconds":1.5,"note":"Wait for results","enabled":True}]},
    "Open & Print":{"desc":"Open each item and print it","icon":"\U0001f5a8","steps":[{"type":"click","x":0,"y":0,"relative":False,"note":"Click item","enabled":True},{"type":"wait","seconds":1.0,"note":"Wait to open","enabled":True},{"type":"hotkey","keys":"ctrl+p","note":"Print","enabled":True},{"type":"hotkey","keys":"enter","note":"Confirm print","enabled":True},{"type":"wait","seconds":2.0,"note":"Wait for print","enabled":True}]},
    "Login Flow":{"desc":"Focus window, enter credentials, submit","icon":"\U0001f510","steps":[{"type":"focus_window","window_title":"","process":"","hwnd":0,"note":"Bring login window to front","enabled":True},{"type":"click","x":0,"y":0,"relative":False,"note":"Click username","enabled":True},{"type":"clip_type","text":"{name}","note":"Type username","enabled":True},{"type":"hotkey","keys":"tab","note":"Go to password","enabled":True},{"type":"clip_type","text":"{password}","note":"Type password","enabled":True},{"type":"hotkey","keys":"enter","note":"Submit login","enabled":True},{"type":"wait_window","window_title":"","process":"","hwnd":0,"timeout":10,"note":"Wait for dashboard","enabled":True}]},
    "Copy & Paste":{"desc":"Select all in a field, copy, click target, paste","icon":"\U0001f4cb","steps":[{"type":"click","x":0,"y":0,"relative":False,"note":"Click source","enabled":True},{"type":"hotkey","keys":"ctrl+a","note":"Select all","enabled":True},{"type":"hotkey","keys":"ctrl+c","note":"Copy","enabled":True},{"type":"click","x":0,"y":0,"relative":False,"note":"Click target","enabled":True},{"type":"hotkey","keys":"ctrl+v","note":"Paste","enabled":True}]},
}
