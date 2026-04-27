"""
core/ocr_engine.py
==================
OCR engine using pytesseract + OpenCV preprocessing.

Provides:
  - ScreenReader — read text from any screen region
  - Pre-processing pipeline (threshold, denoise, scale-up for accuracy)
  - Condition steps that branch on screen text
  - Extract specific patterns (numbers, dates, amounts)

New step types:
  ocr_condition  — if screen text matches pattern → skip / stop / continue
  ocr_extract    — read text from region → store in variable

Dependencies:
  pip install pytesseract Pillow opencv-python-headless
  Windows: install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki
           default path: C:\\Program Files\\Tesseract-OCR\\tesseract.exe
"""

from __future__ import annotations

import os
import re
import time
import threading
from typing import Optional

import cv2
import numpy as np

try:
    import pytesseract
    _TESS_OK = True
    # Auto-detect Tesseract on Windows
    _WIN_TESS_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.name == "nt" and os.path.isfile(_WIN_TESS_PATH):
        pytesseract.pytesseract.tesseract_cmd = _WIN_TESS_PATH
except ImportError:
    _TESS_OK = False

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


# ── OCR config presets ────────────────────────────────────────────────────────

# Tesseract PSM modes
PSM_SINGLE_LINE  = "--psm 7"
PSM_SINGLE_WORD  = "--psm 8"
PSM_BLOCK        = "--psm 6"   # default — assume uniform block of text
PSM_SPARSE       = "--psm 11"  # sparse text, find as much as possible
PSM_AUTO         = "--psm 3"

# OEM modes
OEM_LSTM         = "--oem 1"   # LSTM neural net (best accuracy)
OEM_LEGACY       = "--oem 0"

DEFAULT_CONFIG   = f"{PSM_BLOCK} {OEM_LSTM}"
FAST_CONFIG      = f"{PSM_SINGLE_LINE} {OEM_LSTM}"


# ─────────────────────────────────────────────────────────────────────────────
#  OCRResult
# ─────────────────────────────────────────────────────────────────────────────

class OCRResult:
    def __init__(self, text: str = "", confidence: float = 0.0,
                 raw: str = "", ok: bool = False):
        self.text       = text.strip()
        self.confidence = confidence
        self.raw        = raw
        self.ok         = ok

    def contains(self, pattern: str, case_sensitive: bool = False) -> bool:
        """Check if extracted text contains a substring or regex pattern."""
        haystack = self.text if case_sensitive else self.text.lower()
        needle   = pattern  if case_sensitive else pattern.lower()
        try:
            return bool(re.search(needle, haystack))
        except re.error:
            return needle in haystack

    def extract_numbers(self) -> list[str]:
        """Extract all number sequences from the OCR text."""
        return re.findall(r"\d[\d,._]*", self.text)

    def extract_amounts(self) -> list[float]:
        """Extract monetary amounts (handles comma separators)."""
        raw_nums = re.findall(r"\d[\d,]*\.?\d*", self.text)
        results  = []
        for n in raw_nums:
            try:
                results.append(float(n.replace(",", "")))
            except ValueError:
                pass
        return results

    def __repr__(self):
        return f"OCRResult(ok={self.ok}, text='{self.text[:40]}', conf={self.confidence:.1f})"

    def __bool__(self):
        return self.ok and bool(self.text)


# ─────────────────────────────────────────────────────────────────────────────
#  ScreenReader
# ─────────────────────────────────────────────────────────────────────────────

