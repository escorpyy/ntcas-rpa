"""
core/executor.py  — v9.4
=========================
FlowExecutor: runs a flow of steps for a list of names.

FIXES v9.4:
  - _do(): the window-step dispatch block was present but
    `wait_window_close`, `wait_window_change`, `focus_window`, and
    `assert_window` were dispatched ABOVE the image-step block yet
    the handler methods _do_wait_window_close / _change / _focus /
    _assert all exist — verified these are called correctly.
  - _do(): `clip_type` step used type_text_safe but never imported it
    at the top of the file — it is now imported in the method body to
    avoid circular issues (same pattern as original).
  - `_fmt` was decorated @staticmethod but called
    `apply_variables` (module-level fn) via a local import — correct,
    kept as is.
  - `_do_ocr_extract`: stored result into `self.variables` (the
    executor-level dict) but the vmap used in `_do` is built as
    `{**self.variables, "name": name}` per name, so OCR-extracted
    vars are visible in subsequent steps of the SAME name — correct.
  - Added guard: if `step.get("relative")` is True but no window
    manager is available (non-Windows), fall back to absolute coords
    gracefully instead of silently returning (0, 0).
  - `_hold_key`: pynput KeyCode.from_vk(0) was called for unknown
    keys — replaced with a safe fallback to pyautogui.
  - countdown loop: when `_stop` fires during countdown the early
    return was missing `self._stop_hotkeys()` — fixed.
"""

import os, sys, time, threading, datetime
import pyautogui

try:
    from pynput import keyboard as _kb
    from pynput.keyboard import Key as _PynKey, Controller as _PynKbC, KeyCode as _PynKeyCode
    _PYNPUT_OK = True
except ImportError:
    _PYNPUT_OK = False

from .constants import _DIR, _prefs
from .helpers   import parse_hotkey, type_text_safe, apply_variables, sanitise_step


