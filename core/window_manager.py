"""
core/window_manager.py
======================
Window detection, matching, tracking, and validation engine.

Provides:
  - WindowInfo dataclass — captures full window identity
  - WindowManager — get/match/wait/focus windows
  - get_active_window() — quick helper
  - Multi-level matching: hwnd → process+class → title → fallback
  - Relative coordinate helpers
  - DPI-awareness (Windows only)

Supports Windows fully (win32), macOS / Linux partially (title only).
"""

from __future__ import annotations

import os
import sys
import time
import math
import hashlib
import threading
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable

# ── Optional win32 imports ────────────────────────────────────────────────────
_WIN32 = sys.platform == "win32"
_CTYPES_OK = False
_PSUTIL_OK = False

if _WIN32:
    try:
        import ctypes
        import ctypes.wintypes as _wt
        _CTYPES_OK = True
    except ImportError:
        pass
    try:
        import psutil
        _PSUTIL_OK = True
    except ImportError:
        pass

try:
    import pyautogui as _pag
    _PYAG_OK = True
except ImportError:
    _PYAG_OK = False


# ─────────────────────────────────────────────────────────────────────────────
#  WindowInfo
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WindowInfo:
    """Full identity snapshot of a window."""
    title:     str   = ""
    process:   str   = ""          # e.g. "chrome.exe"
    cls:       str   = ""          # window class name
    hwnd:      int   = 0           # OS handle (Windows only)
    x:         int   = 0
    y:         int   = 0
    width:     int   = 0
    height:    int   = 0
    monitor:   int   = 1
    dpi_scale: float = 1.0
    minimized: bool  = False
    visible:   bool  = True
    # computed
    snapshot_hash: str = ""        # hash of title+process for change detection

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "WindowInfo":
        valid = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**valid)

    @property
    def rect(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.width, "h": self.height}

    def abs_coords(self, rel_x: float, rel_y: float) -> tuple[int, int]:
        """Convert relative (0-1) coords to absolute screen coords."""
        ax = int(self.x + rel_x * self.width)
        ay = int(self.y + rel_y * self.height)
        return ax, ay

    def rel_coords(self, abs_x: int, abs_y: int) -> tuple[float, float]:
        """Convert absolute screen coords to relative (0-1) coords."""
        if self.width == 0 or self.height == 0:
            return 0.5, 0.5
        rx = (abs_x - self.x) / self.width
        ry = (abs_y - self.y) / self.height
        return round(rx, 4), round(ry, 4)

    def contains(self, abs_x: int, abs_y: int) -> bool:
        return (self.x <= abs_x <= self.x + self.width and
                self.y <= abs_y <= self.y + self.height)


# ─────────────────────────────────────────────────────────────────────────────
#  WindowManager
# ─────────────────────────────────────────────────────────────────────────────

