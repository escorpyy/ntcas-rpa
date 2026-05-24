# Swastik RPA v9.5

> A Windows desktop automation tool that repeats your actions across a list of names, bill numbers, or any data — no coding required.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [Name List Features](#name-list-features)
- [Flow Builder Features](#flow-builder-features)
- [Step Types](#step-types)
- [Run & Execution Features](#run--execution-features)
- [Agent Tools](#agent-tools)
- [Settings & Customisation](#settings--customisation)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Variables System](#variables-system)
- [File Management](#file-management)
- [Installation](#installation)

---

## Quick Start

1. Add names to the **Name List** tab (one per line or load from Excel/CSV)
2. Build your automation steps in the **Build Flow** tab
3. Click **▶ Start Automation** in the **Run** tab
4. Switch to your target app during the countdown — the bot does the rest

---

## Core Concepts

- **{name}** — placeholder replaced with each name from your list at runtime
- **Flow** — a sequence of steps (clicks, typing, hotkeys, waits) repeated for every name
- **First-name flow** — optional separate flow that only runs for the very first name (useful for login steps)
- **Variables** — `{varname}` placeholders you define and fill before each run
- **Column-mapped variables** — when loading a multi-column spreadsheet, each column becomes its own `{variable}` (e.g. `{amount}`, `{date}`, `{ref}`)

---

## Name List Features

| Feature | Description |
|---|---|
| Manual entry | Type or paste names directly, one per line |
| Load from Excel | Import `.xlsx` or `.xls` files |
| Load from CSV | Import `.csv` files |
| Column chooser | When a spreadsheet has multiple columns, pick which one holds the names |
| Column mapping (v9.5) | Map extra columns to `{variables}` — e.g. amount column → `{amount}` |
| Sort A→Z / Z→A | Sort the name list alphabetically |
| Shuffle | Randomise the order of names |
| Deduplicate | Remove duplicate entries automatically |
| Recent files | Quick access to the last 5 loaded files |
| Live count | Shows how many names are loaded |

---

## Flow Builder Features

| Feature | Description |
|---|---|
| Step picker dialog | Browse steps by category with descriptions and tips |
| Recent steps | Top 6 most recently used step types shown for quick access |
| Templates | 6 ready-made flows: WhatsApp Message, Fill & Save Form, Open & Search, Open & Print, Login Flow, Copy & Paste |
| Drag to reorder | Drag the ≡ handle to reorder steps |
| Inline editing | Click ✏ on any step card to open the editor |
| Pick from screen | 3-second countdown while you hover over a target — records X, Y coordinates automatically |
| Toggle enable/disable | Disable steps without deleting them (👁 button) |
| Duplicate step | Copy any step instantly |
| Auto-Wait | Option to automatically append a Wait step after any step |
| Undo / Redo | Full undo history (up to 40 actions) |
| Cut / Copy / Paste | Cut, copy, and paste steps within and between panels |
| Find & Replace | Search and replace text across all step fields at once |
| Copy other panel | Copy all steps from the First-name panel to the Repeat panel and vice versa |
| First-name flow | Separate flow for the first name only (e.g. login steps) |
| Grid editor | Excel-style table view of all steps with sort, multi-select, move, and batch edit |
| Step count badge | Shows total step count in the toolbar |
| Step notes | Add a label/comment to any step for documentation |
| Step search | Search through steps (via Find & Replace) |

---

## Step Types

### Mouse Actions

| Step | Description |
|---|---|
| Click | Left-click at X, Y coordinates |
| Double Click | Double-click at X, Y coordinates |
| Right Click | Right-click to open context menus |
| Move Mouse | Move mouse to a position without clicking |
| Scroll | Scroll up or down at a specific screen position |
| Clear a Field | Click a field, select all, and delete — use before typing |

### Keyboard Actions

| Step | Description |
|---|---|
| Press Keys / Hotkey | Press keyboard shortcuts: `ctrl+s`, `enter`, `alt+f4`, etc. |
| Type Text (English) | Type plain ASCII text character by character |
| Type Text (Any Language) | Type via clipboard — works for Nepali, Unicode, emoji |
| Repeat a Key | Press a key (Tab, Enter, etc.) N times |
| Hold a Key | Hold a key down for N seconds |

### Timing & Flow Control

| Step | Description |
|---|---|
| Wait / Pause | Pause for N seconds |
| Scroll Down (Page) | Press Page Down N times |
| Scroll Up (Page) | Press Page Up N times |
| Loop | Repeat a group of inner steps N times |
| Comment / Note | Annotation step — not executed, just labels a section |

### Branching (v9.5)

| Step | Description |
|---|---|
| If / Else Condition | Branch based on a variable value, OCR text, window title, or clipboard content |
| Label | Mark a position in the flow that a Goto step can jump to |
| Go To Label | Jump to a named Label step — useful for loops and skipping sections |

### Window Control

| Step | Description |
|---|---|
| Wait for Window | Pause until a specific window title becomes active |
| Wait for Window Close | Pause until a specific window closes |
| Wait for Window Change | Pause until the active window changes |
| Focus / Bring Window | Bring a window to the foreground before acting |
| Assert Window | Stop or skip if the wrong app window is active |

### Image & OCR

| Step | Description |
|---|---|
| Click Image | Find a button/icon on screen by screenshot match and click it |
| Wait for Image | Pause until a target image appears on screen |
| Wait Image to Vanish | Pause until a loading spinner or image disappears |
| OCR Condition | Branch based on text read from a screen region |
| OCR Extract | Read text from a screen region and store it in a `{variable}` |

### Utilities

| Step | Description |
|---|---|
| Take Screenshot | Save a screenshot to a folder, named after the current name |
| Check Window (title) | Skip or stop if the wrong window title is active (legacy) |

---

## Run & Execution Features

| Feature | Description |
|---|---|
| Startup countdown | Configurable delay (seconds) before automation begins — time to switch to your app |
| Delay between names | Configurable rest time after completing each name |
| Retries on failure | Automatically retry a failed name N times |
| Practice mode | Logs every step without executing any real clicks |
| Screenshot on failure | Saves a PNG when a name's flow fails |
| Auto-minimise | Minimises the Swastik RPA window when a run starts |
| Live progress bar | Shows current progress across the name list |
| Name status badges | Green ✔ / Red ✘ badges shown for each completed name |
| ETA display | Estimated time remaining based on recent average step time |
| Run timer | Shows elapsed time during a run |
| Test with one name | Run the flow for a single name to verify before a full run |
| Emergency stop | Press F10 or move mouse to top-left screen corner |
| Pause / Resume | Press F11 to pause and resume mid-run |
| Run log | Scrollable log of every step with colour-coded output |
| Copy log | Copy the full run log to clipboard |
| Export log | Save the run log to a `.txt` file |
| Clear log | Clear the log panel |
| Zero-coordinate warning | Warns if any click steps have coordinates (0, 0) before running |
| Variable fill dialog | If `{variables}` are defined, prompts for their values before running |

### Resume from Failure (v9.5)

| Feature | Description |
|---|---|
| Checkpoint system | Saves progress after every name to `~/.swastik/checkpoints/` |
| Resume dialog | When a previous run was interrupted, asks: Resume or Restart |
| Resume | Skips already-completed names and continues from where it stopped |
| Restart | Wipes the checkpoint and starts fresh |
| Auto-clear checkpoint | Checkpoint is deleted automatically when all names complete successfully |
| Checkpoint manager | View and delete saved checkpoints from the Settings area |

---

## Agent Tools

### Macro Recorder Pro

| Feature | Description |
|---|---|
| Record mouse clicks | Records left, right, and middle clicks |
| Record keyboard | Records hotkeys, typed text, and special keys |
| Record scroll | Records mouse wheel scroll events |
| Double-click detection | Automatically converts two rapid clicks into a double-click step |
| Shift+char capture | Correctly captures shifted characters: `!`, `@`, `#`, etc. |
| Auto-Wait insertion | Automatically inserts Wait steps for idle gaps above a threshold |
| Window change detection | Inserts Wait Window steps when the active window changes during recording |
| Relative coordinates | Records click positions as relative (0–1) fractions of the window |
| Image click recording | Optionally captures an 80×80px screenshot around each click and records a Click Image step instead |
| Floating overlay panel | Compact always-on-top panel with Record/Pause/Stop/Wait buttons |
| Overlay collapse mode | Collapse overlay to a minimal strip |
| Overlay drag | Drag the overlay anywhere on screen; position is saved |
| Real-time step counter | Overlay shows how many steps are recorded, updated every 0.5 seconds |
| Inline step editing | Double-click any recorded step to edit it |
| Drag to reorder | Reorder recorded steps before importing |
| Multi-select delete | Shift-click to select a range of steps, then delete |
| Move up / down | Move individual steps up or down |
| Merge waits | Merge consecutive auto-wait steps into one |
| Undo | Ctrl+Z to undo the last recorded or deleted step |
| Import preview | Shows a summary of all recorded steps before importing |
| Import mode | Choose Replace (overwrite flow) or Append (add to existing) |
| Import target | Import into Main Flow or First-Name Flow |
| Configurable shortcuts | F2/F3/F4/F5 by default; all four shortcuts are rebindable |
| Conflict detection | Warns if a chosen shortcut conflicts with a Windows system shortcut |
| ESC recorded normally | ESC is not a stop shortcut — it records as a normal Escape key step |

### Flow Debugger

| Feature | Description |
|---|---|
| Step-by-step execution | Step through one action at a time with F10 |
| Run mode | Run continuously until a breakpoint or the end |
| Breakpoints | Click any step to toggle a red breakpoint; execution pauses there |
| Variable panel | Live view of all `{variables}` and their current values |
| Window detection panel | Shows the active window's title, process, class, position, size, DPI, and monitor |
| Capture window target | Save the current window as a match target |
| Test window match | Check whether the current window matches the captured target |
| Step result log | Pass ✔ / Fail ✘ result logged for every executed step |
| Call stack panel | Shows loop nesting depth during loop execution |
| Speed slider | Control delay between steps in run mode (0–2 seconds) |
| Dry-run toggle | Execute steps without real clicks |
| Name selector | Switch which name from the list is used for `{name}` substitution |
| Run single step | Run any individual step from the detail panel |
| Inline step view | Click any step to see full details: type, coordinates, resolved text, last result |
| Relative coord resolution | Shows resolved absolute coordinates when relative mode is active |

### Flow Scheduler

| Feature | Description |
|---|---|
| Daily trigger | Run at a specific HH:MM time every day |
| Interval trigger | Run every N minutes |
| One-time trigger | Run once at a specific date and time |
| Day-of-week filter | Restrict daily runs to selected days (e.g. Mon–Fri) |
| Max runs limit | Stop after N executions |
| Enable / disable | Toggle schedules on or off without deleting them |
| Run now | Manually trigger a scheduled flow from the UI |
| Persistent storage | Schedules saved to `~/.swastik/schedules.json` — survive restarts |
| Run log | Timestamped log of all scheduler activity |
| Auto-refresh list | Schedule list refreshes every 15 seconds |

### Vision Agent (AI-powered)

| Feature | Description |
|---|---|
| Plain-language goal | Describe what to do in English or Nepali |
| Screen capture | Takes a screenshot before each LLM decision |
| LLM-driven actions | Supports click, double_click, right_click, type, hotkey, scroll, wait, done |
| Variable substitution | Substitutes `{name}` and other variables in the goal and typed text |
| Confidence threshold | Skips actions below a configurable confidence score (default 0.35) |
| Max steps limit | Safety cap on how many actions the agent takes per name |
| Configurable model | Change the Ollama model (default: llava) |
| Screenshot preview | Live preview of the last screenshot the agent used |
| Reasoning log | Shows the agent's reasoning for each action |
| Stop button | Abort the agent at any time |
| Iterates name list | Runs the goal for every name in the list automatically |

---

## Settings & Customisation

### Automation Defaults

| Setting | Description |
|---|---|
| Startup countdown | Seconds before automation begins |
| Delay between names | Rest time after each name |
| Retries on failure | Number of retry attempts per name |
| Type interval | Seconds per character for Type Text steps |
| PyAutoGUI global pause | Pause added after every PyAutoGUI call |
| Fail-safe | Enable/disable top-left corner emergency stop |
| Screenshot on failure | Auto-capture PNG when a name fails |
| Practice mode default | Start every run in dry-run mode |

### App Keyboard Shortcuts

All six app shortcuts are fully rebindable:

- Save Flow
- Load Flow
- Undo
- Redo
- Duplicate Last Step
- Emergency Stop
- Pause / Resume

### Appearance

| Setting | Description |
|---|---|
| Theme presets | 5 built-in themes: GitHub Dark (default), Pitch Black, Soft Dark, Dark Navy, Monokai |
| Accent colour presets | 10 preset accent colours |
| Custom accent | Full colour picker for accent colour |
| Per-key colour pickers | Individual pickers for all 12 theme colour keys (bg, fg, green, red, etc.) |
| UI font family | Choose from 8 font options |
| UI font size | Size 7–16 |

### Behaviour

| Setting | Description |
|---|---|
| Interface language | English or Nepali (नेपाली) |
| Undo history depth | Maximum number of undoable actions (default 40) |
| Auto-minimise on run | Minimise the window when a run starts |
| Confirm before clear | Ask confirmation before clearing all steps |
| Warn zero coordinates | Warn when click steps have (0, 0) coordinates |
| Show step count badge | Display step count in the flow panel toolbar |

### Paths & Folders

- Default screenshot folder
- Default flow folder (for Save/Load dialogs)
- Default log export folder

### Macro Recorder Settings

- Auto-Wait threshold (seconds)
- Double-click detection window (seconds)
- Manual Wait step default duration
- Auto-Wait enabled by default
- Keep recorder window always-on-top
- Configurable Record / Pause / Stop / Add Wait shortcuts with live conflict detection

### Vision Agent Settings

- Default model name
- Max actions per name
- Confidence threshold (0.0–1.0)
- Settle time after each action
- Show live reasoning log panel

### Advanced

| Feature | Description |
|---|---|
| Fail-safe corner | Choose which screen corner triggers emergency stop |
| Export settings | Save all preferences to a JSON file |
| Import settings | Load preferences from a JSON file |
| Open settings folder | Open `~/.swastik/` in Explorer |
| Reset all to default | Wipe every customisation and restore defaults |

---

## Keyboard Shortcuts

| Action | Default Shortcut |
|---|---|
| Save flow | Ctrl+S |
| Load flow | Ctrl+O |
| Undo | Ctrl+Z |
| Redo | Ctrl+Y |
| Duplicate last step | Ctrl+D |
| Emergency stop | F10 |
| Pause / Resume | F11 |
| Recorder: Start / Resume | F2 |
| Recorder: Pause | F3 |
| Recorder: Stop | F4 |
| Recorder: Insert Wait | F5 |
| Debugger: Step | F10 |
| Debugger: Run | F5 |
| Debugger: Toggle breakpoint | F9 |
| Fail-safe (emergency stop) | Move mouse to top-left corner |

> All app shortcuts are rebindable from Settings → App Keyboard Shortcuts.
> All recorder shortcuts are rebindable from Settings → Macro Recorder Pro.

---

## Variables System

| Feature | Description |
|---|---|
| `{name}` | Always replaced with the current name from the list |
| Custom variables | Define any `{varname}` in the Variables dialog |
| Fill at runtime | A dialog prompts for variable values before each run |
| Column-mapped variables | Each spreadsheet column maps to its own `{variable}` |
| Variable substitution | Works in: Type Text, Clip Type, Hotkey, Screenshot folder, Window title, OCR pattern, If condition values, and the Vision Agent goal |
| OCR extract to variable | OCR Extract step stores screen text into any `{variable}` for use in later steps |

---

## File Management

| Feature | Description |
|---|---|
| Save flow | Save the current flow to a `.json` file |
| Load flow | Load a flow from a `.json` file |
| Recent flows | Quick access to the last 10 opened flow files |
| Clear recent | Remove all entries from the recent flows list |
| Window title shows filename | Title bar updates to show the current flow filename |
| Save presets | Flows are plain JSON — shareable and version-controllable |
| Auto-save preferences | All settings save automatically whenever changed |

---

## Installation

```bash
pip install pyautogui pyperclip pandas openpyxl Pillow pynput
```

Optional — for OCR steps:
```bash
pip install opencv-python-headless pytesseract
# Windows: install Tesseract binary from https://github.com/UB-Mannheim/tesseract/wiki
```

Optional — for Vision Agent:
```bash
pip install ollama
ollama pull llava
```

Optional — for enhanced UI:
```bash
pip install customtkinter
```

### Run

```bash
python main.py
```

Or on Windows, double-click `run.bat`.

---

## Project Structure

```
swastik_rpa/
├── main.py                    # Entry point
├── run.bat                    # Windows launcher
├── core/
│   ├── constants.py           # Theme, step types, language strings, preferences
│   ├── helpers.py             # Utility functions
│   ├── executor.py            # FlowExecutor — runs flows over name lists
│   ├── checkpoint.py          # Resume-from-failure checkpoint system
│   ├── column_mapper.py       # Multi-column spreadsheet variable mapping
│   ├── image_finder.py        # OpenCV image matching engine
│   ├── ocr_engine.py          # Tesseract OCR engine
│   └── window_manager.py      # Window detection and matching
├── ui/
│   ├── app.py                 # Main application window
│   ├── panels.py              # FlowPanel, NameListPanel, RunStatusPanel
│   ├── dialogs.py             # StepEditor, StepPickerDialog, variable dialogs
│   ├── settings_panel.py      # Settings tab
│   ├── if_editor.py           # If/Else branch editor
│   └── resume_dialog.py       # Checkpoint resume dialog
└── agent/
    ├── macro_recorder.py      # Macro Recorder Pro
    ├── vision_agent.py        # Autonomous Vision Agent (LLM)
    ├── flow_debugger.py       # Step-by-step flow debugger
    └── scheduler.py           # Flow scheduler
```

---

## Requirements

- Windows 10 or later (Linux/macOS supported with limited window detection)
- Python 3.10+
- Screen resolution: 1024×768 minimum

---

*Swastik RPA v9.5 — Built for Nepal's accounting, billing, and form-filling workflows.*
