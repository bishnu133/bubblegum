"""
bubblegum/core/mobile/system_actions.py
=======================================
Parse mobile system / hardware verbs from natural language (M2).

These are device-level actions with no UI element to ground — Android back,
rotate, hide keyboard, deep link, background app, biometric, notification
shade. ``parse_system_action`` recognizes them (anchored at the start of the
instruction so a real button named "Back" is not hijacked) and returns a
``SystemAction`` describing the kind + any argument. Execution lives in
``AppiumAdapter.execute_system_action``; ``sdk.act`` routes mobile system verbs
there before grounding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

I = re.IGNORECASE


@dataclass
class SystemAction:
    """A parsed mobile system verb.

    kind: press_back | rotate | hide_keyboard | deep_link | background_app |
          accept_biometric | open_notification
    arg:  kind-specific payload (orientation / url / seconds / text).
    """

    kind: str
    arg: dict[str, Any] = field(default_factory=dict)


# Each entry: (kind, compiled pattern, group→arg builder). Patterns are
# anchored and ordered most-specific-first.
_BACK_RE = re.compile(r"^(?:press|tap|hit|click)\s+(?:the\s+)?back(?:\s+button)?$", I)
_GO_BACK_RE = re.compile(r"^(?:go|navigate)\s+back$", I)
_ROTATE_RE = re.compile(
    r"^(?:rotate|turn)\s+(?:the\s+)?(?:screen\s+|device\s+|to\s+)*(landscape|portrait)\b", I
)
_ORIENT_RE = re.compile(r"^(?:set\s+orientation\s+to|orient(?:ation)?\s+to)\s+(landscape|portrait)\b", I)
_HIDE_KB_RE = re.compile(r"^(?:hide|dismiss|close)\s+(?:the\s+)?keyboard$", I)
_DEEP_LINK_RE = re.compile(
    r"^(?:open\s+(?:the\s+)?deep\s*link|deep\s*link|open\s+(?:the\s+)?url)\s+(.+)$", I
)
_BACKGROUND_RE = re.compile(
    r"^(?:background\s+(?:the\s+)?app"
    r"|send\s+(?:the\s+)?app\s+to\s+(?:the\s+)?background"
    r"|put\s+(?:the\s+)?app\s+in\s+(?:the\s+)?background)"
    r"(?:\s+for\s+(\d+)\s*(?:seconds?|secs?|s)?)?$", I
)
_BIOMETRIC_RE = re.compile(
    r"^(?:accept|approve|authorize|pass|authenticate(?:\s+with)?)\s+(?:the\s+)?"
    r"(?:biometric|fingerprint|touch\s*id|face\s*id)(?:\s+(?:prompt|auth(?:entication)?))?$", I
)
_NOTIFICATION_RE = re.compile(
    r"^open\s+(?:the\s+)?notifications?(?:\s+(?:shade|panel|drawer))?"
    r"(?:\s+(?:for\s+|named\s+|titled\s+|called\s+)?(.+))?$", I
)


def parse_system_action(instruction: str) -> SystemAction | None:
    """Return the SystemAction for a mobile system verb, or None.

    Detection is conservative and start-anchored; anything that is not clearly
    a system verb returns None so normal grounding handles it.
    """
    text = (instruction or "").strip()
    if not text:
        return None

    if _BACK_RE.match(text) or _GO_BACK_RE.match(text):
        return SystemAction("press_back")

    m = _ROTATE_RE.match(text) or _ORIENT_RE.match(text)
    if m:
        return SystemAction("rotate", {"orientation": m.group(1).lower()})

    if _HIDE_KB_RE.match(text):
        return SystemAction("hide_keyboard")

    m = _DEEP_LINK_RE.match(text)
    if m:
        return SystemAction("deep_link", {"url": m.group(1).strip()})

    m = _BACKGROUND_RE.match(text)
    if m:
        arg: dict[str, Any] = {}
        if m.group(1):
            arg["seconds"] = int(m.group(1))
        return SystemAction("background_app", arg)

    if _BIOMETRIC_RE.match(text):
        return SystemAction("accept_biometric")

    m = _NOTIFICATION_RE.match(text)
    if m:
        arg = {}
        text_arg = (m.group(1) or "").strip()
        if text_arg:
            arg["text"] = text_arg
        return SystemAction("open_notification", arg)

    return None
