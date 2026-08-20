"""`type` into a date/time picker input activates, types with real keystrokes,
commits, and verifies the value stuck (retrying once if it didn't).

Ant `RangePicker` (and similar React-controlled widgets) keep "active editing" on
one field and only commit on Enter, and a programmatic ``fill()`` value can be
dropped/reverted (headless-only flake). ``_do_type`` detects a picker input and
drives: click → clear → type value key-by-key → Enter → verify → retry-once.
Ordinary text inputs keep the plain ``fill()`` path (no stray Enter).
"""
from __future__ import annotations

import asyncio

from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter
from bubblegum.core.schemas import ActionPlan


def _run(c):
    return asyncio.run(c)


class _Locator:
    """Records the calls _do_type makes; ``is_picker`` drives the probe result.

    Models a working picker: keystrokes set the value, `input_value` reflects it.
    """

    def __init__(self, is_picker: bool):
        self._is_picker = is_picker
        self.calls: list[str] = []
        self.value = ""

    async def evaluate(self, _js):
        return self._is_picker

    async def click(self, timeout=None):
        self.calls.append("click")

    async def fill(self, value, timeout=None):
        self.calls.append(f"fill:{value}")
        self.value = value

    async def press_sequentially(self, text, delay=None, timeout=None):
        self.calls.append(f"type:{text}")
        self.value = text

    async def press(self, key, timeout=None):
        self.calls.append(f"press:{key}")

    async def input_value(self, timeout=None):
        return self.value


def _adapter():
    return PlaywrightAdapter.__new__(PlaywrightAdapter)  # no real page needed


def _plan(value="06/07/2026 07:00"):
    return ActionPlan(action_type="type", target_hint="Start date", input_value=value)


def test_picker_input_clicks_types_and_commits():
    a, loc = _adapter(), _Locator(is_picker=True)
    _run(a._do_type(_plan(), loc, timeout=1000))
    # click, clear, type via real keystrokes, commit — no retry (value stuck).
    assert loc.calls == ["click", "fill:", "type:06/07/2026 07:00", "press:Enter"]
    assert loc.value == "06/07/2026 07:00"


def test_plain_input_only_fills():
    a, loc = _adapter(), _Locator(is_picker=False)
    _run(a._do_type(_plan("hello"), loc, timeout=1000))
    assert loc.calls == ["fill:hello"]  # no click, no Enter


def test_commit_failure_is_swallowed():
    # If Enter can't be pressed, the value is already typed — don't fail the step.
    class _NoEnter(_Locator):
        async def press(self, key, timeout=None):
            raise RuntimeError("cannot press")

    a, loc = _adapter(), _NoEnter(is_picker=True)
    _run(a._do_type(_plan(), loc, timeout=1000))  # must not raise
    assert loc.calls[:3] == ["click", "fill:", "type:06/07/2026 07:00"]


def test_dropped_commit_triggers_one_retry():
    # A picker whose value is empty after the first Enter (a lost commit) is
    # re-entered once; the retry uses select-all + backspace, then re-types.
    class _FlakyCommit(_Locator):
        def __init__(self):
            super().__init__(is_picker=True)
            self._reads = 0

        async def input_value(self, timeout=None):
            self._reads += 1
            # First verification sees an empty field (dropped commit); the retry
            # re-types and this fake keeps that value.
            return "" if self._reads == 1 else self.value

    a, loc = _adapter(), _FlakyCommit()
    _run(a._do_type(_plan(), loc, timeout=1000))
    # A second type + Enter happened after the empty read.
    assert loc.calls.count("type:06/07/2026 07:00") == 2
    assert loc.calls.count("press:Enter") == 2
    assert "press:Backspace" in loc.calls
