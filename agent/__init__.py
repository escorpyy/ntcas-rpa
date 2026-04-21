"""
agent/__init__.py
=================
Agent package — exposes the two agent tools.

  MacroRecorderPro      – Records mouse/keyboard → imports as RPA steps.
                          Drop-in replacement for the original MacroRecorder.
                          Pro features: Pause state, global shortcuts, Auto-Wait.

  AutonomousVisionAgent – LLM (llava) sees the screen and acts autonomously
                          for each name in the name list.
"""

from .macro_recorder import MacroRecorderPro
from .vision_agent   import AutonomousVisionAgent

__all__ = ["MacroRecorderPro", "AutonomousVisionAgent"]
