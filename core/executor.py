'''
core/executor.py  — v9.5
=========================
FlowExecutor: runs a flow of steps for a list of names.

NEW v9.5 (added directly, no monkey-patching):
  - start(resume=True): checkpoint/resume-from-failure
  - row_vars kwarg: per-name column-mapped variables
  - if_condition, label, goto step types in _do()
  - _GotoSignal + goto-aware _run_steps loop



'''

import os, sys, time, threading, datetime, copy
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


class _GotoSignal(Exception):
    def __init__(self, label: str):
        self.label = label
        super().__init__(label)


class FlowExecutor:
    def __init__(
        self,
        names,
        flow,
        first_flow       = None,
        log_fn           = None,
        between: float   = 1.0,
        countdown: int   = 5,
        dry_run: bool    = False,
        on_fail_ss: bool = False,
        retries: int     = 0,
        variables: dict  = None,
        progress_fn      = None,
        status_fn        = None,
        eta_fn           = None,
        on_name_start_fn = None,
        verbose_log: bool= True,
        row_vars: dict   = None,
        flow_path: str   = "",
    ):
        self.names      = list(names)
        self.flow       = [sanitise_step(s) for s in (flow or [])]
        self.first_flow = [sanitise_step(s) for s in (first_flow or [])]
        self.log        = log_fn or print
        self.between    = max(0.0, float(between))
        self.countdown  = max(0, int(countdown))
        self.dry_run    = dry_run
        self.on_fail_ss = on_fail_ss
        self.retries    = max(0, int(retries))
        self.variables  = copy.deepcopy(variables) if variables else {}
        self.progress_fn      = progress_fn       or (lambda i,n,nm: None)
        self.status_fn        = status_fn         or (lambda nm,ok: None)
        self.eta_fn           = eta_fn            or (lambda s: None)
        self.on_name_start_fn = on_name_start_fn  or (lambda nm,i,total: None)
        self.verbose_log      = verbose_log
        self.row_vars   = row_vars  or {}
        self.flow_path  = flow_path

        self._stop_event  = threading.Event()
        self._pause_event = threading.Event()
        self._kb_lst      = None
        self._times: list = []
        self._wm          = None

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

    def start(self, resume: bool = False) -> tuple:
        from .checkpoint import CheckpointManager

        cp = CheckpointManager(
            names     = self.names,
            flow      = self.flow,
            settings  = {"countdown": self.countdown,
                         "between":   self.between,
                         "dry_run":   self.dry_run},
            flow_path = self.flow_path,
        )

        if resume:
            existing = CheckpointManager.load_for_flow(self.flow)
            if existing:
                done_set   = set(existing._completed)
                self.names = [n for n in self.names if n not in done_set]
                cp._completed = list(existing._completed)
                cp._failed    = list(existing._failed)
                cp._remaining = list(self.names)
                self.log(
                    f"\\u23e9 Resuming: {len(existing._completed)} already done, "
                    f"{len(self.names)} remaining."
                )

        self._start_hotkeys()
        total, success, failed = len(self.names), 0, []

        if self.dry_run:
            self.log("\\u26a0  Practice mode \\u2014 no actual clicks will happen")

        if self.countdown > 0:
            self.log(f"\\u23f3 Starting in {self.countdown} seconds \\u2014 switch to your app!")
            for i in range(self.countdown, 0, -1):
                if self._stop:
                    self._stop_hotkeys(); return 0, []
                self.log(f"   {i}\\u2026")
                self._interruptible_sleep(1.0)

        for i, name in enumerate(self.names, 1):
            if self._stop:
                self.log("\\u26d4 Stopped."); break
            self._wait_if_paused()
            if self._stop: break

            self.progress_fn(i, total, name)
            self.on_name_start_fn(name, i, total)
            self.log(f"\\n[{i}/{total}]  \\u2192  {name}")

            this_flow = (
                (self.first_flow + self.flow)
                if (i == 1 and self.first_flow) else self.flow
            )

            t0 = time.time()
            ok = False
            for attempt in range(self.retries + 1):
                if self._stop: break
                if attempt > 0:
                    self.log(f"  \\u21bb Retry {attempt}/{self.retries}\\u2026")
                try:
                    ok = self._run_steps(this_flow, name)
                except _SkipName:
                    self.log("  \\u21b7 Skipping name (condition mismatch).")
                    ok = True; break
                except Exception as exc:
                    self.log(f"  \\u2718 Unhandled error: {exc}")
                    ok = False
                if ok: break

            elapsed = time.time() - t0
            self._times.append(elapsed)
            if len(self._times) > 5: self._times.pop(0)
            remaining = total - i
            if remaining > 0 and self._times:
                avg = sum(self._times) / len(self._times)
                self.eta_fn(f"ETA \\u2248 {avg*remaining+self.between*remaining:.0f}s")

            self.status_fn(name, ok)
            cp.mark_done(name, ok)

            if ok:
                success += 1
                self.log("  \\u2714  Done")
            else:
                failed.append(name)
                self.log("  \\u2718  Failed")
                if self.on_fail_ss:
                    self._screenshot(os.path.join(_DIR, "screenshots"), f"fail_{i}")

            if i < total and not self._stop:
                self._interruptible_sleep(self.between)

        self.eta_fn("")
        self._stop_hotkeys()
        self.log(f"\\n{chr(8212)*40}")
        self.log(f"Done!   \\u2714 {success} succeeded   \\u2718 {len(failed)} failed")
        if failed:
            self.log("Failed: " + ", ".join(failed))

        if not self._stop_event.is_set() and len(cp.get_remaining()) == 0:
            cp.clear()
            self.log("\\u2714 Checkpoint cleared.")
        else:
            rem = len(cp.get_remaining())
            if rem > 0:
                self.log(f"\\U0001f4be Checkpoint saved \\u2014 {rem} name(s) remaining. Use Resume to continue.")

        return success, failed

    def _run_steps(self, steps: list, name: str, depth: int = 0) -> bool:
        ind        = "  " * (depth + 1)
        i          = 0
        jump_count = 0
        MAX_JUMPS  = 200

        while i < len(steps):
            if self._stop: return False
            self._wait_if_paused()
            if self._stop: return False

            step = steps[i]
            if not step.get("enabled", True):
                if self.verbose_log:
                    self.log(f"{ind}[{i+1}] \\u2298 skipped (disabled)")
                i += 1; continue

            try:
                self._do(step, name, ind, i + 1, depth)

            except _GotoSignal as gs:
                target = next(
                    (j for j, s in enumerate(steps)
                     if s.get("type") == "label"
                     and s.get("label_name") == gs.label),
                    None,
                )
                if target is None:
                    self.log(f"{ind}  \\u26a0 goto \\u2019{gs.label}\\u2019 \\u2014 label not found, continuing")
                    i += 1; continue
                jump_count += 1
                if jump_count > MAX_JUMPS:
                    raise RuntimeError(
                        f"goto loop limit ({MAX_JUMPS}) exceeded near label \\u2019{gs.label}\\u2019")
                i = target; continue

            except _SkipName: raise
            except pyautogui.FailSafeException:
                self._stop_event.set()
                self.log("\\u26d4 Safety stop \\u2014 mouse moved to corner!")
                return False
            except Exception as e:
                self.log(f"{ind}[{i+1}] \\u2718 Error in \\u2019{step.get(\\\"type\\\",\\\"?\\\")!r}\\u2019: {e}")
                return False

            i += 1
        return True

    def _do(self, step: dict, name: str, ind: str, idx: int, depth: int) -> None:
        t   = step.get("type", "comment")
        dry = self.dry_run
        row_extra = self.row_vars.get(name, {})
        vmap      = {**self.variables, **row_extra, "name": name}

        def sub(text) -> str:
            return apply_variables(str(text), vmap)

        if self.verbose_log:
            self.log(f"{ind}[{idx}] {t}  {self._fmt(step, vmap)}")

        if t == "comment":
            self.log(f"{ind}    \\U0001f4ac {sub(step.get(\\\"text\\\", \\\"\\\"))}"); return

        if t == "if_condition":
            self._do_if_condition(step, name, ind, depth, vmap); return

        if t == "label":
            self.log(f"{ind}    \\U0001f3f7 label: {step.get(\\\"label_name\\\", \\\"?\\\")!r}"); return

        if t == "goto":
            label = step.get("label_name", "")
            self.log(f"{ind}    \\u21a9 goto {label!r}")
            raise _GotoSignal(label)

        if t == "wait_window":      self._do_wait_window(step, sub, dry, ind); return
        if t == "wait_window_close": self._do_wait_window_close(step, sub, dry, ind); return
        if t == "wait_window_change": self._do_wait_window_change(step, dry, ind); return
        if t == "focus_window":     self._do_focus_window(step, sub, dry, ind); return
        if t == "assert_window":    self._do_assert_window(step, sub, dry, ind); return
        if t == "click_image":      self._do_click_image(step, sub, dry, ind); return
        if t == "wait_image":       self._do_wait_image(step, sub, dry, ind); return
        if t == "wait_image_vanish": self._do_wait_image_vanish(step, sub, dry, ind); return
        if t == "ocr_condition":    self._do_ocr_condition(step, sub, dry, ind); return
        if t == "ocr_extract":      self._do_ocr_extract(step, sub, dry, ind, vmap, name); return
        if t == "condition":        self._do_condition(step, ind, dry); return

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
                pyautogui.press(keys[0]) if len(keys)==1 else pyautogui.hotkey(*keys)
        elif t == "type_text":
            text = sub(step.get("text", ""))
            interval = float(_prefs.get("type_interval", 0.05))
            if not dry: pyautogui.typewrite(text, interval=interval)
        elif t == "clip_type":
            text = sub(step.get("text", ""))
            if not dry: type_text_safe(text)
        elif t == "clear_field":
            x, y = self._resolve_coords(step)
            if not dry:
                pyautogui.click(x, y); time.sleep(0.1)
                pyautogui.hotkey("ctrl","a"); time.sleep(0.05)
                pyautogui.press("delete")
        elif t == "wait":
            self._interruptible_sleep(float(step.get("seconds", 1.0)))
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
                x, y = step.get("x",0), step.get("y",0)
                d = step.get("direction","down").lower()
                pyautogui.scroll(-amt if d=="down" else amt, x=x, y=y)
        elif t == "key_repeat":
            if not dry:
                key = step.get("key","tab")
                for _ in range(int(step.get("times",1))):
                    if self._stop: return
                    pyautogui.press(key); time.sleep(0.05)
        elif t == "hold_key":
            if not dry:
                self._hold_key(step.get("key","space"), float(step.get("seconds",1.0)))
        elif t == "loop":
            n_times = int(step.get("times",2))
            for rep in range(n_times):
                if self._stop: return
                self.log(f"{ind}  \\u21ba Loop {rep+1}/{n_times}")
                ok = self._run_steps(step.get("steps",[]), name, depth=depth+1)
                if not ok:
                    raise RuntimeError(f"Loop sub-step failed at repetition {rep+1}/{n_times}")
        elif t == "screenshot":
            folder = sub(step.get("folder","screenshots"))
            if not os.path.isabs(folder): folder = os.path.join(_DIR, folder)
            if not dry: self._screenshot(folder, name)
        else:
            self.log(f"{ind}[{idx}] \\u26a0 Unknown step type {t!r} \\u2014 skipping")

    def _do_if_condition(self, step, name, ind, depth, vmap):
        import re as _re
        condition      = step.get("condition","contains")
        source         = step.get("source","variable")
        expected       = apply_variables(str(step.get("value","")), vmap)
        case_sensitive = bool(step.get("case_sensitive",False))

        actual = ""
        if source == "variable":
            actual = apply_variables(str(step.get("variable","{name}")), vmap)
        elif source == "ocr":
            try:
                from .ocr_engine import get_screen_reader
                x,y,w,h = int(step.get("x",0)),int(step.get("y",0)),int(step.get("w",300)),int(step.get("h",60))
                actual = get_screen_reader().read_region(x,y,w,h).text
            except Exception as e:
                self.log(f"{ind}  \\u26a0 if_condition OCR failed: {e}")
        elif source == "window_title":
            try:
                if sys.platform == "win32":
                    import ctypes
                    hwnd = ctypes.windll.user32.GetForegroundWindow()
                    buf  = ctypes.create_unicode_buffer(512)
                    ctypes.windll.user32.GetWindowTextW(hwnd, buf, 512)
                    actual = buf.value or ""
            except Exception: pass
        elif source == "clipboard":
            try:
                import pyperclip; actual = pyperclip.paste() or ""
            except Exception: pass

        a = actual   if case_sensitive else actual.lower()
        e = expected if case_sensitive else expected.lower()

        result = False
        if   condition == "contains":     result = e in a
        elif condition == "not_contains": result = e not in a
        elif condition == "equals":       result = a == e
        elif condition == "not_equals":   result = a != e
        elif condition == "startswith":   result = a.startswith(e)
        elif condition == "endswith":     result = a.endswith(e)
        elif condition == "empty":        result = a.strip() == ""
        elif condition == "not_empty":    result = a.strip() != ""
        elif condition == "always_true":  result = True
        elif condition == "regex":
            flags = 0 if case_sensitive else _re.IGNORECASE
            try:    result = bool(_re.search(expected, actual, flags))
            except: result = False
        elif condition in ("gt","lt","gte","lte"):
            try:
                fa,fe = float(actual.replace(",","")), float(expected.replace(",",""))
                result = (fa>fe if condition=="gt" else fa<fe if condition=="lt"
                          else fa>=fe if condition=="gte" else fa<=fe)
            except ValueError: result = False

        trunc = lambda s: (s[:40]+"\\u2026") if len(s)>40 else s
        self.log(f"{ind}    \\U0001f500 if [{source}] {trunc(actual)!r} {condition} {trunc(expected)!r} \\u2192 {'TRUE' if result else 'FALSE'}")

        branch_key  = "then_steps" if result else "else_steps"
        branch_name = "THEN" if result else "ELSE"
        sub_steps   = step.get(branch_key, [])

        if not sub_steps:
            self.log(f"{ind}    (empty {branch_name} branch \\u2014 nothing to do)"); return

        self.log(f"{ind}    \\u2192 running {branch_name} branch ({len(sub_steps)} step(s))")
        ok = self._run_steps(sub_steps, name, depth=depth+1)
        if not ok:
            raise RuntimeError(f"if_condition {branch_name} branch failed")

    def _do_wait_window(self, step, sub, dry, ind):
        from .window_manager import WindowInfo, get_window_manager
        wm = get_window_manager()
        target = WindowInfo(title=sub(step.get("window_title","")),
                            process=step.get("process",""),
                            hwnd=int(step.get("hwnd",0) or 0))
        timeout = float(step.get("timeout",10))
        if dry: self.log(f"{ind}    [dry] wait_window: {target.title!r}"); return
        self.log(f"{ind}    \\u23f3 Waiting for window {(target.title or target.process)!r}\\u2026")
        found = wm.wait_for_window(target, timeout=timeout, stop_event=self._stop_event)
        if found: self.log(f"{ind}    \\u2714 Window found: {found.title!r}")
        else: raise RuntimeError(f"Timeout waiting for window {target.title!r}")

    def _do_wait_window_close(self, step, sub, dry, ind):
        from .window_manager import WindowInfo, get_window_manager
        wm = get_window_manager()
        target = WindowInfo(title=sub(step.get("window_title","")),
                            process=step.get("process",""),
                            hwnd=int(step.get("hwnd",0) or 0))
        timeout = float(step.get("timeout",10))
        if dry: self.log(f"{ind}    [dry] wait_window_close: {target.title!r}"); return
        self.log(f"{ind}    \\u23f3 Waiting for {target.title!r} to close\\u2026")
        closed = wm.wait_for_window_close(target, timeout=timeout, stop_event=self._stop_event)
        if closed: self.log(f"{ind}    \\u2714 Window closed")
        else: raise RuntimeError(f"Timeout waiting for window to close: {target.title!r}")

    def _do_wait_window_change(self, step, dry, ind):
        from .window_manager import get_window_manager
        wm = get_window_manager()
        timeout = float(step.get("timeout",10))
        if dry: self.log(f"{ind}    [dry] wait_window_change"); return
        current = wm.get_active_window()
        self.log(f"{ind}    \\u23f3 Waiting for window to change\\u2026")
        new = wm.wait_for_window_change(current, timeout=timeout, stop_event=self._stop_event)
        if new: self.log(f"{ind}    \\u2714 Window changed to: {new.title!r}")
        else: raise RuntimeError("Timeout waiting for window change")

    def _do_focus_window(self, step, sub, dry, ind):
        from .window_manager import WindowInfo, get_window_manager
        wm = get_window_manager()
        target = WindowInfo(title=sub(step.get("window_title","")),
                            process=step.get("process",""),
                            hwnd=int(step.get("hwnd",0) or 0))
        restore = bool(step.get("restore_minimized",True))
        if dry: self.log(f"{ind}    [dry] focus_window: {target.title!r}"); return
        ok = wm.focus_window(target, restore_minimized=restore)
        self.log(f"{ind}    {'\\u2714 Focused' if ok else '\\u26a0 Could not focus'}: {target.title!r}")
        if ok: time.sleep(0.2)

    def _do_assert_window(self, step, sub, dry, ind):
        from .window_manager import WindowInfo, get_window_manager
        wm = get_window_manager()
        target = WindowInfo(title=sub(step.get("window_title","")),
                            process=step.get("process",""),
                            hwnd=int(step.get("hwnd",0) or 0))
        tolerance = step.get("tolerance","normal")
        action    = step.get("action","skip")
        if dry: self.log(f"{ind}    [dry] assert_window: {target.title!r}"); return
        ok, msg = wm.assert_window(target, tolerance=tolerance)
        self.log(f"{ind}    {'\\u2714' if ok else '\\u2718'} {msg}")
        if not ok:
            if action == "stop": raise RuntimeError(f"assert_window failed: {msg}")
            else: raise _SkipName()

    def _resolve_coords(self, step):
        x = step.get("x",0); y = step.get("y",0)
        if step.get("relative",False):
            wm = self._get_wm()
            if wm:
                win = wm.get_active_window()
                if win: return win.abs_coords(float(x), float(y))
        try: return int(float(x)), int(float(y))
        except: return 0, 0

    def _do_condition(self, step, ind, dry):
        if dry: return
        title = ""
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                buf  = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, 256)
                title = buf.value or ""
            except Exception as e:
                self.log(f"{ind}  \\u26a0 condition: {e}")
        else:
            try:
                fn = getattr(pyautogui,"getActiveWindowTitle",None)
                if fn: title = fn() or ""
            except Exception: pass
        needle = step.get("window_title","")
        if needle and needle.lower() not in title.lower():
            action = step.get("action","skip")
            self.log(f"{ind}  \\u26a0 Window {needle!r} not in {title!r} \\u2192 {action}")
            if action == "stop": self._stop_event.set(); raise RuntimeError(f"Condition stop: {needle!r} not found")
            else: raise _SkipName()

    def _hold_key(self, key, secs):
        if _PYNPUT_OK:
            kb   = _PynKbC(); pkey = None
            try:
                pkey = getattr(_PynKey,key,None)
                if pkey is None and len(key)==1: pkey = _PynKeyCode.from_char(key)
            except Exception: pkey = None
            if pkey is not None:
                try:
                    kb.press(pkey); self._interruptible_sleep(max(0.0,secs)); kb.release(pkey); return
                except Exception: pass
        try:
            pyautogui.keyDown(key); self._interruptible_sleep(max(0.0,secs)); pyautogui.keyUp(key)
        except Exception as e:
            self.log(f"    \\u26a0 hold_key error: {e}")

    def _do_click_image(self, step, sub, dry, ind):
        from .image_finder import get_image_finder
        finder = get_image_finder()
        raw_path = sub(step.get("image_path",""))
        if not os.path.isabs(raw_path): raw_path = os.path.join(_DIR, raw_path)
        conf,timeout,action = float(step.get("confidence",0.80)),float(step.get("timeout",10)),step.get("action","click")
        ox,oy = int(step.get("offset_x",0)),int(step.get("offset_y",0))
        gray  = bool(step.get("grayscale",True))
        if dry: self.log(f"{ind}    [dry] click_image: {os.path.basename(raw_path)!r}"); return
        self.log(f"{ind}    \\U0001f5bc Searching for {os.path.basename(raw_path)!r}\\u2026")
        result = finder.find(raw_path,confidence=conf,timeout=timeout,grayscale=gray,stop_event=self._stop_event)
        if not result.found: raise RuntimeError(f"Image not found: {raw_path!r} (conf\\u2265{conf})")
        x,y = result.x+ox, result.y+oy
        self.log(f"{ind}    \\u2714 Found @ ({x},{y}) conf={result.confidence:.2f}")
        if action=="double_click": pyautogui.doubleClick(x,y)
        elif action=="right_click": pyautogui.rightClick(x,y)
        elif action=="hover": pyautogui.moveTo(x,y,duration=0.2)
        else: pyautogui.click(x,y)

    def _do_wait_image(self, step, sub, dry, ind):
        from .image_finder import get_image_finder
        finder = get_image_finder()
        raw_path = sub(step.get("image_path",""))
        if not os.path.isabs(raw_path): raw_path = os.path.join(_DIR, raw_path)
        conf,timeout = float(step.get("confidence",0.80)),float(step.get("timeout",10))
        if dry: self.log(f"{ind}    [dry] wait_image: {os.path.basename(raw_path)!r}"); return
        self.log(f"{ind}    \\U0001f441 Waiting for {os.path.basename(raw_path)!r}\\u2026")
        result = finder.wait_for_image(raw_path,confidence=conf,timeout=timeout,stop_event=self._stop_event)
        if not result.found: raise RuntimeError(f"Image did not appear: {raw_path!r}")
        self.log(f"{ind}    \\u2714 Image appeared")

    def _do_wait_image_vanish(self, step, sub, dry, ind):
        from .image_finder import get_image_finder
        finder = get_image_finder()
        raw_path = sub(step.get("image_path",""))
        if not os.path.isabs(raw_path): raw_path = os.path.join(_DIR, raw_path)
        conf,timeout = float(step.get("confidence",0.80)),float(step.get("timeout",10))
        if dry: self.log(f"{ind}    [dry] wait_image_vanish: {os.path.basename(raw_path)!r}"); return
        self.log(f"{ind}    \\U0001f6ab Waiting for image to vanish\\u2026")
        gone = finder.wait_for_image_to_vanish(raw_path,confidence=conf,timeout=timeout,stop_event=self._stop_event)
        if not gone: raise RuntimeError(f"Image did not vanish: {raw_path!r}")
        self.log(f"{ind}    \\u2714 Image vanished")

    def _do_ocr_condition(self, step, sub, dry, ind):
        from .ocr_engine import get_screen_reader
        x,y,w,h = int(step.get("x",0)),int(step.get("y",0)),int(step.get("w",300)),int(step.get("h",60))
        pat,cs,action = sub(step.get("pattern","")),bool(step.get("case_sensitive",False)),step.get("action","skip")
        if dry: self.log(f"{ind}    [dry] ocr_condition: {pat!r} in ({x},{y},{w},{h})"); return
        result = get_screen_reader().read_region(x,y,w,h)
        self.log(f"{ind}    \\U0001f524 OCR: {result.text[:40]!r}")
        if not result.contains(pat, cs):
            self.log(f"{ind}    \\u26a0 Pattern {pat!r} not found \\u2192 {action}")
            if action=="stop": raise RuntimeError(f"ocr_condition stop: {pat!r} not in screen text")
            elif action=="skip": raise _SkipName()

    def _do_ocr_extract(self, step, sub, dry, ind, vmap, name):
        from .ocr_engine import get_screen_reader
        x,y,w,h = int(step.get("x",0)),int(step.get("y",0)),int(step.get("w",300)),int(step.get("h",60))
        var_key = step.get("variable","ocr_result")
        if dry: self.log(f"{ind}    [dry] ocr_extract \\u2192 {{{var_key}}}"); return
        result = get_screen_reader().read_region(x,y,w,h)
        self.variables[var_key] = result.text; vmap[var_key] = result.text
        self.log(f"{ind}    \\U0001f4d6 Extracted {result.text[:40]!r} \\u2192 {{{var_key}}}")

    @staticmethod
    def _fmt(step, vmap):
        from .helpers import step_summary, apply_variables
        try: return apply_variables(step_summary(step), vmap)
        except Exception: return ""

    def _screenshot(self, folder, label="ss"):
        try:
            os.makedirs(folder, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe = "".join(c for c in label if c.isalnum() or c in "._- ").strip() or "ss"
            pyautogui.screenshot(os.path.join(folder, f"{safe}_{ts}.png"))
            self.log(f"  \\U0001f4f8 Saved \\u2192 {folder}")
        except Exception as e:
            self.log(f"  \\U0001f4f8 Screenshot failed: {e}")

    def _wait_if_paused(self):
        while self._pause_event.is_set() and not self._stop_event.is_set():
            time.sleep(0.15)

    def _interruptible_sleep(self, secs):
        end = time.time() + secs
        while time.time() < end:
            if self._stop_event.is_set(): return
            time.sleep(min(0.1, end - time.time()))

    def _start_hotkeys(self):
        if not _PYNPUT_OK: return
        sc        = _prefs.get("shortcuts", {})
        stop_key  = sc.get("emergency_stop","F10").upper()
        pause_key = sc.get("pause_resume","F11").upper()
        def _on_press(key):
            try:
                name = getattr(key,"name","").upper()
                if not name:
                    name = getattr(getattr(key,"char",None) or "","upper",lambda: "")()
                if name == stop_key:
                    self.stop(); self.log(f"\\u26d4 {stop_key} \\u2014 stopped!")
                elif name == pause_key:
                    if self._pause: self.resume(); self.log(f"\\u25b6 {pause_key} \\u2014 resumed")
                    else: self.pause(); self.log(f"\\u23f8 {pause_key} \\u2014 paused")
            except Exception: pass
        self._kb_lst = _kb.Listener(on_press=_on_press)
        self._kb_lst.daemon = True; self._kb_lst.start()

    def _stop_hotkeys(self):
        if self._kb_lst:
            try: self._kb_lst.stop()
            except Exception: pass
            self._kb_lst = None
'''

with open("/home/claude/core/executor.py", "w", encoding="utf-8") as f:
    f.write(executor_src)
print("executor.py written:", len(executor_src), "chars")