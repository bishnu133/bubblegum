"""Phase 22D-6: SessionScope stack + close_dialog helper.

Covers:
  - ScopeStack push/pop/current/depth/is_dialog_active/snapshot semantics
  - SessionScope dataclass defaults
  - close_dialog_web behaviour against a fake Playwright page:
      * dialog with a "Close" button -> button click, scope pops
      * dialog with no close affordance -> Escape fallback, scope pops
      * no dialog at all -> Escape fallback, no scope pop
      * scope-pinned dialog skips the page-level dialog scan
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import pytest

from bubblegum.core.scope import (
    ScopeStack,
    SessionScope,
    _CLOSE_BUTTON_RE,
    close_dialog_web,
)


# ---------------------------------------------------------------------------
# Fakes — minimal Playwright async API surface
# ---------------------------------------------------------------------------


class _FakeLocator:
    """Fake locator covering count / first / get_by_role / click.

    Children produced via get_by_role share the same `clicks` list as the
    parent, so a test can assert on the original dialog-root locator that a
    descendant button was clicked.
    """

    def __init__(
        self,
        *,
        count: int = 0,
        buttons: list[str] | None = None,
        clicks: list[str] | None = None,
    ) -> None:
        self._count = count
        self._buttons = list(buttons or [])
        self.clicks: list[str] = clicks if clicks is not None else []

    @property
    def first(self) -> "_FakeLocator":
        return self

    @property
    def clicked(self) -> bool:
        return bool(self.clicks)

    async def count(self) -> int:
        return self._count

    def get_by_role(self, role: str, name: Any = None) -> "_FakeLocator":
        if role != "button":
            return _FakeLocator(count=0, clicks=self.clicks)
        if name is None:
            matches = list(self._buttons)
        elif isinstance(name, str):
            matches = [b for b in self._buttons if b.lower() == name.lower()]
        elif isinstance(name, re.Pattern):
            matches = [b for b in self._buttons if name.search(b)]
        else:
            matches = []
        return _FakeLocator(count=len(matches), buttons=matches, clicks=self.clicks)

    async def click(self, **_: Any) -> None:
        self.clicks.append(self._buttons[0] if self._buttons else "(unmatched)")


class _FakeKeyboard:
    def __init__(self) -> None:
        self.presses: list[str] = []

    async def press(self, key: str) -> None:
        self.presses.append(key)


class _FakePage:
    def __init__(self, locators: dict[str, _FakeLocator] | None = None) -> None:
        # locators: {selector: _FakeLocator returned by page.locator(sel)}
        self._locators = locators or {}
        self.keyboard = _FakeKeyboard()

    def locator(self, selector: str) -> _FakeLocator:
        return self._locators.get(selector, _FakeLocator(count=0))


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# ScopeStack
# ---------------------------------------------------------------------------


def test_scope_stack_starts_with_page_scope():
    stack = ScopeStack()
    assert stack.current().type == "page"
    assert stack.depth() == 0
    assert stack.is_dialog_active() is False


def test_push_and_pop_dialog_scope():
    stack = ScopeStack()
    stack.push(SessionScope(type="dialog", label="Settings"))
    assert stack.current().type == "dialog"
    assert stack.current().label == "Settings"
    assert stack.depth() == 1
    assert stack.is_dialog_active() is True

    popped = stack.pop()
    assert popped is not None and popped.type == "dialog"
    assert stack.current().type == "page"
    assert stack.depth() == 0


def test_pop_on_base_page_scope_returns_none():
    stack = ScopeStack()
    assert stack.pop() is None
    assert stack.current().type == "page"


def test_snapshot_is_json_safe():
    import json

    stack = ScopeStack()
    stack.push(SessionScope(type="dialog", label="Confirm"))
    snap = stack.snapshot()
    json.dumps(snap)
    assert snap == [{"type": "page", "label": None}, {"type": "dialog", "label": "Confirm"}]


# ---------------------------------------------------------------------------
# Close-button regex
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["Close", "close", "CLOSE", "Cancel", "Dismiss", "X", "x", "×", " close "])
def test_close_button_regex_matches_common_affordances(name):
    assert _CLOSE_BUTTON_RE.match(name) is not None


@pytest.mark.parametrize("name", ["Save", "Submit", "OK", "Confirm", "Closer", "Cancel order"])
def test_close_button_regex_rejects_non_close_buttons(name):
    assert _CLOSE_BUTTON_RE.match(name) is None


# ---------------------------------------------------------------------------
# close_dialog_web — page-level dialog detection
# ---------------------------------------------------------------------------


def test_close_dialog_clicks_internal_close_button():
    dialog = _FakeLocator(count=1, buttons=["Close"])
    page = _FakePage({"[role='dialog'][aria-modal='true']": dialog})
    stack = ScopeStack()

    report = _run(close_dialog_web(page, stack))

    # The button inside the dialog should have been clicked, not Escape.
    assert page.keyboard.presses == []
    assert report["closed_by"] == "close_button"
    assert report["dialog_detected_via"] == "[role='dialog'][aria-modal='true']"
    assert report["popped_scope"] is None  # nothing on the stack to pop
    assert report["scope_after"] == "page"


def test_close_dialog_falls_back_to_escape_when_no_close_affordance():
    dialog = _FakeLocator(count=1, buttons=["Save", "Submit"])
    page = _FakePage({"[role='dialog'][aria-modal='true']": dialog})
    stack = ScopeStack()

    report = _run(close_dialog_web(page, stack))

    assert dialog.clicked is False
    assert page.keyboard.presses == ["Escape"]
    assert report["closed_by"] == "escape"
    assert report["dialog_detected_via"] == "[role='dialog'][aria-modal='true']"


def test_close_dialog_with_no_dialog_pressed_escape_anyway():
    page = _FakePage({})  # no dialog selectors match
    stack = ScopeStack()

    report = _run(close_dialog_web(page, stack))

    assert page.keyboard.presses == ["Escape"]
    assert report["closed_by"] == "escape"
    assert report["dialog_detected_via"] is None
    assert report["popped_scope"] is None
    assert report["scope_after"] == "page"


def test_close_dialog_tries_alertdialog_when_aria_modal_misses():
    alert = _FakeLocator(count=1, buttons=["Dismiss"])
    page = _FakePage(
        {
            # aria-modal selector intentionally absent
            "[role='alertdialog']": alert,
        }
    )
    stack = ScopeStack()

    report = _run(close_dialog_web(page, stack))

    assert report["closed_by"] == "close_button"
    assert report["dialog_detected_via"] == "[role='alertdialog']"
    assert alert.clicked is True


# ---------------------------------------------------------------------------
# close_dialog_web — scope-pinned dialog
# ---------------------------------------------------------------------------


def test_close_dialog_uses_scope_root_when_present():
    # When the session has a dialog scope with a root_locator, we should not
    # scan the page; we should drive the close affordance off the scope root.
    scope_root = _FakeLocator(count=1, buttons=["Close"])
    page = _FakePage(
        {
            # Even though a different dialog exists on the page, the scope
            # root wins -- this asserts we do not scan when scope is pinned.
            "[role='dialog'][aria-modal='true']": _FakeLocator(count=1, buttons=["Save"]),
        }
    )
    stack = ScopeStack()
    stack.push(SessionScope(type="dialog", label="Settings", root_locator=scope_root))

    report = _run(close_dialog_web(page, stack))

    assert scope_root.clicked is True
    assert report["closed_by"] == "close_button"
    assert report["dialog_detected_via"] == "scope"
    assert report["popped_scope"] == {"type": "dialog", "label": "Settings"}
    assert report["scope_after"] == "page"
    assert stack.current().type == "page"


def test_close_dialog_pops_scope_even_when_falling_back_to_escape():
    scope_root = _FakeLocator(count=1, buttons=["Save", "Submit"])  # no close affordance
    page = _FakePage({})
    stack = ScopeStack()
    stack.push(SessionScope(type="dialog", label="Edit", root_locator=scope_root))

    report = _run(close_dialog_web(page, stack))

    assert page.keyboard.presses == ["Escape"]
    assert report["closed_by"] == "escape"
    assert report["popped_scope"] == {"type": "dialog", "label": "Edit"}
    assert stack.current().type == "page"


# ---------------------------------------------------------------------------
# BubblegumSession integration
# ---------------------------------------------------------------------------


def test_session_exposes_scope_stack_and_pushes_correctly():
    from bubblegum.session import BubblegumSession

    s = BubblegumSession.web(page=_FakePage({}))
    assert s.current_scope.type == "page"
    assert s.scope_snapshot() == [{"type": "page", "label": None}]

    s.push_scope("dialog", label="Confirm")
    assert s.current_scope.type == "dialog"
    assert s.current_scope.label == "Confirm"
    assert s.scope_snapshot() == [
        {"type": "page", "label": None},
        {"type": "dialog", "label": "Confirm"},
    ]

    popped = s.pop_scope()
    assert popped is not None and popped.type == "dialog"
    assert s.current_scope.type == "page"


def test_session_close_dialog_drives_helper_and_pops_scope():
    from bubblegum.session import BubblegumSession

    scope_root = _FakeLocator(count=1, buttons=["Close"])
    page = _FakePage({})
    s = BubblegumSession.web(page=page)
    s.push_scope("dialog", label="Settings", root_locator=scope_root)

    report = _run(s.close_dialog())

    assert report["closed_by"] == "close_button"
    assert scope_root.clicked is True
    assert s.current_scope.type == "page"


def test_session_close_dialog_raises_on_mobile_channel():
    from bubblegum.session import BubblegumSession

    s = BubblegumSession.mobile(driver=object())
    with pytest.raises(NotImplementedError, match="web channel"):
        _run(s.close_dialog())