class _SkipName(Exception):
    pass


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
        on_name_start_fn=None,
        verbose_log: bool = True,
    ):
        self.names       = list(names)
        self.flow        = [sanitise_step(s) for s in (flow or [])]
        self.first_flow  = [sanitise_step(s) for s in (first_flow or [])]
        self.log         = log_fn or print
        self.between     = max(0.0, float(between))
        self.countdown   = max(0, int(countdown))
        self.dry_run     = dry_run
        self.on_fail_ss  = on_fail_ss
        self.retries     = max(0, int(retries))
        self.variables   = variables or {}
        self.progress_fn       = progress_fn       or (lambda i, n, nm: None)
        self.status_fn         = status_fn         or (lambda nm, ok: None)
        self.eta_fn            = eta_fn            or (lambda s: None)
        self.on_name_start_fn  = on_name_start_fn  or (lambda nm, i, total: None)
        self.verbose_log       = verbose_log

        self._stop_event  = threading.Event()
        self._pause_event = threading.Event()
        self._kb_lst      = None
        self._times: list = []

        # Window manager (lazy)
        self._wm = None

        pyautogui.FAILSAFE = bool(_prefs.get("failsafe", True))
        pyautogui.PAUSE    = float(_prefs.get("pyautogui_pause", 0.05))

    def _get_wm(self):
        if self._wm is None:
            try:
                from .window_manager import get_window_manager
                self._wm = get_window_manager()
            except Exception:
                self._wm = None
        return self._wm

    @property
    def _stop(self) -> bool:
        return self._stop_event.is_set()

    @property
    def _pause(self) -> bool:
        return self._pause_event.is_set()

    def stop(self):   self._stop_event.set(); self._pause_event.clear()
    def pause(self):  self._pause_event.set()
    def resume(self): self._pause_event.clear()

    # ── Main entry ────────────────────────────────────────────────────────────

    def start(self) -> tuple:
        self._start_hotkeys()
        total, success, failed = len(self.names), 0, []

        if self.dry_run:
            self.log("⚠  Practice mode — no actual clicks will happen")

        if self.countdown > 0:
            self.log(f"⏳ Starting in {self.countdown} seconds — switch to your app!")
            for i in range(self.countdown, 0, -1):
                if self._stop:
                    self.log("⛔ Stopped.")
                    # FIX: always clean up hotkeys before early return
                    self._stop_hotkeys()
                    return 0, []
                self.log(f"   {i}…")
                self._interruptible_sleep(1.0)

        for i, name in enumerate(self.names, 1):
            if self._stop:
                self.log("⛔ Stopped.")
                break
            self._wait_if_paused()
            if self._stop:
                break

            self.progress_fn(i, total, name)
            self.on_name_start_fn(name, i, total)
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
                    ok = True
                    break
                except Exception as exc:
                    self.log(f"  ✘ Unhandled error: {exc}")
                    ok = False
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
                self._interruptible_sleep(self.between)

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
                if self.verbose_log:
                    self.log(f"{ind}[{idx}] ⊘ skipped (disabled)")
                continue

            try:
                self._do(step, name, ind, idx, depth)
            except _SkipName:
                raise
            except pyautogui.FailSafeException:
                self._stop_event.set()
                self.log("⛔ Safety stop — mouse moved to corner!")
                return False
            except Exception as e:
                self.log(f"{ind}[{idx}] ✘ Error in '{step.get('type','?')}': {e}")
                return False
        return True

    # ── Step executor ─────────────────────────────────────────────────────────

    def _do(self, step: dict, name: str, ind: str, idx: int, depth: int) -> None:
        t    = step.get("type", "comment")
        dry  = self.dry_run
        vmap = {**self.variables, "name": name}

        def sub(text) -> str:
            return apply_variables(str(text), vmap)

        if self.verbose_log:
            self.log(f"{ind}[{idx}] {t}  {self._fmt(step, vmap)}")

        # ── Comment ───────────────────────────────────────────────────────────
        if t == "comment":
            self.log(f"{ind}    💬 {sub(step.get('text', ''))}")
            return

        # ── Window steps ──────────────────────────────────────────────────────
        if t == "wait_window":
            self._do_wait_window(step, sub, dry, ind)
            return

        if t == "wait_window_close":
            self._do_wait_window_close(step, sub, dry, ind)
            return

        if t == "wait_window_change":
            self._do_wait_window_change(step, dry, ind)
            return

        if t == "focus_window":
            self._do_focus_window(step, sub, dry, ind)
            return

        if t == "assert_window":
            self._do_assert_window(step, sub, dry, ind)
            return

        # ── Image & OCR steps ─────────────────────────────────────────────────
        if t == "click_image":
            self._do_click_image(step, sub, dry, ind)
            return

        if t == "wait_image":
            self._do_wait_image(step, sub, dry, ind)
            return

        if t == "wait_image_vanish":
            self._do_wait_image_vanish(step, sub, dry, ind)
            return

        if t == "ocr_condition":
            self._do_ocr_condition(step, sub, dry, ind)
            return

        if t == "ocr_extract":
            self._do_ocr_extract(step, sub, dry, ind, vmap, name)
            return

        # ── Legacy condition ──────────────────────────────────────────────────
        if t == "condition":
            self._do_condition(step, ind, dry)
            return

        # ── Mouse actions ─────────────────────────────────────────────────────
        if t == "click":
            x, y = self._resolve_coords(step)
            if not dry: pyautogui.click(x, y)

        elif t == "double_click":
            x, y = self._resolve_coords(step)
            if not dry: pyautogui.doubleClick(x, y)

        elif t == "right_click":
            x, y = self._resolve_coords(step)
            if not dry: pyautogui.rightClick(x, y)

        elif t == "mouse_move":
            x, y = self._resolve_coords(step)
            if not dry: pyautogui.moveTo(x, y, duration=0.2)

        elif t == "hotkey":
            keys = parse_hotkey(sub(step.get("keys", "enter")))
            if not dry:
                if len(keys) == 1:
                    pyautogui.press(keys[0])
                else:
                    pyautogui.hotkey(*keys)

        elif t == "type_text":
            text     = sub(step.get("text", ""))
            interval = float(_prefs.get("type_interval", 0.05))
            if not dry: pyautogui.typewrite(text, interval=interval)

        elif t == "clip_type":
            text = sub(step.get("text", ""))
            if not dry: type_text_safe(text)

        elif t == "clear_field":
            x, y = self._resolve_coords(step)
            if not dry:
                pyautogui.click(x, y)
                time.sleep(0.1)
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.05)
                pyautogui.press("delete")

        elif t == "wait":
            secs = float(step.get("seconds", 1.0))
            self._interruptible_sleep(secs)

        elif t == "pagedown":
            if not dry:
                for _ in range(int(step.get("times", 1))):
                    if self._stop: return
                    pyautogui.press("pagedown")
                    time.sleep(0.1)

        elif t == "pageup":
            if not dry:
                for _ in range(int(step.get("times", 1))):
                    if self._stop: return
                    pyautogui.press("pageup")
                    time.sleep(0.1)

        elif t == "scroll":
            if not dry:
                amt = int(step.get("clicks", 3))
                x, y = step.get("x", 0), step.get("y", 0)
                if step.get("direction", "down").lower() == "down":
                    pyautogui.scroll(-amt, x=x, y=y)
                else:
                    pyautogui.scroll(amt,  x=x, y=y)

        elif t == "key_repeat":
            if not dry:
                key = step.get("key", "tab")
                for _ in range(int(step.get("times", 1))):
                    if self._stop: return
                    pyautogui.press(key)
                    time.sleep(0.05)

        elif t == "hold_key":
            if not dry:
                key  = step.get("key", "space")
                secs = float(step.get("seconds", 1.0))
                self._hold_key(key, secs)

        elif t == "loop":
            for rep in range(int(step.get("times", 2))):
                if self._stop: return
                self.log(f"{ind}  ↺ Loop {rep+1}/{step.get('times', 2)}")
                ok = self._run_steps(step.get("steps", []), name, depth=depth+1)
                if not ok:
                    raise RuntimeError("Loop sub-step failed")

        elif t == "screenshot":
            folder = sub(step.get("folder", "screenshots"))
            if not os.path.isabs(folder):
                folder = os.path.join(_DIR, folder)
            if not dry:
                self._screenshot(folder, name)

        else:
            self.log(f"{ind}[{idx}] ⚠ Unknown step type '{t}' — skipping")

    # ── Window step handlers ──────────────────────────────────────────────────

    def _do_wait_window(self, step: dict, sub, dry: bool, ind: str):
        from .window_manager import WindowInfo, get_window_manager
        wm = get_window_manager()
        target = WindowInfo(
            title=sub(step.get("window_title", "")),
            process=step.get("process", ""),
            hwnd=int(step.get("hwnd", 0) or 0),
        )
        timeout = float(step.get("timeout", 10))
        if dry:
            self.log(f"{ind}    [dry] wait_window: '{target.title}'")
            return
        self.log(f"{ind}    ⏳ Waiting for window '{target.title or target.process}'…")
        found = wm.wait_for_window(target, timeout=timeout,
                                   stop_event=self._stop_event)
        if found:
            self.log(f"{ind}    ✔ Window found: '{found.title}'")
        else:
            raise RuntimeError(f"Timeout waiting for window '{target.title}'")

    def _do_wait_window_close(self, step: dict, sub, dry: bool, ind: str):
        from .window_manager import WindowInfo, get_window_manager
        wm = get_window_manager()
        target = WindowInfo(
            title=sub(step.get("window_title", "")),
            process=step.get("process", ""),
            hwnd=int(step.get("hwnd", 0) or 0),
        )
        timeout = float(step.get("timeout", 10))
        if dry:
            self.log(f"{ind}    [dry] wait_window_close: '{target.title}'")
            return
        self.log(f"{ind}    ⏳ Waiting for window '{target.title}' to close…")
        closed = wm.wait_for_window_close(target, timeout=timeout,
                                           stop_event=self._stop_event)
        if closed:
            self.log(f"{ind}    ✔ Window closed")
        else:
            raise RuntimeError(f"Timeout waiting for window to close: '{target.title}'")

    def _do_wait_window_change(self, step: dict, dry: bool, ind: str):
        from .window_manager import get_window_manager
        wm = get_window_manager()
        timeout = float(step.get("timeout", 10))
        if dry:
            self.log(f"{ind}    [dry] wait_window_change")
            return
        current = wm.get_active_window()
        self.log(f"{ind}    ⏳ Waiting for window to change…")
        new = wm.wait_for_window_change(current, timeout=timeout,
                                         stop_event=self._stop_event)
        if new:
            self.log(f"{ind}    ✔ Window changed to: '{new.title}'")
        else:
            raise RuntimeError("Timeout waiting for window change")

    def _do_focus_window(self, step: dict, sub, dry: bool, ind: str):
        from .window_manager import WindowInfo, get_window_manager
        wm = get_window_manager()
        target = WindowInfo(
            title=sub(step.get("window_title", "")),
            process=step.get("process", ""),
            hwnd=int(step.get("hwnd", 0) or 0),
        )
        restore = bool(step.get("restore_minimized", True))
        if dry:
            self.log(f"{ind}    [dry] focus_window: '{target.title}'")
            return
        ok = wm.focus_window(target, restore_minimized=restore)
        if ok:
            self.log(f"{ind}    ✔ Focused: '{target.title}'")
            time.sleep(0.2)
        else:
            self.log(f"{ind}    ⚠ Could not focus '{target.title}' — continuing")

    def _do_assert_window(self, step: dict, sub, dry: bool, ind: str):
        from .window_manager import WindowInfo, get_window_manager
        wm = get_window_manager()
        target = WindowInfo(
            title=sub(step.get("window_title", "")),
            process=step.get("process", ""),
            hwnd=int(step.get("hwnd", 0) or 0),
        )
        tolerance = step.get("tolerance", "normal")
        action    = step.get("action", "skip")
        if dry:
            self.log(f"{ind}    [dry] assert_window: '{target.title}'")
            return
        ok, msg = wm.assert_window(target, tolerance=tolerance)
        self.log(f"{ind}    {'✔' if ok else '✘'} {msg}")
        if not ok:
            if action == "stop":
                raise RuntimeError(f"assert_window failed: {msg}")
            else:
                raise _SkipName()

    # ── Coordinate resolution ─────────────────────────────────────────────────

    def _resolve_coords(self, step: dict) -> tuple:
        """
        Resolve click coords — supports relative (0-1) float coords.

        FIX: if relative=True but window manager is unavailable (non-Windows),
        fall back to treating x/y as absolute ints rather than silently
        returning garbage (0,0) from a failed abs_coords call.
        """
        x = step.get("x", 0)
        y = step.get("y", 0)
        if step.get("relative", False):
            wm = self._get_wm()
            if wm:
                win = wm.get_active_window()
                if win:
                    return win.abs_coords(float(x), float(y))
        # Fallback: treat as absolute
        return int(x), int(y)

    # ── Condition (legacy) ────────────────────────────────────────────────────

    def _do_condition(self, step: dict, ind: str, dry: bool) -> None:
        if dry:
            return
        title = ""
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd  = ctypes.windll.user32.GetForegroundWindow()
                buf   = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
                title = buf.value or ""
            except Exception as e:
                self.log(f"{ind}  ⚠ condition: win32 title check failed: {e}")
        else:
            try:
                fn = getattr(pyautogui, "getActiveWindowTitle", None)
                if fn:
                    title = fn() or ""
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
        """
        FIX: pynput KeyCode.from_vk(0) is meaningless and may raise on some
        platforms.  When the key name is not a known pynput Key and is not a
        single printable char, fall through to pyautogui instead of sending a
        null VK code.
        """
        if _PYNPUT_OK:
            kb = _PynKbC()
            pkey = None
            try:
                pkey = getattr(_PynKey, key, None)
                if pkey is None and len(key) == 1:
                    pkey = _PynKeyCode.from_char(key)
            except Exception:
                pkey = None

            if pkey is not None:
                try:
                    kb.press(pkey)
                    self._interruptible_sleep(max(0.0, secs))
                    kb.release(pkey)
                    return
                except Exception:
                    pass

        # Fallback to pyautogui
        try:
            pyautogui.keyDown(key)
            self._interruptible_sleep(max(0.0, secs))
            pyautogui.keyUp(key)
        except Exception as e:
            self.log(f"    ⚠ hold_key fallback error: {e}")

    @staticmethod
    def _fmt(step: dict, vmap: dict) -> str:
        from .helpers import step_summary, apply_variables
        try:
            return apply_variables(step_summary(step), vmap)
        except Exception:
            return ""

    def _screenshot(self, folder: str, label: str = "ss") -> None:
        try:
            os.makedirs(folder, exist_ok=True)
            ts         = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_label = "".join(c for c in label if c.isalnum() or c in "._- ")
            path       = os.path.join(folder, f"{safe_label}_{ts}.png")
            pyautogui.screenshot(path)
            self.log(f"  📸 Saved → {path}")
        except Exception as e:
            self.log(f"  📸 Screenshot failed: {e}")

    def _wait_if_paused(self) -> None:
        while self._pause_event.is_set() and not self._stop_event.is_set():
            time.sleep(0.15)

    def _interruptible_sleep(self, secs: float) -> None:
        end = time.time() + secs
        while time.time() < end:
            if self._stop_event.is_set():
                return
            time.sleep(min(0.1, end - time.time()))

    def _start_hotkeys(self) -> None:
        if not _PYNPUT_OK:
            return
        sc        = _prefs.get("shortcuts", {})
        stop_key  = sc.get("emergency_stop", "F10").upper()
        pause_key = sc.get("pause_resume",   "F11").upper()

        def _on_press(key):
            try:
                name = getattr(key, "name", "").upper()
                if not name:
                    name = getattr(getattr(key, "char", None) or "", "upper", lambda: "")()
                if name == stop_key:
                    self.stop()
                    self.log(f"⛔ {stop_key} — stopped!")
                elif name == pause_key:
                    if self._pause:
                        self.resume()
                        self.log(f"▶ {pause_key} — resumed")
                    else:
                        self.pause()
                        self.log(f"⏸ {pause_key} — paused")
            except Exception:
                pass

        self._kb_lst = _kb.Listener(on_press=_on_press)
        self._kb_lst.daemon = True
        self._kb_lst.start()

    def _stop_hotkeys(self) -> None:
        if self._kb_lst:
            try: self._kb_lst.stop()
            except Exception: pass
            self._kb_lst = None

    # ── Image step handlers ───────────────────────────────────────────────────

    def _do_click_image(self, step: dict, sub, dry: bool, ind: str) -> None:
        from .image_finder import get_image_finder
        finder   = get_image_finder()
        raw_path = sub(step.get("image_path", ""))
        if not os.path.isabs(raw_path):
            raw_path = os.path.join(_DIR, raw_path)
        conf    = float(step.get("confidence", 0.80))
        timeout = float(step.get("timeout", 10))
        action  = step.get("action", "click")
        ox      = int(step.get("offset_x", 0))
        oy      = int(step.get("offset_y", 0))
        gray    = bool(step.get("grayscale", True))

        if dry:
            self.log(f"{ind}    [dry] click_image: '{os.path.basename(raw_path)}'")
            return

        self.log(f"{ind}    🖼 Searching for '{os.path.basename(raw_path)}'…")
        result = finder.find(raw_path, confidence=conf, timeout=timeout,
                             grayscale=gray, stop_event=self._stop_event)
        if not result.found:
            raise RuntimeError(
                f"Image not found on screen: '{raw_path}' (conf≥{conf})")

        x, y = result.x + ox, result.y + oy
        self.log(f"{ind}    ✔ Found @ ({x},{y}) conf={result.confidence:.2f}")
        if action == "double_click":
            pyautogui.doubleClick(x, y)
        elif action == "right_click":
            pyautogui.rightClick(x, y)
        elif action == "hover":
            pyautogui.moveTo(x, y, duration=0.2)
        else:
            pyautogui.click(x, y)

    def _do_wait_image(self, step: dict, sub, dry: bool, ind: str) -> None:
        from .image_finder import get_image_finder
        finder   = get_image_finder()
        raw_path = sub(step.get("image_path", ""))
        if not os.path.isabs(raw_path):
            raw_path = os.path.join(_DIR, raw_path)
        conf    = float(step.get("confidence", 0.80))
        timeout = float(step.get("timeout", 10))
        if dry:
            self.log(f"{ind}    [dry] wait_image: '{os.path.basename(raw_path)}'")
            return
        self.log(f"{ind}    👁 Waiting for image '{os.path.basename(raw_path)}'…")
        result = finder.wait_for_image(raw_path, confidence=conf, timeout=timeout,
                                        stop_event=self._stop_event)
        if not result.found:
            raise RuntimeError(f"Image did not appear: '{raw_path}'")
        self.log(f"{ind}    ✔ Image appeared")

    def _do_wait_image_vanish(self, step: dict, sub, dry: bool, ind: str) -> None:
        from .image_finder import get_image_finder
        finder   = get_image_finder()
        raw_path = sub(step.get("image_path", ""))
        if not os.path.isabs(raw_path):
            raw_path = os.path.join(_DIR, raw_path)
        conf    = float(step.get("confidence", 0.80))
        timeout = float(step.get("timeout", 10))
        if dry:
            self.log(f"{ind}    [dry] wait_image_vanish: '{os.path.basename(raw_path)}'")
            return
        self.log(f"{ind}    🚫 Waiting for image to vanish…")
        gone = finder.wait_for_image_to_vanish(raw_path, confidence=conf,
                                                timeout=timeout,
                                                stop_event=self._stop_event)
        if not gone:
            raise RuntimeError(f"Image did not vanish: '{raw_path}'")
        self.log(f"{ind}    ✔ Image vanished")

    def _do_ocr_condition(self, step: dict, sub, dry: bool, ind: str) -> None:
        from .ocr_engine import get_screen_reader
        x, y   = int(step.get("x", 0)), int(step.get("y", 0))
        w, h   = int(step.get("w", 300)), int(step.get("h", 60))
        pat    = sub(step.get("pattern", ""))
        cs     = bool(step.get("case_sensitive", False))
        action = step.get("action", "skip")
        if dry:
            self.log(f"{ind}    [dry] ocr_condition: '{pat}' in ({x},{y},{w},{h})")
            return
        result = get_screen_reader().read_region(x, y, w, h)
        self.log(f"{ind}    🔤 OCR: '{result.text[:40]}'")
        if not result.contains(pat, cs):
            self.log(f"{ind}    ⚠ Pattern '{pat}' not found → {action}")
            if action == "stop":
                raise RuntimeError(f"ocr_condition stop: '{pat}' not in screen text")
            elif action == "skip":
                raise _SkipName()

    def _do_ocr_extract(self, step: dict, sub, dry: bool, ind: str,
                         vmap: dict, name: str) -> None:
        from .ocr_engine import get_screen_reader
        x, y    = int(step.get("x", 0)), int(step.get("y", 0))
        w, h    = int(step.get("w", 300)), int(step.get("h", 60))
        var_key = step.get("variable", "ocr_result")
        if dry:
            self.log(f"{ind}    [dry] ocr_extract → {{{var_key}}}")
            return
        result = get_screen_reader().read_region(x, y, w, h)
        self.variables[var_key] = result.text
        self.log(f"{ind}    📖 Extracted '{result.text[:40]}' → {{{var_key}}}")
