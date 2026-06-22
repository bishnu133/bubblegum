"""DOM clickable fallback for an ambiguous/low-confidence click."""
from __future__ import annotations

import asyncio
import bubblegum.core.sdk as sdk
from bubblegum.core.schemas import StepIntent


def _run(c): return asyncio.run(c)


class _Adapter:
    def __init__(self, ref="[data-bg-click=\"1\"]"):
        self._ref = ref
        self.calls = []

    async def find_clickable(self, text, *, exact=False):
        self.calls.append((text, exact))
        return self._ref


def _intent(instruction, action="click", target_phrase=None):
    return StepIntent(instruction=instruction, channel="web", action_type=action,
                      target_phrase=target_phrase, context={})


def test_uses_quoted_text():
    a = _Adapter()
    t = _run(sdk._maybe_resolve_clickable(a, "web", 'Click the "Update account status" button', _intent('x')))
    assert t is not None and t.ref == '[data-bg-click="1"]'
    assert t.resolver_name == "clickable_dom"
    assert a.calls == [("Update account status", False)]


def test_falls_back_to_target_phrase():
    a = _Adapter()
    _run(sdk._maybe_resolve_clickable(a, "web", "Click Submit", _intent("Click Submit", target_phrase="Submit")))
    assert a.calls == [("Submit", False)]


def test_skips_non_click():
    a = _Adapter()
    assert _run(sdk._maybe_resolve_clickable(a, "web", 'type "x"', _intent('type "x"', action="type"))) is None
    assert a.calls == []


def test_skips_mobile():
    a = _Adapter()
    assert _run(sdk._maybe_resolve_clickable(a, "mobile", 'Click "X"', _intent('Click "X"'))) is None


def test_none_when_no_match():
    a = _Adapter(ref=None)
    assert _run(sdk._maybe_resolve_clickable(a, "web", 'Click "Nope"', _intent('Click "Nope"'))) is None
