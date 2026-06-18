"""DOM select-trigger fallback for dropdown/select intents.

When a custom combobox can't be ground from the a11y snapshot (nameless, or
several nameless comboboxes), the SDK falls back to the adapter's DOM-based
``find_select_trigger``. These tests cover the routing helper in isolation.
"""

from __future__ import annotations

import asyncio

import bubblegum.core.sdk as sdk
from bubblegum.core.schemas import StepIntent


def _run(coro):
    return asyncio.run(coro)


class _Adapter:
    def __init__(self, ref):
        self._ref = ref
        self.calls = []

    async def find_select_trigger(self, phrase, value):
        self.calls.append((phrase, value))
        return self._ref


def _intent(instruction, action_type, target_phrase=None, value=None):
    return StepIntent(instruction=instruction, channel="web", action_type=action_type,
                      target_phrase=target_phrase, input_value=value, context={})


def test_fallback_resolves_select_intent():
    adapter = _Adapter('[data-bg-select="1"]')
    intent = _intent("Select Participant from the search type dropdown", "select",
                     "search type", "Participant")
    target = _run(sdk._maybe_resolve_select_trigger(adapter, "web", intent))
    assert target is not None
    assert target.ref == '[data-bg-select="1"]'
    assert target.metadata.get("role") == "combobox"
    assert adapter.calls == [("search type", "Participant")]


def test_fallback_skips_non_dropdown_intent():
    adapter = _Adapter('[data-bg-select="1"]')
    intent = _intent("Click the Save button", "click", "Save")
    assert _run(sdk._maybe_resolve_select_trigger(adapter, "web", intent)) is None
    assert adapter.calls == []


def test_fallback_skips_mobile():
    adapter = _Adapter('[data-bg-select="1"]')
    intent = _intent("Select X from the Y dropdown", "select", "Y", "X")
    assert _run(sdk._maybe_resolve_select_trigger(adapter, "mobile", intent)) is None


def test_fallback_none_when_no_trigger_found():
    adapter = _Adapter(None)
    intent = _intent("Select X from the Y dropdown", "select", "Y", "X")
    assert _run(sdk._maybe_resolve_select_trigger(adapter, "web", intent)) is None


def test_fallback_handles_adapter_without_finder():
    class _Bare:
        pass
    intent = _intent("Select X from the Y dropdown", "select", "Y", "X")
    assert _run(sdk._maybe_resolve_select_trigger(_Bare(), "web", intent)) is None
