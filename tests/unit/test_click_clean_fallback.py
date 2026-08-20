"""Low-confidence click fallback strips widget-kind noise words.

"Click on the My Account menu" grounds low-confidence when the phrase carries the
widget-kind word ("menu") that isn't part of the element's accessible name ("My
Account"). The clickable DOM fallback now tries the cleaned phrase first, so it
resolves the menu title by its real name.
"""
from __future__ import annotations

import asyncio

import bubblegum.core.sdk as sdk
from bubblegum.core.schemas import StepIntent


def _run(c):
    return asyncio.run(c)


class _Adapter:
    """find_clickable that only matches the clean accessible name 'My Account'."""

    def __init__(self):
        self.calls: list[str] = []

    async def find_clickable(self, text, exact=False):
        self.calls.append(text)
        return '[data-bg="1"]' if text.strip().lower() == "my account" else None


def _intent(instr, phrase, action="click"):
    return StepIntent(instruction=instr, channel="web", action_type=action,
                      target_phrase=phrase, context={})


def test_clean_click_phrase():
    f = sdk._clean_click_phrase
    assert f("the My Account menu") == "My Account"
    assert f("on the My Account menu") == "My Account"
    assert f("My Account submenu") == "My Account"
    assert f("the Next button") == "Next"
    assert f("Activities menu") == "Activities"
    assert f("the Search icon") == "Search"
    assert f("Logout") == "Logout"                 # nothing to strip
    assert f('the "Yes, approve" button') == "Yes, approve"


def test_fallback_resolves_menu_via_cleaned_phrase():
    a = _Adapter()
    intent = _intent("Click on the My Account menu", "the My Account menu")
    t = _run(sdk._maybe_resolve_clickable(a, "web", "Click on the My Account menu", intent))
    assert t is not None and t.resolver_name == "clickable_dom"
    # The cleaned phrase "My Account" was tried (and matched); the raw phrase alone
    # ("the My Account menu") would not have matched the fake finder.
    assert any(c.strip().lower() == "my account" for c in a.calls)


def test_fallback_returns_none_when_nothing_matches():
    class _None(_Adapter):
        async def find_clickable(self, text, exact=False):
            self.calls.append(text)
            return None

    a = _None()
    intent = _intent("Click on the Ghost menu", "the Ghost menu")
    assert _run(sdk._maybe_resolve_clickable(a, "web", "Click on the Ghost menu", intent)) is None


def test_fallback_skips_non_click_and_mobile():
    a = _Adapter()
    assert _run(sdk._maybe_resolve_clickable(a, "web", "Enter x", _intent("Enter x", "x", "type"))) is None
    assert _run(sdk._maybe_resolve_clickable(a, "mobile", "Click x", _intent("Click x", "x"))) is None
