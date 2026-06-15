"""
bubblegum/core/recorder/models.py
==================================
Data models for the recorder (A1).

``RecordedAction`` is the normalized form of one captured user interaction —
distilled from a raw browser event into the few signals the NL-label
derivation needs (action kind, ARIA role, accessible name, typed/selected
value, and a best-effort fallback ref).

``RecordedStep`` is the emitted result for one action: an NL instruction such
as ``Click Login`` plus the resolved selector kept as a fallback comment. A
step may instead be *skipped* (instruction is None) when an action carries no
accessible name to phrase it from — emission renders those as comments so the
author can see what was dropped.
"""

from __future__ import annotations

from dataclasses import dataclass

# Action kinds the recorder understands. Each maps to a Bubblegum NL verb in
# codegen.py. Kept deliberately small for the MVP recorder.
RecordedActionKind = str  # "click" | "type" | "select" | "check" | "uncheck"


@dataclass
class RecordedAction:
    """A single normalized user interaction captured during recording.

    Attributes:
        action:       click | type | select | check | uncheck
        role:         best-effort ARIA role of the target element
        name:         accessible name (label/aria-label/placeholder/text), or ""
        value:        typed text (type) or chosen option label (select), else None
        tag:          lowercased HTML tag name (informational)
        fallback_ref: a Bubblegum-style locator ref (role=…[name="…"] / #id / [name=…])
                      kept as a comment beside the emitted NL step
    """

    action: RecordedActionKind
    role: str = ""
    name: str = ""
    value: str | None = None
    tag: str = ""
    fallback_ref: str | None = None


@dataclass
class RecordedStep:
    """One emitted line of a recorded flow.

    ``instruction`` is the NL step (e.g. ``Enter "tom" into Username``) or None
    when the action could not be phrased (no accessible name); in that case
    ``skipped_reason`` explains why and the line is emitted as a comment.
    """

    instruction: str | None
    fallback_ref: str | None = None
    skipped_reason: str | None = None
