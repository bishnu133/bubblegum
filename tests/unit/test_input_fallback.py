"""DOM input fallback for `type` steps whose field has no accessible name."""
from __future__ import annotations

import asyncio
import bubblegum.core.sdk as sdk
from bubblegum.core.schemas import StepIntent


def _run(c): return asyncio.run(c)


class _Adapter:
    def __init__(self, ref='[data-bg-input="1"]'):
        self._ref = ref
        self.calls = []

    async def find_input(self, target_phrase):
        self.calls.append(target_phrase)
        return self._ref


def _intent(action="type", target_phrase="Remarks"):
    return StepIntent(instruction="x", channel="web", action_type=action,
                      target_phrase=target_phrase, context={})


def test_resolves_type_target():
    a = _Adapter()
    t = _run(sdk._maybe_resolve_input(a, "web", _intent("type", "Remarks field")))
    assert t is not None and t.ref == '[data-bg-input="1"]'
    assert t.resolver_name == "input_dom"
    assert a.calls == ["Remarks field"]


def test_skips_non_type():
    a = _Adapter()
    assert _run(sdk._maybe_resolve_input(a, "web", _intent("click", "Remarks"))) is None
    assert a.calls == []


def test_skips_mobile():
    a = _Adapter()
    assert _run(sdk._maybe_resolve_input(a, "mobile", _intent("type", "Remarks"))) is None


def test_none_when_no_match():
    a = _Adapter(ref=None)
    assert _run(sdk._maybe_resolve_input(a, "web", _intent("type", "Remarks"))) is None


def test_none_when_no_target_phrase():
    a = _Adapter()
    assert _run(sdk._maybe_resolve_input(a, "web", _intent("type", ""))) is None
