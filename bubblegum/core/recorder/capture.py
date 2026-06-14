"""
bubblegum/core/recorder/capture.py
==================================
Turn raw in-page events into normalized :class:`RecordedAction` objects (A1).

``normalize_event`` distils one JSON payload (as produced by ``RECORDER_JS``)
into a ``RecordedAction``, dropping anything without a usable action kind.
``coalesce_actions`` runs the whole stream through normalization and collapses
consecutive ``type`` events on the *same* field into a single action that keeps
the final value — so re-editing a field while recording yields one clean step.

``ActionRecorder`` holds the captured raw events (it is the Python side of the
``__bubblegum_record__`` binding) and exposes ``actions()`` / ``steps()``. Its
``attach`` wires the binding + init script onto a Playwright BrowserContext;
it is duck-typed (no Playwright import) so the core stays browser-free and
unit-testable.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from bubblegum.core.recorder.codegen import derive_steps
from bubblegum.core.recorder.js import RECORDER_JS
from bubblegum.core.recorder.models import RecordedAction, RecordedStep

logger = logging.getLogger(__name__)

_VALID_ACTIONS = {"click", "type", "select", "check", "uncheck"}
_MAX_NAME_LEN = 120


def _clean(value: Any) -> str:
    """Collapse whitespace and strip; return '' for non-strings/None."""
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()


def normalize_event(raw: dict[str, Any]) -> RecordedAction | None:
    """Normalize one raw recorder payload into a RecordedAction.

    Returns None when the payload has no recognized action kind. The accessible
    name is whitespace-collapsed and length-capped so a button wrapping an icon
    plus a long caption still yields a tractable NL label.
    """
    if not isinstance(raw, dict):
        return None
    action = _clean(raw.get("action")).lower()
    if action not in _VALID_ACTIONS:
        return None

    name = _clean(raw.get("name"))
    if len(name) > _MAX_NAME_LEN:
        name = name[:_MAX_NAME_LEN].rstrip()

    value = raw.get("value")
    value = value if isinstance(value, str) else (None if value is None else str(value))

    fallback = raw.get("fallback_ref")
    fallback = fallback if isinstance(fallback, str) and fallback.strip() else None

    return RecordedAction(
        action=action,
        role=_clean(raw.get("role")).lower(),
        name=name,
        value=value,
        tag=_clean(raw.get("tag")).lower(),
        fallback_ref=fallback,
    )


def coalesce_actions(raw_events: list[dict[str, Any]]) -> list[RecordedAction]:
    """Normalize a raw event stream and collapse redundant consecutive typing.

    Two consecutive ``type`` events targeting the same field (same fallback_ref,
    or same name when no ref) are merged into the later one — re-editing a field
    should produce a single ``Enter "<final value>" into <field>`` step.
    """
    actions: list[RecordedAction] = []
    for raw in raw_events:
        action = normalize_event(raw)
        if action is None:
            continue
        if action.action == "type" and actions:
            prev = actions[-1]
            same_field = prev.action == "type" and (
                (prev.fallback_ref and prev.fallback_ref == action.fallback_ref)
                or (not prev.fallback_ref and not action.fallback_ref and prev.name == action.name)
            )
            if same_field:
                actions[-1] = action
                continue
        actions.append(action)
    return actions


class ActionRecorder:
    """Collects recorded events from a page and turns them into NL steps.

    Lives on the Python side of the ``__bubblegum_record__`` binding. Usage:

        rec = ActionRecorder()
        await rec.attach(context)          # before opening pages
        page = await context.new_page()
        ...                                # user clicks/types
        steps = rec.steps()                # NL steps for emission
    """

    BINDING_NAME = "__bubblegum_record__"

    def __init__(self) -> None:
        self._raw: list[dict[str, Any]] = []

    # -- collection -----------------------------------------------------

    def record_raw(self, payload: Any) -> None:
        """Append one raw payload (called by the exposed browser binding)."""
        if isinstance(payload, dict):
            self._raw.append(payload)
        else:
            logger.debug("recorder: ignoring non-dict payload %r", payload)

    def _on_binding(self, source: Any, payload: Any = None) -> None:
        """expose_binding callback: ``(source, *args)`` — keep the payload."""
        self.record_raw(payload)

    @property
    def raw_events(self) -> list[dict[str, Any]]:
        """Raw payloads captured so far (copy)."""
        return list(self._raw)

    # -- derivation -----------------------------------------------------

    def actions(self) -> list[RecordedAction]:
        """Normalized + coalesced actions captured so far."""
        return coalesce_actions(self._raw)

    def steps(self) -> list[RecordedStep]:
        """NL steps derived from the captured actions (ready for emission)."""
        return derive_steps(self.actions())

    # -- browser wiring (duck-typed; no Playwright import) --------------

    async def attach(self, context: Any) -> None:
        """Install the binding + recorder init script on a BrowserContext.

        Must be called before pages navigate so the init script runs on the
        first document. ``context`` is anything exposing ``expose_binding`` and
        ``add_init_script`` (a Playwright BrowserContext in practice).
        """
        await context.expose_binding(self.BINDING_NAME, self._on_binding)
        await context.add_init_script(RECORDER_JS)