class WindowManager:
    """
    Central window detection and matching engine.
    Thread-safe; maintains a change-detection loop when started.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._last_active: Optional[WindowInfo] = None
        self._change_callbacks: list[Callable[[WindowInfo, WindowInfo], None]] = []
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitoring = False
        self._poll_interval = 0.5   # seconds

    # ── Public API ────────────────────────────────────────────────────────────

    def get_active_window(self) -> Optional[WindowInfo]:
        """Return full WindowInfo for the currently focused window."""
        if _WIN32 and _CTYPES_OK:
            return self._get_active_win32()
        return self._get_active_fallback()

    def get_all_windows(self) -> list[WindowInfo]:
        """Return list of all visible top-level windows (Windows only)."""
        if _WIN32 and _CTYPES_OK:
            return self._enum_windows_win32()
        return []

    def match(self, expected: WindowInfo | dict, current: Optional[WindowInfo] = None,
              tolerance: str = "normal") -> bool:
        """
        Multi-level window matching.
        tolerance: "strict" | "normal" | "loose"
        Returns True if current matches expected.
        """
        if current is None:
            current = self.get_active_window()
        if current is None:
            return False

        if isinstance(expected, dict):
            expected = WindowInfo.from_dict(expected)

        # Level 1 — exact hwnd match (most reliable)
        if expected.hwnd and expected.hwnd == current.hwnd:
            return True

        # Level 2 — process + class
        if expected.process and expected.cls:
            if (expected.process.lower() == current.process.lower() and
                    expected.cls.lower() == current.cls.lower()):
                return True

        # Level 3 — process match
        if expected.process and current.process:
            if expected.process.lower() == current.process.lower():
                if tolerance in ("normal", "loose"):
                    return True

        # Level 4 — title contains (loose)
        if expected.title and current.title:
            if expected.title.lower() in current.title.lower():
                return True

        # Level 5 — any window (fallback)
        if tolerance == "loose" and not expected.hwnd and not expected.process:
            return True

        return False

    def wait_for_window(self, expected: WindowInfo | dict,
                        timeout: float = 10.0,
                        poll: float = 0.3,
                        tolerance: str = "normal",
                        stop_event: "threading.Event | None" = None) -> Optional[WindowInfo]:
        """
        Wait until a matching window becomes active.
        Returns the WindowInfo if found, None on timeout.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if stop_event and stop_event.is_set():
                return None
            current = self.get_active_window()
            if current and self.match(expected, current, tolerance):
                return current
            time.sleep(poll)
        return None

    def wait_for_window_close(self, expected: WindowInfo | dict,
                              timeout: float = 10.0,
                              poll: float = 0.3,
                              stop_event: "threading.Event | None" = None) -> bool:
        """
        Wait until the matching window is no longer active.
        Returns True when it closes, False on timeout.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if stop_event and stop_event.is_set():
                return False
            current = self.get_active_window()
            if current is None or not self.match(expected, current, "loose"):
                return True
            time.sleep(poll)
        return False

    def wait_for_window_change(self, current_ref: Optional[WindowInfo] = None,
                               timeout: float = 10.0,
                               poll: float = 0.3,
                               stop_event: "threading.Event | None" = None) -> Optional[WindowInfo]:
        """
        Wait until the active window changes from current_ref.
        Returns the new WindowInfo when detected.
        """
        if current_ref is None:
            current_ref = self.get_active_window()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if stop_event and stop_event.is_set():
                return None
            new = self.get_active_window()
            if new and (not current_ref or new.hwnd != current_ref.hwnd or
                        new.title != current_ref.title):
                return new
            time.sleep(poll)
        return None

    def focus_window(self, expected: WindowInfo | dict,
                     restore_minimized: bool = True) -> bool:
        """Bring a window to the foreground. Returns True if successful."""
        if isinstance(expected, dict):
            expected = WindowInfo.from_dict(expected)

        if not _WIN32 or not _CTYPES_OK:
            return False

        hwnd = expected.hwnd
        if not hwnd:
            # Find by title or process
            matches = self._find_windows_by_criteria(expected)
            if matches:
                hwnd = matches[0].hwnd

        if not hwnd:
            return False

        try:
            user32 = ctypes.windll.user32
            # Restore if minimized
            if restore_minimized:
                placement = user32.IsIconic(hwnd)
                if placement:
                    import ctypes
                    SW_RESTORE = 9
                    user32.ShowWindow(hwnd, SW_RESTORE)
                    time.sleep(0.1)
            # Bring to front
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            time.sleep(0.1)
            return True
        except Exception:
            return False

    def assert_window(self, expected: WindowInfo | dict,
                      tolerance: str = "normal") -> tuple[bool, str]:
        """
        Assert the current window matches expected.
        Returns (ok, message).
        """
        current = self.get_active_window()
        if current is None:
            return False, "Could not detect active window"
        if self.match(expected, current, tolerance):
            return True, f"Window matched: '{current.title}'"
        if isinstance(expected, dict):
            exp_title = expected.get("title", "?")
        else:
            exp_title = expected.title
        return False, (f"Window mismatch: expected '{exp_title}', "
                       f"got '{current.title}' [{current.process}]")

    def validate_before_action(self, expected: WindowInfo | dict,
                               timeout: float = 5.0,
                               stop_event=None) -> tuple[bool, str]:
        """
        Called before every automated action.
        Tries to match, waits up to timeout, returns (ok, message).
        """
        if isinstance(expected, dict) and not any([
                expected.get("hwnd"), expected.get("process"),
                expected.get("title"), expected.get("cls")]):
            # No criteria set — skip validation
            return True, "No window constraint"

        current = self.get_active_window()
        if current and self.match(expected, current):
            return True, "OK"

        # Try to focus it
        self.focus_window(expected)
        time.sleep(0.2)

        # Wait for it
        found = self.wait_for_window(expected, timeout=timeout,
                                     stop_event=stop_event)
        if found:
            return True, f"Window acquired: '{found.title}'"
        return False, "Window not found within timeout"

    # ── Change monitoring ─────────────────────────────────────────────────────

    def start_monitoring(self, callback: Callable[[WindowInfo, WindowInfo], None] | None = None,
                         interval: float = 0.5):
        """Start background thread that fires callback on window changes."""
        if callback:
            self._change_callbacks.append(callback)
        self._poll_interval = interval
        self._monitoring = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop_monitoring(self):
        self._monitoring = False
        self._change_callbacks.clear()

    def _monitor_loop(self):
        prev = self.get_active_window()
        while self._monitoring:
            time.sleep(self._poll_interval)
            current = self.get_active_window()
            if current and prev:
                if (current.hwnd != prev.hwnd or current.title != prev.title):
                    for cb in list(self._change_callbacks):
                        try:
                            cb(prev, current)
                        except Exception:
                            pass
                    prev = current
            elif current:
                prev = current

    # ── Win32 implementation ──────────────────────────────────────────────────

    def _get_active_win32(self) -> Optional[WindowInfo]:
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None
            return self._hwnd_to_info(hwnd)
        except Exception:
            return self._get_active_fallback()

    def _hwnd_to_info(self, hwnd: int) -> Optional[WindowInfo]:
        try:
            user32 = ctypes.windll.user32

            # Title
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            title = buf.value or ""

            # Class name
            cbuf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, cbuf, 256)
            cls = cbuf.value or ""

            # Rect
            rect = _wt.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            x = rect.left
            y = rect.top
            w = rect.right - rect.left
            h = rect.bottom - rect.top

            # Minimized / visible
            minimized = bool(user32.IsIconic(hwnd))
            visible   = bool(user32.IsWindowVisible(hwnd))

            # Process
            pid = ctypes.c_ulong(0)
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            process = self._pid_to_name(pid.value)

            # DPI scale
            dpi_scale = self._get_dpi_scale(hwnd)

            # Monitor index
            monitor = self._get_monitor_index(hwnd)

            # Hash
            snap = hashlib.md5(f"{title}{process}{cls}".encode()).hexdigest()[:8]

            return WindowInfo(
                title=title, process=process, cls=cls, hwnd=hwnd,
                x=x, y=y, width=w, height=h,
                monitor=monitor, dpi_scale=dpi_scale,
                minimized=minimized, visible=visible,
                snapshot_hash=snap,
            )
        except Exception:
            return None

    def _enum_windows_win32(self) -> list[WindowInfo]:
        results = []
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)

        def callback(hwnd, lParam):
            user32 = ctypes.windll.user32
            if user32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(512)
                user32.GetWindowTextW(hwnd, buf, 512)
                if buf.value:
                    info = self._hwnd_to_info(hwnd)
                    if info:
                        results.append(info)
            return True

        try:
            ctypes.windll.user32.EnumWindows(WNDENUMPROC(callback), 0)
        except Exception:
            pass
        return results

    def _find_windows_by_criteria(self, expected: WindowInfo) -> list[WindowInfo]:
        all_wins = self.get_all_windows()
        matches = []
        for w in all_wins:
            if self.match(expected, w, "loose"):
                matches.append(w)
        return matches

    def _pid_to_name(self, pid: int) -> str:
        if _PSUTIL_OK:
            try:
                p = psutil.Process(pid)
                return p.name()
            except Exception:
                pass
        if _WIN32 and _CTYPES_OK:
            try:
                PROCESS_QUERY_LIMITED = 0x1000
                handle = ctypes.windll.kernel32.OpenProcess(
                    PROCESS_QUERY_LIMITED, False, pid)
                if handle:
                    buf = ctypes.create_unicode_buffer(260)
                    ctypes.windll.psapi.GetModuleFileNameExW(
                        handle, None, buf, 260)
                    ctypes.windll.kernel32.CloseHandle(handle)
                    name = os.path.basename(buf.value)
                    return name
            except Exception:
                pass
        return ""

    def _get_dpi_scale(self, hwnd: int) -> float:
        try:
            dpi = ctypes.windll.user32.GetDpiForWindow(hwnd)
            return dpi / 96.0
        except Exception:
            return 1.0

    def _get_monitor_index(self, hwnd: int) -> int:
        try:
            MONITOR_DEFAULTTONEAREST = 2
            hmon = ctypes.windll.user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
            # Enumerate monitors to get index
            monitors = []
            MONITORENUMPROC = ctypes.WINFUNCTYPE(
                ctypes.c_bool, ctypes.c_ulong, ctypes.c_ulong,
                ctypes.POINTER(_wt.RECT), ctypes.c_double)

            def _cb(hm, hdc, rect, data):
                monitors.append(hm)
                return True

            ctypes.windll.user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(_cb), 0)
            if hmon in monitors:
                return monitors.index(hmon) + 1
        except Exception:
            pass
        return 1

    # ── Fallback (non-Windows) ────────────────────────────────────────────────

    def _get_active_fallback(self) -> Optional[WindowInfo]:
        title = ""
        try:
            fn = getattr(_pag if _PYAG_OK else None, "getActiveWindowTitle", None)
            if fn:
                title = fn() or ""
        except Exception:
            pass
        if not title:
            return None
        snap = hashlib.md5(title.encode()).hexdigest()[:8]
        return WindowInfo(title=title, snapshot_hash=snap)


# ── Module-level singleton + helpers ──────────────────────────────────────────

_manager = WindowManager()


def get_active_window() -> Optional[WindowInfo]:
    """Quick module-level helper."""
    return _manager.get_active_window()


def get_window_manager() -> WindowManager:
    return _manager
