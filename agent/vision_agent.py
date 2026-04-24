"""
agent/vision_agent.py
=====================
AutonomousVisionAgent — LLM (llava via ollama) sees the screen and acts.
Iterates over name list, screenshots each turn, sends image+goal to llava,
parses JSON action, executes it, logs reasoning.

Features:
  - Iterates over all names in the name list
  - Screenshots the screen before each LLM call
  - Parses JSON action from LLM response
  - Executes click, type, hotkey, scroll, wait, done actions
  - Confidence threshold gate: skips action if confidence < 0.35
  - Variable substitution on goal and typed text ({name}, {varname})
  - Thread-safe stop signal via threading.Event
  - All UI updates dispatched via self.after() from worker thread

Requirements:
    pip install ollama
    ollama pull llava
"""

import io, base64, json, re, time, threading
import tkinter as tk
from tkinter import messagebox, ttk

import pyautogui
from PIL import Image, ImageTk

try:
    import ollama
    _OLLAMA_OK = True
except ImportError:
    _OLLAMA_OK = False

from core.constants import T
from core.helpers   import apply_variables


# ── Prompt & thresholds ───────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are an RPA automation agent. You see a screenshot of the user's screen. "
    "Based on the goal and current name, decide the SINGLE best next action. "
    "Respond ONLY with valid JSON (no markdown, no preamble) with these keys:\n"
    "  reasoning  : string — why you chose this action\n"
    "  action     : one of: click, double_click, right_click, type, hotkey, "
    "scroll_down, scroll_up, wait, done\n"
    "  x          : integer screen X (for click actions)\n"
    "  y          : integer screen Y (for click actions)\n"
    "  text       : string (for type / hotkey actions, hotkey uses '+' separator)\n"
    "  confidence : float 0.0–1.0\n"
    "Return 'done' when the goal for this name is fully complete."
)

_CONFIDENCE_THRESHOLD = 0.35


# ─────────────────────────────────────────────────────────────────────────────
#  AutonomousVisionAgent
# ─────────────────────────────────────────────────────────────────────────────

