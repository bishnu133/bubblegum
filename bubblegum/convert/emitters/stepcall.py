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

import re

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


# Leading verbs to drop from a Then so the verify phrase is the bare
# expectation ("see the Discount applied message" -> "the Discount applied
# message"), matching how Bubblegum verify phrases read.
_VERIFY_LEAD_RE = re.compile(
    r"^(?:see|observe|verify|check|confirm|ensure|assert|should\s+see|"
    r"will\s+see|can\s+see)\s+",
    re.IGNORECASE,
)

# A step that causes navigation / a page transition — used to insert the
# team's wait pattern after it.
_NAV_PHRASE_RE = re.compile(
    r"\b(open|navigate|go\s+to|click\s+the\s+.+\s+(?:menu|tab|link)|"
    r"submit|sign\s+in|log\s+in|continue|next|save|create\b|configure\b)\b",
    re.IGNORECASE,
)


def _cap_first(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def act_phrase(step) -> str:
    """Natural-language phrase for a Bubblegum act(), capitalized like the SDK examples."""
    return _cap_first(step.instruction.strip())


def verify_phrase(step) -> str:
    """Expectation phrase for a Bubblegum verify(): drop leading see/verify verbs."""
    phrase = _VERIFY_LEAD_RE.sub("", step.instruction.strip()).strip()
    return _cap_first(phrase or step.instruction.strip())


def is_nav_step(step) -> bool:
    return bool(_NAV_PHRASE_RE.search(step.instruction))
