"""Prefer a clickable inside the topmost open dialog for click/tap steps.

When a blocking modal is open, a button with the same name usually also exists on
the page behind it (covered by the modal mask). ``_maybe_resolve_dialog_click``
pins the button inside the dialog before grounding runs.
"""
from __future__ import annotations

import asyncio

import bubblegum.core.sdk as sdk
from bubblegum.core.schemas import StepIntent


def _run(c):
    return asyncio.run(c)


class _Adapter:
    def __init__(self, ref='[data-bg-dialogclick="1"]'):
        self._ref = ref
        self.calls = []

    async def find_dialog_clickable(self, text, *, exact=False):
        self.calls.append(text)
        return self._ref


def _intent(action="click", target_phrase="Submit button on Submit Badge? dialog"):
    return StepIntent(instruction="Click " + (target_phrase or ""), channel="web",
                      action_type=action, target_phrase=target_phrase, context={})


def test_resolves_click_in_dialog():
    a = _Adapter()
    t = _run(sdk._maybe_resolve_dialog_click(a, "web", _intent()))
    assert t is not None and t.ref == '[data-bg-dialogclick="1"]'
    assert t.resolver_name == "dialog_click_dom"
    assert a.calls == ["Submit button on Submit Badge? dialog"]


def test_prefers_quoted_button_label_over_mangled_target_phrase():
    # `Click on "Add" button`: the parser mangles target_phrase to 'on "Add', and
    # the raw instruction trips the finder's "on" scope-split. The quoted label is
    # authoritative — the finder must be called with "Add".
    a = _Adapter()
    intent = StepIntent(instruction='Click on "Add" button', channel="web",
                        action_type="click", target_phrase='on "Add', context={})
    t = _run(sdk._maybe_resolve_dialog_click(a, "web", intent))
    assert t is not None and t.resolver_name == "dialog_click_dom"
    assert a.calls == ["Add"]


def test_tap_is_also_handled():
    a = _Adapter()
    t = _run(sdk._maybe_resolve_dialog_click(a, "web", _intent("tap", "Submit")))
    assert t is not None and t.resolver_name == "dialog_click_dom"


def test_skips_non_click():
    a = _Adapter()
    assert _run(sdk._maybe_resolve_dialog_click(a, "web", _intent("type", "Name"))) is None
    assert a.calls == []


def test_skips_mobile():
    a = _Adapter()
    assert _run(sdk._maybe_resolve_dialog_click(a, "mobile", _intent())) is None


def test_none_when_no_dialog_open():
    # Adapter returns None (no open dialog) -> resolver yields None and the click
    # falls through to normal grounding. Non-modal flows are unaffected.
    a = _Adapter(ref=None)
    assert _run(sdk._maybe_resolve_dialog_click(a, "web", _intent())) is None