class AutonomousVisionAgent(tk.Toplevel):
    """
    Iterates over names; for each: screenshot → llava → JSON action → execute.
    Requires:  pip install ollama   and   ollama pull llava
    """

    def __init__(self, parent, names: list, variables: dict = None):
        super().__init__(parent)
        self.title("🚀 Swastik — Autonomous Vision Agent")
        self.configure(bg=T["bg"])
        self.geometry("1120x740")
        self.minsize(900, 600)

        self.names             = list(names)
        self.variables         = variables or {}
        self.current_name_idx  = 0
        self._stop_event       = threading.Event()
        self._running          = False
        self._max_steps        = 30

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.grab_set()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Goal row
        top = tk.Frame(self, bg=T["bg2"], pady=12)
        top.pack(fill="x")
        tk.Label(top, text="🎯 Describe your goal (plain English or Nepali)",
                 bg=T["bg2"], fg=T["fg"], font=T["font_h"]).pack(anchor="w", padx=20)
        self.goal_entry = tk.Text(top, height=2, bg=T["bg3"], fg=T["fg"],
                                  font=T["font_m"], insertbackground=T["fg"],
                                  relief="flat", padx=8, pady=6)
        self.goal_entry.pack(fill="x", padx=20, pady=(4, 8))

        # Options row
        opts = tk.Frame(top, bg=T["bg2"])
        opts.pack(fill="x", padx=20, pady=(0, 8))
        tk.Label(opts, text="Max actions per name:", bg=T["bg2"],
                 fg=T["fg3"], font=T["font_s"]).pack(side="left")
        self._max_var = tk.StringVar(value="30")
        tk.Entry(opts, textvariable=self._max_var, width=5, bg=T["bg3"],
                 fg=T["yellow"], font=T["font_m"], relief="flat"
                 ).pack(side="left", padx=6)
        tk.Label(opts, text="  Model:", bg=T["bg2"], fg=T["fg3"],
                 font=T["font_s"]).pack(side="left", padx=(16, 4))
        self._model_var = tk.StringVar(value="llava")
        tk.Entry(opts, textvariable=self._model_var, width=12, bg=T["bg3"],
                 fg=T["fg"], font=T["font_m"], relief="flat"
                 ).pack(side="left")

        tk.Button(top, text="🚀  Start Agent",
                  bg=T["green"], fg="white",
                  font=("Segoe UI Semibold", 11), relief="flat", padx=20, pady=8,
                  command=self._start_agent).pack(side="left", padx=20, pady=(0, 8))

        # Main paned area
        pane = tk.PanedWindow(self, orient="horizontal", bg=T["bg"],
                              sashwidth=6, sashrelief="flat")
        pane.pack(fill="both", expand=True, padx=8, pady=4)

        # Left: reasoning log
        left = tk.Frame(pane, bg=T["bg"])
        pane.add(left, stretch="always", width=560)
        tk.Label(left, text="🧠 Agent Reasoning Log",
                 bg=T["bg"], fg=T["acc"], font=T["font_h"]).pack(anchor="w", padx=8, pady=(4, 0))
        self.reason_text = tk.Text(
            left, bg=T["bg3"], fg=T["fg"], font=T["font_m"],
            state="disabled", relief="flat", padx=8, pady=6)
        self.reason_text.tag_config("ok",   foreground=T["green"])
        self.reason_text.tag_config("warn", foreground=T["yellow"])
        self.reason_text.tag_config("err",  foreground=T["red"])
        self.reason_text.tag_config("dim",  foreground=T["fg3"])
        lsb = ttk.Scrollbar(left, orient="vertical", command=self.reason_text.yview)
        self.reason_text.configure(yscrollcommand=lsb.set)
        lsb.pack(side="right", fill="y")
        self.reason_text.pack(fill="both", expand=True, padx=8, pady=4)

        # Right: screenshot preview
        right = tk.Frame(pane, bg=T["bg"])
        pane.add(right, stretch="always", width=520)
        tk.Label(right, text="📸 Last Screenshot",
                 bg=T["bg"], fg=T["acc"], font=T["font_h"]).pack(anchor="w", padx=8, pady=(4, 0))
        self.screenshot_label = tk.Label(right, bg=T["bg3"], relief="flat")
        self.screenshot_label.pack(fill="both", expand=True, padx=8, pady=4)

        # Bottom status bar
        ctrl = tk.Frame(self, bg=T["bg2"], pady=8)
        ctrl.pack(fill="x")
        self.status_lbl = tk.Label(ctrl, text="Ready",
                                   bg=T["bg2"], fg=T["green"], font=T["font_h"])
        self.status_lbl.pack(side="left", padx=20)
        self.current_name_lbl = tk.Label(ctrl, text="",
                                         bg=T["bg2"], fg=T["cyan"], font=T["font_m"])
        self.current_name_lbl.pack(side="left", padx=12)
        tk.Button(ctrl, text="⏹ STOP",
                  bg=T["red"], fg="white",
                  font=("Segoe UI Semibold", 9), relief="flat", padx=14, pady=6,
                  command=self._stop_agent).pack(side="right", padx=20)

    # ── Agent control ─────────────────────────────────────────────────────────

    def _start_agent(self):
        if not _OLLAMA_OK:
            messagebox.showerror(
                "Missing library",
                "ollama is required.\n\npip install ollama\nollama pull llava")
            return
        self.goal = self.goal_entry.get("1.0", "end").strip()
        if not self.goal:
            messagebox.showwarning("Goal Required",
                                   "Please describe what you want the agent to do.")
            return
        try:
            self._max_steps = max(1, int(self._max_var.get()))
        except ValueError:
            self._max_steps = 30

        self.current_name_idx = 0
        self._stop_event.clear()
        self._running = True
        self.status_lbl.config(text="🤖 Agent Running…", fg=T["yellow"])
        threading.Thread(target=self._agent_loop, daemon=True).start()

    def _stop_agent(self):
        self._stop_event.set()
        self._running = False
        self.after(0, lambda: self.status_lbl.config(
            text="🛑 Stopped by user", fg=T["red"]))

    # ── Agent loop ────────────────────────────────────────────────────────────

    def _agent_loop(self):
        model = self._model_var.get().strip() or "llava"

        while not self._stop_event.is_set() and self.current_name_idx < len(self.names):
            name = self.names[self.current_name_idx]
            self.after(0, lambda n=name: self.current_name_lbl.config(
                text=f"Processing: {n}"))
            self._log(f"\n── Name: {name} ──────────────────────────────", "ok")

            step_count = 0
            while step_count < self._max_steps and not self._stop_event.is_set():
                step_count += 1

                # 1. Screenshot
                try:
                    screenshot = pyautogui.screenshot()
                except Exception as e:
                    self._log(f"⚠ Screenshot failed: {e}", "err")
                    break

                img_bytes = io.BytesIO()
                screenshot.save(img_bytes, format="PNG")
                img_b64   = base64.b64encode(img_bytes.getvalue()).decode()

                # Update preview (shows what the agent sees)
                self.after(0, lambda sc=screenshot: self._update_screenshot(sc))

                # 2. Prompt
                vmap = {**self.variables, "name": name}
                goal_substituted = apply_variables(self.goal, vmap)
                context = (
                    f"Goal: {goal_substituted}\n"
                    f"Current name: {name}\n"
                    f"Action step: {step_count}/{self._max_steps}\n"
                    f"What is the single best next action?"
                )

                # 3. LLM call
                try:
                    response = ollama.chat(
                        model=model,
                        messages=[{
                            "role":    "user",
                            "content": f"{_SYSTEM_PROMPT}\n\n{context}",
                            "images":  [img_b64],
                        }],
                    )
                    raw_content = response["message"]["content"]
                except Exception as e:
                    self._log(f"⚠ LLM error: {e}", "err")
                    time.sleep(2)
                    continue

                # 4. Parse JSON
                action_data = self._parse_action(raw_content)
                reasoning   = action_data.get("reasoning", "…")
                act         = action_data.get("action", "wait").lower()
                conf        = float(action_data.get("confidence", 0.5))

                self._log(f"[{step_count}] Action: {act}  conf={conf:.2f}", "dim")
                self._log(f"     {reasoning}")

                # Confidence gate
                if conf < _CONFIDENCE_THRESHOLD:
                    self._log(
                        f"⚠ Low confidence ({conf:.2f}) — waiting before retry.", "warn")
                    time.sleep(2)
                    continue

                # 5. Execute
                done = self._execute_action(act, action_data, name)
                time.sleep(0.6)

                if done:
                    self._log("✅ Agent: task done for this name.", "ok")
                    break

            self.current_name_idx += 1
            time.sleep(0.5)

        self._running = False
        self.after(0, lambda: self.status_lbl.config(
            text="✅ Agent Finished", fg=T["green"]))
        self.after(0, lambda: self.current_name_lbl.config(text=""))

    # ── Action execution ──────────────────────────────────────────────────────

    def _execute_action(self, act: str, data: dict, name: str) -> bool:
        """Execute one action. Returns True when 'done'."""
        vmap = {**self.variables, "name": name}

        def subst(text):
            return apply_variables(str(text), vmap)

        try:
            x = int(data.get("x", 500))
            y = int(data.get("y", 500))

            if act == "click":
                pyautogui.click(x, y)
            elif act == "double_click":
                pyautogui.doubleClick(x, y)
            elif act == "right_click":
                pyautogui.rightClick(x, y)
            elif act == "type":
                text = subst(data.get("text", ""))
                pyautogui.typewrite(text, interval=0.05)
            elif act == "hotkey":
                keys_raw = subst(data.get("text", "enter"))
                keys     = [k.strip() for k in keys_raw.split("+") if k.strip()]
                pyautogui.hotkey(*keys)
            elif act == "scroll_down":
                pyautogui.scroll(-3)
            elif act == "scroll_up":
                pyautogui.scroll(3)
            elif act == "wait":
                time.sleep(float(data.get("seconds", 1.5)))
            elif act == "done":
                return True
            else:
                self._log(f"⚠ Unknown action '{act}' — waiting 1s.", "warn")
                time.sleep(1.0)
        except pyautogui.FailSafeException:
            self._stop_event.set()
            self._log("⛔ Safety stop — mouse corner!", "err")
        except Exception as e:
            self._log(f"⚠ Execute error: {e}", "err")

        return False

    # ── JSON parsing ──────────────────────────────────────────────────────────

    @staticmethod
    def _parse_action(raw: str) -> dict:
        """Extract first JSON object from LLM response; return safe defaults on failure."""
        raw = re.sub(r"```json\s*", "", raw)
        raw = re.sub(r"```\s*", "", raw)
        match = re.search(r"\{.*?\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        return {"reasoning": "Could not parse LLM response", "action": "wait", "confidence": 0.0}

    # ── UI helpers ────────────────────────────────────────────────────────────

    def _log(self, text: str, tag: str = ""):
        def _do():
            self.reason_text.config(state="normal")
            self.reason_text.insert("end", text + "\n", tag)
            self.reason_text.see("end")
            self.reason_text.config(state="disabled")
        self.after(0, _do)

    def _update_screenshot(self, screenshot):
        try:
            w = self.screenshot_label.winfo_width()  or 500
            h = self.screenshot_label.winfo_height() or 320
            w = max(w, 200); h = max(h, 150)
            img = screenshot.resize((w, h), Image.LANCZOS)
            self._tk_img = ImageTk.PhotoImage(img)
            self.screenshot_label.config(image=self._tk_img)
        except Exception:
            pass

    def _on_close(self):
        self._stop_event.set()
        self.destroy()
