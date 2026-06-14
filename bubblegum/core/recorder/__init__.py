"""Recorder / codegen (A1) — capture a manual click-through and emit
Bubblegum natural-language steps.

Pieces:
  - ``RECORDER_JS``           in-page capture script (injected via add_init_script)
  - ``ActionRecorder``        Python side of the capture binding; produces steps
  - ``RecordedAction`` / ``RecordedStep``  normalized capture + emitted step models
  - ``derive_steps``          element/action → NL instruction (parser-compatible)
  - ``emit_script``           runnable ``*_recorded.py`` source from steps
"""

from bubblegum.core.recorder.capture import (
    ActionRecorder,
    coalesce_actions,
    normalize_event,
)
from bubblegum.core.recorder.codegen import action_to_step, derive_steps
from bubblegum.core.recorder.emit import emit_script
from bubblegum.core.recorder.js import RECORDER_JS
from bubblegum.core.recorder.models import RecordedAction, RecordedStep

__all__ = [
    "RECORDER_JS",
    "ActionRecorder",
    "RecordedAction",
    "RecordedStep",
    "normalize_event",
    "coalesce_actions",
    "action_to_step",
    "derive_steps",
    "emit_script",
]