class ScreenReader:
    """
    Read text from any screen region using Tesseract OCR.

    Usage:
        reader = ScreenReader()
        result = reader.read_region(x=100, y=200, w=300, h=50)
        if result.contains("Invoice"):
            ...
    """

    def __init__(self, scale_factor: float = 2.0, lang: str = "eng"):
        """
        Args:
            scale_factor:  upscale image before OCR (improves accuracy for small text)
            lang:          Tesseract language code ('eng', 'nep', 'eng+nep')
        """
        self.scale_factor = scale_factor
        self.lang         = lang
        self._lock        = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def read_region(self, x: int, y: int, w: int, h: int,
                    config: str = DEFAULT_CONFIG,
                    preprocess: str = "auto") -> OCRResult:
        """
        Read text from a screen rectangle.

        Args:
            x, y, w, h:  screen coordinates and size
            config:      Tesseract config string
            preprocess:  'auto' | 'threshold' | 'none'

        Returns:
            OCRResult
        """
        if not _TESS_OK:
            return OCRResult(ok=False, raw="pytesseract not installed")

        try:
            img = self._capture_region(x, y, w, h)
            return self._ocr(img, config, preprocess)
        except Exception as e:
            return OCRResult(ok=False, raw=str(e))

    def read_fullscreen(self, config: str = DEFAULT_CONFIG,
                         preprocess: str = "auto") -> OCRResult:
        """Read text from the entire screen."""
        if not _PAG_OK:
            return OCRResult(ok=False, raw="pyautogui not available")
        try:
            screenshot = _pag.screenshot()
            img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            return self._ocr(img, config, preprocess)
        except Exception as e:
            return OCRResult(ok=False, raw=str(e))

    def find_text_location(self, text: str,
                            confidence: float = 60.0,
                            case_sensitive: bool = False) -> Optional[tuple[int, int]]:
        """
        Find where a specific text appears on screen.
        Returns (center_x, center_y) or None.
        """
        if not _TESS_OK or not _PAG_OK:
            return None
        try:
            screenshot = _pag.screenshot()
            img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            data = pytesseract.image_to_data(
                self._preprocess_auto(img),
                output_type=pytesseract.Output.DICT,
                lang=self.lang)

            needle = text if case_sensitive else text.lower()

            for i, word in enumerate(data["text"]):
                w = word if case_sensitive else word.lower()
                if needle in w and int(data["conf"][i]) >= confidence:
                    x = data["left"][i] + data["width"][i]  // 2
                    y = data["top"][i]  + data["height"][i] // 2
                    return (x, y)
        except Exception:
            pass
        return None

    def wait_for_text(self, text: str,
                       region: Optional[tuple] = None,
                       timeout: float = 10.0,
                       poll_interval: float = 0.5,
                       case_sensitive: bool = False,
                       stop_event=None) -> OCRResult:
        """
        Keep reading until the text appears (or timeout).
        Returns the OCRResult when found.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if stop_event and stop_event.is_set():
                return OCRResult(ok=False, raw="stopped")

            if region:
                result = self.read_region(*region)
            else:
                result = self.read_fullscreen()

            if result.contains(text, case_sensitive):
                return result

            time.sleep(poll_interval)

        return OCRResult(ok=False, raw=f"Timeout: '{text}' not found in {timeout}s")

    def wait_for_text_to_vanish(self, text: str,
                                  region: Optional[tuple] = None,
                                  timeout: float = 10.0,
                                  poll_interval: float = 0.5,
                                  stop_event=None) -> bool:
        """Wait until text disappears. Returns True when gone, False on timeout."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if stop_event and stop_event.is_set():
                return False

            if region:
                result = self.read_region(*region)
            else:
                result = self.read_fullscreen()

            if not result.contains(text):
                return True

            time.sleep(poll_interval)
        return False

    def is_tesseract_available(self) -> tuple[bool, str]:
        """Check if Tesseract is properly installed."""
        if not _TESS_OK:
            return False, "pytesseract not installed: pip install pytesseract"
        try:
            ver = pytesseract.get_tesseract_version()
            return True, f"Tesseract {ver}"
        except Exception as e:
            return False, (f"Tesseract binary not found: {e}\n"
                           f"Install from: https://github.com/UB-Mannheim/tesseract/wiki\n"
                           f"Expected path: {_WIN_TESS_PATH}")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _capture_region(self, x: int, y: int, w: int, h: int) -> np.ndarray:
        if not _PAG_OK:
            raise RuntimeError("pyautogui required")
        pil_img = _pag.screenshot(region=(x, y, w, h))
        return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    def _ocr(self, img: np.ndarray,
             config: str,
             preprocess: str) -> OCRResult:
        """Run OCR on a BGR numpy image."""

        # Scale up for better accuracy on small text
        if self.scale_factor != 1.0:
            h, w = img.shape[:2]
            img  = cv2.resize(img, (int(w * self.scale_factor),
                                     int(h * self.scale_factor)),
                              interpolation=cv2.INTER_CUBIC)

        # Preprocess
        if preprocess == "auto":
            proc = self._preprocess_auto(img)
        elif preprocess == "threshold":
            proc = self._preprocess_threshold(img)
        else:
            proc = img

        # Run OCR
        with self._lock:
            try:
                data = pytesseract.image_to_data(
                    proc, config=config, lang=self.lang,
                    output_type=pytesseract.Output.DICT)
            except Exception as e:
                return OCRResult(ok=False, raw=str(e))

        # Build text + avg confidence
        words   = []
        confs   = []
        for i, word in enumerate(data["text"]):
            c = int(data["conf"][i])
            if c > 0 and word.strip():
                words.append(word)
                confs.append(c)

        full_text = " ".join(words)
        avg_conf  = sum(confs) / len(confs) if confs else 0.0

        return OCRResult(
            text=full_text,
            confidence=avg_conf,
            raw=full_text,
            ok=bool(full_text))

    def _preprocess_auto(self, img: np.ndarray) -> np.ndarray:
        """Auto-detect best preprocessing based on image brightness."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mean = gray.mean()
        # Dark background → invert first
        if mean < 100:
            gray = cv2.bitwise_not(gray)
        # Light, clean background
        if mean > 180:
            return self._preprocess_threshold(img)
        return self._preprocess_denoise(gray)

    def _preprocess_threshold(self, img: np.ndarray) -> np.ndarray:
        """Adaptive threshold — best for light backgrounds."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        return cv2.threshold(gray, 0, 255,
                             cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    def _preprocess_denoise(self, gray: np.ndarray) -> np.ndarray:
        """Denoise then threshold — best for noisy/gradient backgrounds."""
        denoised = cv2.fastNlMeansDenoising(gray, h=10)
        return cv2.threshold(denoised, 0, 255,
                             cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]


# ── Module-level singleton ────────────────────────────────────────────────────

_reader = ScreenReader()


def read_region(x: int, y: int, w: int, h: int, **kwargs) -> OCRResult:
    return _reader.read_region(x, y, w, h, **kwargs)


def wait_for_text(text: str, **kwargs) -> OCRResult:
    return _reader.wait_for_text(text, **kwargs)


def get_screen_reader() -> ScreenReader:
    return _reader
