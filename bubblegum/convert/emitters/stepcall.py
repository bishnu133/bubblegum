"""
bubblegum/convert/emitters/stepcall.py
======================================
Shared helper: map a CanonicalStep to the Bubblegum primitive call it should
become. Both the Python and TypeScript emitters use this so the two languages
stay in lockstep.

Design note: we pass the *cleaned natural-language step text* straight to
``act`` / ``verify`` / ``extract``. Bubblegum re-parses that text at runtime
with the very same grammar the converter used for classification — so there is
no brittle call reconstruction, and a step that runs in Python runs identically
in TypeScript.
"""

from __future__ import annotations

from bubblegum.convert.models import CanonicalStep


_ACTION_VERBS = {
    "click", "tap", "type", "select", "upload", "check", "uncheck",
    "set", "hover", "scroll", "long_press", "double_tap", "pinch", "zoom", "drag",
}


def primitive_for(step: CanonicalStep) -> str:
    """Return 'verify' | 'extract' | 'act' for a step.

    The parsed action type wins over Gherkin position: an action written under a
    ``Then`` (e.g. "And they click the Save button") still emits ``act``, not
    ``verify``. Section is only the tie-breaker when the action is unknown.
    """
    if step.action_type == "extract":
        return "extract"
    if step.action_type in _ACTION_VERBS:
        return "act"
    if step.action_type == "verify" or step.keyword == "then":
        return "verify"
    return "act"


def py_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def ts_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'")
