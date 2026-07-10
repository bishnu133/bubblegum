"""Deterministic DOM resolver for the start/end input of a date range picker.

Ant ``RangePicker`` inputs are nameless, so a "type into Start date" step can
ground onto the wrong element; ``_maybe_resolve_daterange`` pins the exact input
from the DOM before name-based grounding runs.
"""
from __future__ import annotations

import asyncio

import bubblegum.core.sdk as sdk
from bubblegum.core.schemas import StepIntent


def _run(c):
    return asyncio.run(c)


class _Adapter:
    def __init__(self, ref='[data-bg-daterange="1"]'):
        self._ref = ref
        self.calls = []

    async def find_date_range_input(self, which, target_phrase=""):
        self.calls.append((which, target_phrase))
        return self._ref


def _intent(action="type", target_phrase="Start date"):
    return StepIntent(instruction="x", channel="web", action_type=action,
                      target_phrase=target_phrase, context={})


def test_side_detection():
    assert sdk._date_range_side("Start date") == "start"
    assert sdk._date_range_side("the End date field") == "end"
    assert sdk._date_range_side("Visibility Period from date") == "start"
    assert sdk._date_range_side("until date") == "end"
    # No side named -> None (falls through to normal grounding).
    assert sdk._date_range_side("Display Name") is None
    assert sdk._date_range_side("date") is None
    assert sdk._date_range_side("") is None


def test_resolves_start():
    a = _Adapter()
    t = _run(sdk._maybe_resolve_daterange(a, "web", _intent("type", "Start date")))
    assert t is not None and t.ref == '[data-bg-daterange="1"]'
    assert t.resolver_name == "date_range_dom"
    assert t.metadata["which"] == "start"
    assert a.calls == [("start", "Start date")]


def test_resolves_end():
    a = _Adapter()
    t = _run(sdk._maybe_resolve_daterange(a, "web", _intent("type", "End date")))
    assert t is not None and t.metadata["which"] == "end"
    assert a.calls == [("end", "End date")]


def test_skips_when_no_side_named():
    # A generic field phrase must not be claimed by the range resolver.
    a = _Adapter()
    assert _run(sdk._maybe_resolve_daterange(a, "web", _intent("type", "Display Name"))) is None
    assert a.calls == []


def test_skips_non_type():
    a = _Adapter()
    assert _run(sdk._maybe_resolve_daterange(a, "web", _intent("click", "Start date"))) is None
    assert a.calls == []


def test_skips_mobile():
    a = _Adapter()
    assert _run(sdk._maybe_resolve_daterange(a, "mobile", _intent("type", "Start date"))) is None


def test_none_when_no_picker_on_page():
    # Adapter returns None (no range picker) -> resolver yields None, so the step
    # falls through to normal grounding. Non-picker pages are unaffected.
    a = _Adapter(ref=None)
    assert _run(sdk._maybe_resolve_daterange(a, "web", _intent("type", "Start date"))) is None
