"""
core/image_finder.py
====================
Image-based click engine using OpenCV template matching.

Provides:
  - ImageFinder  — find a template image on screen, return best match location
  - Multi-scale search (handles DPI differences + window resize)
  - Confidence threshold gate
  - Debug overlay (save annotated screenshot)
  - click_image step type support in executor

Step type: click_image
  {
    "type":       "click_image",
    "image_path": "targets/save_button.png",   # relative to _DIR or absolute
    "confidence": 0.80,                         # 0.0–1.0
    "timeout":    10,                           # seconds to keep retrying
    "offset_x":   0,                            # click offset from center
    "offset_y":   0,
    "action":     "click",                      # click | double_click | right_click | hover
    "grayscale":  true,                         # faster matching
    "note":       "",
    "enabled":    true
  }

Also provides:
  - ScreenReader.find_text(region)  — OCR wrapper (see ocr_engine.py)
  - capture_target(path)            — save a screen region as a new target image

Dependencies:
  pip install opencv-python-headless Pillow pyautogui
"""

from __future__ import annotations

import os
import time
import threading
from typing import Optional

import cv2
import numpy as np

try:
    import pyautogui as _pag
    _PAG_OK = True
except ImportError:
    _PAG_OK = False

try:
    from PIL import Image as _PILImage
    _PIL_OK = True
except ImportError:
    _PIL_OK = False


# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_CONFIDENCE  = 0.80
DEFAULT_TIMEOUT     = 10.0
SCALE_RANGE         = [1.0, 0.9, 0.85, 0.75, 1.1, 1.15, 1.25]  # search order
DEBUG_OUTPUT_FOLDER = os.path.join(os.path.expanduser("~"), ".swastik", "debug_images")


# ─────────────────────────────────────────────────────────────────────────────
#  MatchResult
# ─────────────────────────────────────────────────────────────────────────────

class MatchResult:
    """Result of a template match search."""
    def __init__(self, found: bool, x: int = 0, y: int = 0,
                 confidence: float = 0.0, scale: float = 1.0,
                 width: int = 0, height: int = 0):
        self.found      = found
        self.x          = x          # center x on screen
        self.y          = y          # center y on screen
        self.confidence = confidence
        self.scale      = scale
        self.width      = width
        self.height     = height

    def __repr__(self):
        if self.found:
            return (f"MatchResult(found=True, x={self.x}, y={self.y}, "
                    f"conf={self.confidence:.3f}, scale={self.scale:.2f})")
        return "MatchResult(found=False)"


# ─────────────────────────────────────────────────────────────────────────────
#  ImageFinder
# ─────────────────────────────────────────────────────────────────────────────

