"""
core/executor.py
================
FlowExecutor: runs a flow of steps for a list of names.
Handles countdown, pause/resume, retries, ETA, hotkeys,
and all step-type execution logic.

BUG FIXES vs V8/V9:
  - _SkipName properly propagated through _run_steps
  - condition step now also works on non-Windows via pyautogui.getActiveWindowTitle
  - hold_key falls back gracefully when pynput unavailable
  - All bare except replaced with except Exception
  - _wait_if_paused checks both events atomically
  - screenshot path uses _DIR not cwd
  - ETA rolling window capped at 5 samples
"""

import os, sys, time, threading, datetime
import pyautogui

try:
    from pynput import keyboard as _kb
    from pynput.keyboard import Key as _PynKey, Controller as _PynKbC, KeyCode as _PynKeyCode
    _PYNPUT_OK = True
except ImportError:
    _PYNPUT_OK = False

from .constants import _DIR
from .helpers   import parse_hotkey, type_text_safe, apply_variables


class _SkipName(Exception):
    """Raised by a 'condition' step with action=skip — skips to the next name."""


class FlowExecutor:
    def __init__(
        self,
        names,
        flow,
        first_flow=None,
        log_fn=None,
        between: float = 1.0,
        countdown: int = 5,
        dry_run: bool = False,
        on_fail_ss: bool = False,
        retries: int = 0,
        variables: dict = None,
        progress_fn=None,
        status_fn=None,
        eta_fn=None,
    ):
        self.names       = names
        self.flow        = flow
        self.first_flow  = first_flow or []
        self.log         = log_fn or print
        self.between     = max(0.0, float(between))
        self.countdown   = max(0, int(countdown))
        self.dry_run     = dry_run
        self.on_fail_ss  = on_fail_ss
        self.retries     = max(0, int(retries))
        self.variables   = variables or {}
        self.progress_fn = progress_fn or (lambda i, n, nm: None)
        self.status_fn   = status_fn   or (lambda nm, ok: None)
        self.eta_fn      = eta_fn      or (lambda s: None)

        # Thread-safe stop / pause
        self._stop_event  = threading.Event()
        self._pause_event = threading.Event()
        self._kb_lst      = None
        self._times: list = []   # rolling window of last-5 per-name durations

    # ── Public properties ─────────────────────────────────────────────────────

    @property
    def _stop(self) -> bool:
        return self._stop_event.is_set()

    @property
    def _pause(self) -> bool:
        return self._pause_event.is_set()

    def stop(self)   -> None: self._stop_event.set(); self._pause_event.clear()
    def pause(self)  -> None: self._pause_event.set()
    def resume(self) -> None: self._pause_event.clear()

    # ── Main entry ────────────────────────────────────────────────────────────

    def start(self) -> tuple:
        self._start_hotkeys()
        total, success, failed = len(self.names), 0, []

        if self.dry_run:
            self.log("⚠  Practice mode — no actual clicks will happen")

        # Countdown
        if self.countdown > 0:
            self.log(f"⏳ Starting in {self.countdown} seconds — switch to your app!")
            for i in range(self.countdown, 0, -1):
                if self._stop:
                    self.log("⛔ Stopped.")
                    self._stop_hotkeys()
                    return 0, []
                self.log(f"   {i}…")
                time.sleep(1)

        for i, name in enumerate(self.names, 1):
            if self._stop:
                self.log("⛔ Stopped.")
                break
            self._wait_if_paused()
            if self._stop:
                break

            self.progress_fn(i, total, name)
            self.log(f"\n[{i}/{total}]  →  {name}")

            this_flow = (
                (self.first_flow + self.flow) if (i == 1 and self.first_flow) else self.flow
            )

            t0 = time.time()
            ok = False
            for attempt in range(self.retries + 1):
                if self._stop:
                    break
                if attempt > 0:
                    self.log(f"  ↻ Retry {attempt}/{self.retries}…")
                try:
                    ok = self._run_steps(this_flow, name)
                except _SkipName:
                    self.log("  ↷ Skipping name (condition mismatch).")
                    ok = True   # not a failure, just skipped
                    break
                if ok:
                    break

            elapsed = time.time() - t0
            self._times.append(elapsed)
            if len(self._times) > 5:
                self._times.pop(0)
            remaining = total - i
            if remaining > 0 and self._times:
                avg = sum(self._times) / len(self._times)
                eta = avg * remaining + self.between * remaining
                self.eta_fn(f"ETA ≈ {eta:.0f}s")

            self.status_fn(name, ok)
            if ok:
                success += 1
                self.log("  ✔  Done")
            else:
                failed.append(name)
                self.log("  ✘  Failed")
                if self.on_fail_ss:
                    folder = os.path.join(_DIR, "screenshots")
                    self._screenshot(folder, f"fail_{i}")

            if i < total and not self._stop:
                time.sleep(self.between)

        self.eta_fn("")
        self._stop_hotkeys()
        self.log(f"\n{'─'*40}")
        self.log(f"Done!   ✔ {success} succeeded   ✘ {len(failed)} failed")
        if failed:
            self.log("Failed: " + ", ".join(failed))
        return success, failed

    # ── Step runner ───────────────────────────────────────────────────────────

    def _run_steps(self, steps: list, name: str, depth: int = 0) -> bool:
        ind = "  " * (depth + 1)
        for idx, step in enumerate(steps, 1):
            if self._stop:
                return False
            self._wait_if_paused()
            if self._stop:
                return False

            if not step.get("enabled", True):
                self.log(f"{ind}[{idx}] ⊘ skipped — {step['type']} (disabled)")
                continue

            try:
                self._do(step, name, ind, idx, depth)
            except _SkipName:
                raise   # propagate up to start()
            except pyautogui.FailSafeException:
                self._stop_event.set()
                self.log("⛔ Safety stop — mouse moved to corner!")
                return False
            except Exception as e:
                self.log(f"{ind}[{idx}] ✘ Error in '{step['type']}': {e}")
                return False
        return True

    # ── Step executor ─────────────────────────────────────────────────────────

    def _do(self, step: dict, name: str, ind: str, idx: int, depth: int) -> None:
        t    = step["type"]
        dry  = self.dry_run
        vmap = {**self.variables, "name": name}

        def sub(text: str) -> str:
            return apply_variables(str(text), vmap)

        self.log(f"{ind}[{idx}] {t}  {self._fmt(step, vmap)}")

        if t == "comment":
            self.log(f"{ind}    💬 {sub(step.get('text', ''))}")
            return

        if t == "condition":
            self._do_condition(step, ind, dry)
            return

        if t == "click":
            if not dry: pyautogui.click(step["x"], step["y"])

        elif t == "double_click":
            if not dry: pyautogui.doubleClick(step["x"], step["y"])

        elif t == "right_click":
            if not dry: pyautogui.rightClick(step["x"], step["y"])

        elif t == "mouse_move":
            if not dry: pyautogui.moveTo(step["x"], step["y"], duration=0.2)

        elif t == "hotkey":
            keys = parse_hotkey(sub(step.get("keys", "enter")))
            if not dry:
                if len(keys) == 1:
                    pyautogui.press(keys[0])
                else:
                    pyautogui.hotkey(*keys)

        elif t == "type_text":
            text = sub(step.get("text", ""))
            if not dry: pyautogui.typewrite(text, interval=0.05)

        elif t == "clip_type":
            text = sub(step.get("text", ""))
            if not dry: type_text_safe(text)

        elif t == "clear_field":
            if not dry:
                pyautogui.click(step["x"], step["y"])
                time.sleep(0.1)
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.05)
                pyautogui.press("delete")

        elif t == "wait":
            secs = float(step.get("seconds", 1.0))
            end  = time.time() + secs
            while time.time() < end:
                if self._stop: return
                time.sleep(0.1)

        elif t == "pagedown":
            if not dry:
                for _ in range(int(step.get("times", 1))):
                    if self._stop: return
                    pyautogui.press("pagedown"); time.sleep(0.1)

        elif t == "pageup":
            if not dry:
                for _ in range(int(step.get("times", 1))):
                    if self._stop: return
                    pyautogui.press("pageup"); time.sleep(0.1)

        elif t == "scroll":
            if not dry:
                amt = int(step.get("clicks", 3))
                if step.get("direction", "down") == "down":
                    pyautogui.scroll(-amt, x=step["x"], y=step["y"])
                else:
                    pyautogui.scroll(amt,  x=step["x"], y=step["y"])

        elif t == "key_repeat":
            if not dry:
                for _ in range(int(step.get("times", 1))):
                    if self._stop: return
                    pyautogui.press(step.get("key", "tab")); time.sleep(0.05)

        elif t == "hold_key":
            if not dry:
                key  = step.get("key", "space")
                secs = float(step.get("seconds", 1.0))
                self._hold_key(key, secs)

        elif t == "loop":
            for rep in range(int(step.get("times", 2))):
                if self._stop: return
                self.log(f"{ind}  ↺ Loop {rep+1}/{step['times']}")
                ok = self._run_steps(step.get("steps", []), name, depth=depth + 1)
                if not ok:
                    raise RuntimeError("Loop sub-step failed")

        elif t == "screenshot":
            folder = os.path.join(_DIR, sub(step.get("folder", "screenshots")))
            self._screenshot(folder, name)

    def _do_condition(self, step: dict, ind: str, dry: bool) -> None:
        """Check foreground window title; raise _SkipName or stop if mismatch."""
        if dry:
            return
        title = ""
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd  = ctypes.windll.user32.GetForegroundWindow()
                buf   = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
                title = buf.value
            except Exception as e:
                self.log(f"{ind}  ⚠ condition: win32 title check failed: {e}")
        else:
            try:
                title = pyautogui.getActiveWindowTitle() or ""
            except Exception:
                pass

        needle = step.get("window_title", "")
        if needle and needle.lower() not in title.lower():
            action = step.get("action", "skip")
            self.log(f"{ind}  ⚠ Window '{needle}' not in '{title}' → {action}")
            if action == "stop":
                self._stop_event.set()
                raise RuntimeError(f"Condition stop: '{needle}' not found")
            else:
                raise _SkipName()

    def _hold_key(self, key: str, secs: float) -> None:
        if _PYNPUT_OK:
            kb = _PynKbC()
            try:
                pkey = getattr(_PynKey, key, None) or _PynKeyCode.from_char(key)
                kb.press(pkey)
                time.sleep(max(0.0, secs))
                kb.release(pkey)
                return
            except Exception:
                pass
        # Fallback: pyautogui
        pyautogui.keyDown(key)
        time.sleep(max(0.0, secs))
        pyautogui.keyUp(key)

    @staticmethod
    def _fmt(step: dict, vmap: dict) -> str:
        """One-liner summary for log, with variable substitution."""
        from .helpers import step_summary, apply_variables
        try:
            raw = step_summary(step)
            return apply_variables(raw, vmap)
        except Exception:
            return ""

    # ── Screenshot ────────────────────────────────────────────────────────────

    def _screenshot(self, folder: str, label: str = "ss") -> None:
        try:
            os.makedirs(folder, exist_ok=True)
            ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(folder, f"{label}_{ts}.png")
            pyautogui.screenshot(path)
            self.log(f"  📸 Saved → {path}")
        except Exception as e:
            self.log(f"  📸 Screenshot failed: {e}")

    # ── Pause helper ──────────────────────────────────────────────────────────

    def _wait_if_paused(self) -> None:
        while self._pause_event.is_set() and not self._stop_event.is_set():
            time.sleep(0.15)

    # ── Global hotkeys ────────────────────────────────────────────────────────

    def _start_hotkeys(self) -> None:
        if not _PYNPUT_OK:
            return

        def _on_press(key):
            try:
                name = getattr(key, "name", "").lower()
                if name == "f10":
                    self.stop()
                    self.log("⛔ F10 — stopped!")
                elif name == "f11":
                    if self._pause:
                        self.resume()
                        self.log("▶ F11 — resumed")
                    else:
                        self.pause()
                        self.log("⏸ F11 — paused")
            except Exception as e:
                print(f"[hotkey] {e}")

        self._kb_lst = _kb.Listener(on_press=_on_press)
        self._kb_lst.daemon = True
        self._kb_lst.start()

    def _stop_hotkeys(self) -> None:
        if self._kb_lst:
            try:
                self._kb_lst.stop()
            except Exception:
                pass
            self._kb_lst = None
