"""Rich-text (contenteditable) DOM pre-resolution for `type` steps.

RTE widgets (Quill, TinyMCE, ProseMirror, …) render as a bare
``[contenteditable]`` div with no ``textbox`` role and no accessible name, so
name-based grounding can't see them and may mis-match a nearby valued input
(e.g. a just-filled tagline whose value leaked into the a11y tree). These tests
cover the SDK wiring; ``test_ant_nested_label_input.py`` covers the browser-level
DOM behaviour.
"""
from __future__ import annotations

import asyncio

import bubblegum.core.sdk as sdk
from bubblegum.core.schemas import StepIntent


def _run(c):
    return asyncio.run(c)


class _Adapter:
    def __init__(self, ref='[data-bg-input="1"]'):
        self._ref = ref
        self.calls = []

    async def find_rich_text(self, target_phrase):
        self.calls.append(target_phrase)
        return self._ref


def _intent(action="type", target_phrase="About this Challenge"):
    return StepIntent(instruction="x", channel="web", action_type=action,
                      target_phrase=target_phrase, context={})


def test_resolves_rich_text_target():
    a = _Adapter()
    t = _run(sdk._maybe_resolve_rich_text(a, "web", _intent("type", "About this Challenge")))
    assert t is not None and t.ref == '[data-bg-input="1"]'
    assert t.resolver_name == "rich_text_dom"
    assert t.metadata.get("rich_text_dom") is True
    assert a.calls == ["About this Challenge"]


def test_skips_non_type():
    a = _Adapter()
    assert _run(sdk._maybe_resolve_rich_text(a, "web", _intent("click", "About"))) is None
    assert a.calls == []


def test_skips_mobile():
    a = _Adapter()
    assert _run(sdk._maybe_resolve_rich_text(a, "mobile", _intent("type", "About"))) is None


def test_none_when_no_match():
    """No RTE on the page (or only a partial label match) -> fall through."""
    a = _Adapter(ref=None)
    assert _run(sdk._maybe_resolve_rich_text(a, "web", _intent("type", "About"))) is None


def test_none_when_no_target_phrase():
    a = _Adapter()
    assert _run(sdk._maybe_resolve_rich_text(a, "web", _intent("type", ""))) is None


def test_missing_finder_is_safe():
    """Adapters without find_rich_text (e.g. mobile) must not error."""
    class _Bare:
        pass
    assert _run(sdk._maybe_resolve_rich_text(_Bare(), "web", _intent("type", "About"))) is None
