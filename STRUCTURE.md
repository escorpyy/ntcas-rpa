# Swastik RPA v9.2 — Project Structure

```
swastik_rpa/
│
├── main.py                         # Entry point — run this
│
├── core/                           # Pure logic, no UI
│   ├── __init__.py
│   ├── constants.py                # Theme (T), step types, lang strings, prefs
│   ├── helpers.py                  # step_summary, parse_hotkey, apply_variables
│   └── executor.py                 # FlowExecutor — runs flows over name lists
│
├── ui/                             # Tkinter UI components
│   ├── __init__.py
│   ├── app.py                      # App(tk.Tk) — main window, tabs, shortcut wiring
│   ├── panels.py                   # FlowPanel, NameListPanel, RunStatusPanel
│   ├── dialogs.py                  # StepEditor, StepPickerDialog, Tooltip, etc.
│   └── settings_panel.py          # ⚙ SettingsPanel — full customisation tab (NEW)
│
└── agent/                          # Autonomous automation tools
    ├── __init__.py
    ├── macro_recorder.py           # 🎙 MacroRecorderPro
    └── vision_agent.py             # 🚀 AutonomousVisionAgent
```

## Settings Tab — what you can customise

| Section | Settings |
|---|---|
| 🤖 Automation Defaults | Countdown, between-delay, retries, type interval, pyautogui pause, failsafe, screenshot-on-fail, practice mode |
| ⌨ Keyboard Shortcuts | Rebind every app shortcut: Save, Load, Undo, Redo, Duplicate, Emergency Stop, Pause/Resume |
| 🎨 Appearance | Theme presets (5), accent colour presets (10) + custom picker, individual colour pickers for all 12 theme keys, UI font family & size |
| 🔧 Behaviour | Language, undo depth, auto-minimise on run, confirm-before-clear, warn-zero-coords, show step count |
| 📁 Paths | Default screenshot folder, flow folder, log export folder |
| 🎙 Macro Recorder | Auto-Wait threshold, double-click window, default wait duration, auto-wait on/off default, always-on-top |
| 🚀 Vision Agent | Default model, max steps, confidence threshold, settle time, show reasoning log |
| 🛠 Advanced | Failsafe corner, Export/Import settings JSON, open settings folder, Reset all to defaults |

## Installation

```bash
pip install pyautogui pyperclip pandas openpyxl Pillow pynput

# Optional — Vision Agent only:
pip install ollama
ollama pull llava
```

## Run

```bash
python main.py
```
