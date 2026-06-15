"""
bubblegum/core/recorder/codegen.py
==================================
Element → natural-language step derivation (A1).

Maps a :class:`RecordedAction` onto a Bubblegum NL instruction using the same
verb vocabulary the parser understands, so every emitted line *round-trips*:
``decompose()`` parses the generated step back to the same action_type / target
/ value the recorder saw. The recorded selector travels alongside as
``fallback_ref`` for emission as a comment.

Verb mapping:
    click           → ``Click <name>``
    type            → ``Enter "<value>" into <name>``
    select          → ``Select "<value>" from <name>``
    check           → ``Check <name>``
    uncheck         → ``Uncheck <name>``

Actions with no accessible name cannot be phrased as NL, so they are returned
as *skipped* steps (instruction None) with a reason; emission renders them as
comments rather than dropping them silently.
"""

from __future__ import annotations

from bubblegum.core.recorder.models import RecordedAction, RecordedStep


def _skip(action: RecordedAction, reason: str) -> RecordedStep:
    return RecordedStep(instruction=None, fallback_ref=action.fallback_ref, skipped_reason=reason)


def action_to_step(action: RecordedAction) -> RecordedStep:
    """Derive one NL step from a recorded action.

    Returns a skipped step (instruction None) when the action lacks the
    accessible name or value needed to phrase a resolvable instruction.
    """
    name = action.name.strip()
    ref = action.fallback_ref

    if action.action == "type":
        if not name:
            return _skip(action, "type action with no field label")
        value = action.value or ""
        return RecordedStep(f'Enter "{value}" into {name}', ref)

    if action.action == "select":
        if not name:
            return _skip(action, "select action with no field label")
        value = action.value or ""
        return RecordedStep(f'Select "{value}" from {name}', ref)

    if action.action == "check":
        if not name:
            return _skip(action, "check action with no label")
        return RecordedStep(f"Check {name}", ref)

    if action.action == "uncheck":
        if not name:
            return _skip(action, "uncheck action with no label")
        return RecordedStep(f"Uncheck {name}", ref)

    if action.action == "click":
        if not name:
            return _skip(action, "click target with no accessible name")
        return RecordedStep(f"Click {name}", ref)

    return _skip(action, f"unsupported action {action.action!r}")


def derive_steps(actions: list[RecordedAction]) -> list[RecordedStep]:
    """Derive NL steps for a list of recorded actions (preserving order)."""
    return [action_to_step(a) for a in actions]
