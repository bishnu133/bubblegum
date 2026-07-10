"""Deterministic DOM resolver for `upload` steps into hidden file inputs.

Upload widgets (Ant/MUI ``Upload``) hide the real ``<input type=file>`` behind a
styled button, so name-based grounding can't reach it. ``_maybe_resolve_upload``
pins the file input from the DOM by label / section / id before grounding runs.
"""
from __future__ import annotations

import asyncio

import bubblegum.core.sdk as sdk
from bubblegum.core.schemas import StepIntent


def _run(c):
    return asyncio.run(c)


class _Adapter:
    def __init__(self, ref='[data-bg-file="1"]'):
        self._ref = ref
        self.calls = []

    async def find_file_input(self, target_phrase):
        self.calls.append(target_phrase)
        return self._ref


def _intent(action="upload", target_phrase="Awarded Album View"):
    return StepIntent(instruction="x", channel="web", action_type=action,
                      target_phrase=target_phrase, input_value="/tmp/badge.png", context={})


def test_resolves_upload_target():
    a = _Adapter()
    t = _run(sdk._maybe_resolve_upload(a, "web", _intent()))
    assert t is not None and t.ref == '[data-bg-file="1"]'
    assert t.resolver_name == "file_input_dom"
    assert a.calls == ["Awarded Album View"]


def test_skips_non_upload():
    a = _Adapter()
    assert _run(sdk._maybe_resolve_upload(a, "web", _intent("type", "Display Name"))) is None
    assert a.calls == []


def test_skips_mobile():
    a = _Adapter()
    assert _run(sdk._maybe_resolve_upload(a, "mobile", _intent())) is None


def test_none_when_no_file_input():
    # Adapter returns None (no file input on the page) -> resolver yields None and
    # the step falls through to normal grounding. Non-upload pages unaffected.
    a = _Adapter(ref=None)
    assert _run(sdk._maybe_resolve_upload(a, "web", _intent())) is None


def test_none_when_no_target_phrase():
    a = _Adapter()
    assert _run(sdk._maybe_resolve_upload(a, "web", _intent("upload", ""))) is None
