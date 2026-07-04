"""`type` into a date/time picker input activates + commits (click, fill, Enter).

Ant `RangePicker` (and similar widgets) keep "active editing" on one field and
only commit typed text on Enter, so a bare ``fill()`` sends both range values to
the start input. ``_do_type`` detects a picker input and drives the full
sequence; ordinary text inputs keep the plain ``fill()`` path (no stray Enter).
"""
from __future__ import annotations

import asyncio

from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter
from bubblegum.core.schemas import ActionPlan


def _run(c):
    return asyncio.run(c)


class _Locator:
    """Records the calls _do_type makes; ``is_picker`` drives the probe result."""

    def __init__(self, is_picker: bool):
        self._is_picker = is_picker
        self.calls: list[str] = []

    async def evaluate(self, _js):
        return self._is_picker

    async def click(self, timeout=None):
        self.calls.append("click")

    async def fill(self, value, timeout=None):
        self.calls.append(f"fill:{value}")

    async def press(self, key, timeout=None):
        self.calls.append(f"press:{key}")


def _adapter():
    return PlaywrightAdapter.__new__(PlaywrightAdapter)  # no real page needed


def _plan(value="06/07/2026 07:00"):
    return ActionPlan(action_type="type", target_hint="Start date", input_value=value)


def test_picker_input_clicks_fills_and_commits():
    a, loc = _adapter(), _Locator(is_picker=True)
    _run(a._do_type(_plan(), loc, timeout=1000))
    assert loc.calls == ["click", "fill:06/07/2026 07:00", "press:Enter"]


def test_plain_input_only_fills():
    a, loc = _adapter(), _Locator(is_picker=False)
    _run(a._do_type(_plan("hello"), loc, timeout=1000))
    assert loc.calls == ["fill:hello"]  # no click, no Enter


def test_commit_failure_is_swallowed():
    # If Enter can't be pressed, the value is already set — don't fail the step.
    class _NoEnter(_Locator):
        async def press(self, key, timeout=None):
            raise RuntimeError("cannot press")

    a, loc = _adapter(), _NoEnter(is_picker=True)
    _run(a._do_type(_plan(), loc, timeout=1000))  # must not raise
    assert loc.calls[:2] == ["click", "fill:06/07/2026 07:00"]