class ImageFinder:
    """
    Finds a template image on the current screen using OpenCV.
    Thread-safe; uses its own screenshot per call.
    """

    def __init__(self):
        self._lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def find(self, template_path: str,
             confidence: float = DEFAULT_CONFIDENCE,
             grayscale: bool = True,
             region: Optional[tuple] = None,
             scales: Optional[list] = None,
             timeout: float = 0.0,
             poll_interval: float = 0.5,
             stop_event=None) -> MatchResult:
        """
        Find template_path on screen.

        Args:
            template_path:  path to the target image (.png/.jpg)
            confidence:     minimum match confidence 0.0–1.0
            grayscale:      convert both images to gray (faster, usually fine)
            region:         (x, y, w, h) to limit search area; None = full screen
            scales:         list of scale factors to try; None = SCALE_RANGE
            timeout:        if > 0, keep retrying for this many seconds
            poll_interval:  seconds between retries
            stop_event:     threading.Event to abort waiting

        Returns:
            MatchResult
        """
        if not os.path.isfile(template_path):
            return MatchResult(False)

        template_bgr = cv2.imread(template_path, cv2.IMREAD_COLOR)
        if template_bgr is None:
            return MatchResult(False)

        _scales = scales or SCALE_RANGE
        deadline = time.time() + timeout if timeout > 0 else 0

        while True:
            result = self._search_once(template_bgr, confidence, grayscale,
                                       region, _scales)
            if result.found:
                return result

            if timeout > 0 and time.time() < deadline:
                if stop_event and stop_event.is_set():
                    return MatchResult(False)
                time.sleep(poll_interval)
                continue

            return result

    def find_all(self, template_path: str,
                 confidence: float = DEFAULT_CONFIDENCE,
                 grayscale: bool = True,
                 region: Optional[tuple] = None) -> list[MatchResult]:
        """Find all non-overlapping occurrences of template on screen."""
        if not os.path.isfile(template_path):
            return []

        template_bgr = cv2.imread(template_path, cv2.IMREAD_COLOR)
        if template_bgr is None:
            return []

        screen_bgr = self._screenshot_np(region)
        results    = []

        if grayscale:
            screen   = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
            template = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)
        else:
            screen   = screen_bgr
            template = template_bgr

        th, tw = template.shape[:2]
        res = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        loc = np.where(res >= confidence)

        used = set()
        ox, oy = (region[0], region[1]) if region else (0, 0)

        for pt in zip(*loc[::-1]):
            # Deduplicate overlapping matches
            key = (pt[0] // tw, pt[1] // th)
            if key in used:
                continue
            used.add(key)
            cx = ox + pt[0] + tw // 2
            cy = oy + pt[1] + th // 2
            results.append(MatchResult(
                found=True, x=cx, y=cy,
                confidence=float(res[pt[1], pt[0]]),
                scale=1.0, width=tw, height=th))

        return results

    def wait_for_image(self, template_path: str,
                       confidence: float = DEFAULT_CONFIDENCE,
                       timeout: float = DEFAULT_TIMEOUT,
                       poll_interval: float = 0.5,
                       stop_event=None) -> MatchResult:
        """Convenience: find with timeout."""
        return self.find(template_path, confidence=confidence,
                         timeout=timeout, poll_interval=poll_interval,
                         stop_event=stop_event)

    def wait_for_image_to_vanish(self, template_path: str,
                                  confidence: float = DEFAULT_CONFIDENCE,
                                  timeout: float = DEFAULT_TIMEOUT,
                                  poll_interval: float = 0.5,
                                  stop_event=None) -> bool:
        """
        Wait until the template is NO LONGER visible on screen.
        Returns True when it vanishes, False on timeout.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if stop_event and stop_event.is_set():
                return False
            result = self.find(template_path, confidence=confidence)
            if not result.found:
                return True
            time.sleep(poll_interval)
        return False

    def capture_target(self, save_path: str,
                       region: Optional[tuple] = None,
                       delay: float = 0.0) -> str:
        """
        Capture current screen (or region) and save as a target image.

        Args:
            save_path:  where to save (e.g. "targets/save_btn.png")
            region:     (x, y, w, h) to crop; None = full screen
            delay:      seconds to wait before capturing

        Returns:
            absolute path to saved image
        """
        if delay > 0:
            time.sleep(delay)

        if not os.path.isabs(save_path):
            from core.constants import _DIR
            save_path = os.path.join(_DIR, save_path)

        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)

        if _PAG_OK:
            screenshot = _pag.screenshot()
            if region:
                x, y, w, h = region
                screenshot = screenshot.crop((x, y, x + w, y + h))
            screenshot.save(save_path)
        else:
            raise RuntimeError("pyautogui required for capture_target")

        return save_path

    def save_debug_image(self, template_path: str,
                         result: MatchResult,
                         label: str = "") -> Optional[str]:
        """Save annotated screenshot showing match location (for debugging)."""
        try:
            os.makedirs(DEBUG_OUTPUT_FOLDER, exist_ok=True)
            screen_bgr = self._screenshot_np()
            if result.found:
                # Draw green rectangle around match
                x1 = result.x - result.width  // 2
                y1 = result.y - result.height // 2
                x2 = result.x + result.width  // 2
                y2 = result.y + result.height // 2
                cv2.rectangle(screen_bgr, (x1, y1), (x2, y2), (0, 255, 0), 3)
                cv2.circle(screen_bgr, (result.x, result.y), 8, (0, 0, 255), -1)
                text = f"{label or 'match'} {result.confidence:.2f}"
                cv2.putText(screen_bgr, text, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

            import datetime
            ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            name = os.path.splitext(os.path.basename(template_path))[0]
            out  = os.path.join(DEBUG_OUTPUT_FOLDER, f"{name}_{ts}.png")
            cv2.imwrite(out, screen_bgr)
            return out
        except Exception:
            return None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _search_once(self, template_bgr: np.ndarray,
                     confidence: float,
                     grayscale: bool,
                     region: Optional[tuple],
                     scales: list) -> MatchResult:
        """One screenshot + multi-scale search."""
        screen_bgr = self._screenshot_np(region)
        ox, oy     = (region[0], region[1]) if region else (0, 0)

        best = MatchResult(False)

        for scale in scales:
            template = template_bgr.copy()

            if scale != 1.0:
                th, tw = template.shape[:2]
                nw = max(1, int(tw * scale))
                nh = max(1, int(th * scale))
                template = cv2.resize(template, (nw, nh),
                                      interpolation=cv2.INTER_AREA
                                      if scale < 1.0 else cv2.INTER_CUBIC)

            th, tw = template.shape[:2]
            sh, sw = screen_bgr.shape[:2]

            # Template must fit in screen
            if th > sh or tw > sw:
                continue

            if grayscale:
                screen_gray   = cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2GRAY)
                template_gray = cv2.cvtColor(template,   cv2.COLOR_BGR2GRAY)
                res = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
            else:
                res = cv2.matchTemplate(screen_bgr, template, cv2.TM_CCOEFF_NORMED)

            _, max_val, _, max_loc = cv2.minMaxLoc(res)

            if max_val >= confidence and max_val > best.confidence:
                cx = ox + max_loc[0] + tw // 2
                cy = oy + max_loc[1] + th // 2
                best = MatchResult(
                    found=True, x=cx, y=cy,
                    confidence=float(max_val),
                    scale=scale, width=tw, height=th)

        return best

    def _screenshot_np(self, region: Optional[tuple] = None) -> np.ndarray:
        """Take a screenshot and return as BGR numpy array."""
        if _PAG_OK and _PIL_OK:
            if region:
                x, y, w, h = region
                pil_img = _pag.screenshot(region=(x, y, w, h))
            else:
                pil_img = _pag.screenshot()
            return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        raise RuntimeError("pyautogui + Pillow required for screen capture")


# ── Module-level singleton ────────────────────────────────────────────────────

_finder = ImageFinder()


def find_image(template_path: str, **kwargs) -> MatchResult:
    return _finder.find(template_path, **kwargs)


def wait_for_image(template_path: str, **kwargs) -> MatchResult:
    return _finder.wait_for_image(template_path, **kwargs)


def get_image_finder() -> ImageFinder:
    return _finder
