"""Phase 22D-7: dom_helpers — find_open_dialog and follow_aria_controls.

Covers:
  - find_open_dialog: probe order (aria-modal > alertdialog > <dialog open> >
    role=dialog), empty page returns (None, None), JSON-safe return shape.
  - follow_aria_controls: aria-controls preferred over aria-owns, space-
    separated IDREFs take the first, missing/empty attributes return None,
    referenced node missing returns None, ID escaping for special chars.

Fakes mimic the minimum Playwright async surface used by the helpers:
  page.locator(selector) -> _FakeLocator
  locator.count() -> int (async)
  locator.first -> Locator
  locator.get_attribute(name) -> str | None (async)
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from bubblegum.core.grounding.dom_helpers import (
    _OPEN_DIALOG_SELECTORS,
    _css_escape_id,
    find_open_dialog,
    follow_aria_controls,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeLocator:
    def __init__(
        self,
        *,
        count: int = 0,
        attributes: dict[str, str] | None = None,
    ) -> None:
        self._count = count
        self._attributes: dict[str, str] = dict(attributes or {})

    @property
    def first(self) -> "_FakeLocator":
        return self

    async def count(self) -> int:
        return self._count

    async def get_attribute(self, name: str) -> str | None:
        return self._attributes.get(name)


class _FakePage:
    def __init__(self, locators: dict[str, _FakeLocator] | None = None) -> None:
        # locators keyed by selector string; misses return an empty locator.
        self._locators = locators or {}

    def locator(self, selector: str) -> _FakeLocator:
        return self._locators.get(selector, _FakeLocator(count=0))


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# find_open_dialog
# ---------------------------------------------------------------------------


def test_find_open_dialog_prefers_aria_modal():
    aria_modal = _FakeLocator(count=1)
    alert = _FakeLocator(count=1)
    plain = _FakeLocator(count=1)
    page = _FakePage(
        {
            "[role='dialog'][aria-modal='true']": aria_modal,
            "[role='alertdialog']": alert,
            "[role='dialog']": plain,
        }
    )

    locator, selector = _run(find_open_dialog(page))

    assert locator is aria_modal
    assert selector == "[role='dialog'][aria-modal='true']"


def test_find_open_dialog_falls_back_to_alertdialog():
    alert = _FakeLocator(count=1)
    page = _FakePage({"[role='alertdialog']": alert})

    locator, selector = _run(find_open_dialog(page))

    assert locator is alert
    assert selector == "[role='alertdialog']"


def test_find_open_dialog_falls_back_to_html_dialog_open():
    html_dialog = _FakeLocator(count=1)
    page = _FakePage({"dialog[open]": html_dialog})

    locator, selector = _run(find_open_dialog(page))

    assert locator is html_dialog
    assert selector == "dialog[open]"


def test_find_open_dialog_falls_back_to_plain_role_dialog():
    plain = _FakeLocator(count=1)
    page = _FakePage({"[role='dialog']": plain})

    locator, selector = _run(find_open_dialog(page))

    assert locator is plain
    assert selector == "[role='dialog']"


def test_find_open_dialog_returns_none_when_nothing_matches():
    page = _FakePage({})  # all probes return count=0

    locator, selector = _run(find_open_dialog(page))

    assert locator is None
    assert selector is None


def test_find_open_dialog_probe_order_is_stable():
    # Pin the probe order so future selector additions are explicit.
    assert _OPEN_DIALOG_SELECTORS == (
        "[role='dialog'][aria-modal='true']",
        "[role='alertdialog']",
        "dialog[open]",
        "[role='dialog']",
    )


# ---------------------------------------------------------------------------
# follow_aria_controls
# ---------------------------------------------------------------------------


def test_follow_aria_controls_returns_target_for_aria_controls():
    trigger = _FakeLocator(attributes={"aria-controls": "country-listbox"})
    target = _FakeLocator(count=1)
    page = _FakePage({"#country-listbox": target})

    result = _run(follow_aria_controls(page, trigger))

    assert result is target


def test_follow_aria_controls_prefers_controls_over_owns():
    trigger = _FakeLocator(attributes={
        "aria-controls": "lb-controls",
        "aria-owns": "lb-owns",
    })
    controls_target = _FakeLocator(count=1)
    owns_target = _FakeLocator(count=1)
    page = _FakePage({
        "#lb-controls": controls_target,
        "#lb-owns": owns_target,
    })

    result = _run(follow_aria_controls(page, trigger))

    assert result is controls_target


def test_follow_aria_controls_falls_back_to_aria_owns():
    trigger = _FakeLocator(attributes={"aria-owns": "menu-1"})
    target = _FakeLocator(count=1)
    page = _FakePage({"#menu-1": target})

    result = _run(follow_aria_controls(page, trigger))

    assert result is target


def test_follow_aria_controls_takes_first_idref_when_multiple():
    trigger = _FakeLocator(attributes={"aria-controls": "panel-a panel-b panel-c"})
    target_a = _FakeLocator(count=1)
    page = _FakePage({"#panel-a": target_a})

    result = _run(follow_aria_controls(page, trigger))

    assert result is target_a


def test_follow_aria_controls_returns_none_when_no_attributes():
    trigger = _FakeLocator(attributes={})
    page = _FakePage({})

    result = _run(follow_aria_controls(page, trigger))

    assert result is None


def test_follow_aria_controls_returns_none_for_empty_string():
    trigger = _FakeLocator(attributes={"aria-controls": "", "aria-owns": ""})
    page = _FakePage({})

    result = _run(follow_aria_controls(page, trigger))

    assert result is None


def test_follow_aria_controls_returns_none_when_target_missing():
    trigger = _FakeLocator(attributes={"aria-controls": "ghost"})
    page = _FakePage({})  # #ghost does not exist (count=0)

    result = _run(follow_aria_controls(page, trigger))

    assert result is None


def test_follow_aria_controls_strips_whitespace_in_attribute_value():
    trigger = _FakeLocator(attributes={"aria-controls": "  spaced-id  "})
    target = _FakeLocator(count=1)
    page = _FakePage({"#spaced-id": target})

    result = _run(follow_aria_controls(page, trigger))

    assert result is target


# ---------------------------------------------------------------------------
# _css_escape_id
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("country-listbox", "country-listbox"),
        ("plain_id", "plain_id"),
        ("alphanum123", "alphanum123"),
        ("with.dot", r"with\.dot"),
        ("with:colon", r"with\:colon"),
        ("with space", r"with\ space"),
        ("with[bracket", r"with\[bracket"),
    ],
)
def test_css_escape_id_handles_special_chars(raw: str, expected: str) -> None:
    assert _css_escape_id(raw) == expected


def test_css_escape_id_escapes_leading_digit():
    # Per CSS, identifiers cannot start with a digit unless escaped.
    assert _css_escape_id("1abc") == "\\31 abc"


def test_css_escape_id_empty_string_is_unchanged():
    assert _css_escape_id("") == ""


# ---------------------------------------------------------------------------
# Integration: scope.close_dialog_web now consumes find_open_dialog
# ---------------------------------------------------------------------------


def test_close_dialog_web_still_works_through_shared_helper():
    # Sanity check that the refactor in scope.py still produces the same
    # outcome for a basic page-level aria-modal dialog.
    from bubblegum.core.scope import ScopeStack, close_dialog_web

    class _Btn:
        def __init__(self) -> None:
            self.clicked = False
            self.clicks: list[str] = []

        @property
        def first(self):
            return self

        async def count(self):
            return 1

        async def click(self, **_):
            self.clicked = True
            self.clicks.append("Close")

    class _DialogLocator:
        def __init__(self, btn):
            self._btn = btn

        @property
        def first(self):
            return self

        async def count(self):
            return 1

        def get_by_role(self, role, name=None):
            if role == "button" and name is not None:
                return self._btn
            return _Btn()

    class _Keyboard:
        def __init__(self):
            self.presses: list[str] = []

        async def press(self, key):
            self.presses.append(key)

    class _Page:
        def __init__(self, dialog):
            self._dialog = dialog
            self.keyboard = _Keyboard()

        def locator(self, sel):
            if sel == "[role='dialog'][aria-modal='true']":
                return self._dialog
            class _Empty:
                @property
                def first(self):
                    return self

                async def count(self):
                    return 0
            return _Empty()

    btn = _Btn()
    page = _Page(_DialogLocator(btn))
    stack = ScopeStack()

    report = _run(close_dialog_web(page, stack))

    assert report["closed_by"] == "close_button"
    assert report["dialog_detected_via"] == "[role='dialog'][aria-modal='true']"
    assert btn.clicked is True
    assert page.keyboard.presses == []
