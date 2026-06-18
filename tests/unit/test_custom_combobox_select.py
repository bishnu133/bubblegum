"""Custom (non-native) combobox selection in the Playwright adapter.

Ant Design / MUI / Angular CDK / React-Select render div/button-based
comboboxes (role="combobox") whose options live in a portal-rendered listbox.
Playwright's ``select_option()`` only drives a real ``<select>``, so
``_do_select`` must instead open the trigger and click the matching option.

These tests use lightweight fakes (no browser) to assert the dispatch:
  - native <select>      -> select_option (unchanged legacy path)
  - custom combobox      -> trigger.click() then option.click()
  - exact-name miss      -> falls back to a non-exact option match
"""

from __future__ import annotations

import asyncio
from typing import Any

from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter
from bubblegum.core.schemas import ActionPlan, ExecutionOptions, ResolvedTarget


def _run(coro):
    return asyncio.run(coro)


def _plan(value: str) -> ActionPlan:
    return ActionPlan(
        action_type="select",
        target_hint="x",
        input_value=value,
        options=ExecutionOptions(),
    )


def _target() -> ResolvedTarget:
    return ResolvedTarget(ref="#widget", confidence=1.0, resolver_name="test")


class _OptionLocator:
    """Stands in for a get_by_role(...) result; ``.first`` returns itself."""

    def __init__(self, *, name: str, clickable: bool) -> None:
        self.name = name
        self._clickable = clickable
        self.clicked = False

    @property
    def first(self) -> "_OptionLocator":
        return self

    async def click(self, *args: Any, **kwargs: Any) -> None:
        if not self._clickable:
            raise TimeoutError(f"no option matched {self.name!r}")
        self.clicked = True


class _TriggerLocator:
    def __init__(self, tag: str) -> None:
        self._tag = tag
        self.clicks = 0
        self.force_clicks = 0

    async def evaluate(self, _expr: str, *args: Any, **kwargs: Any) -> str:
        return self._tag

    async def click(self, *args: Any, **kwargs: Any) -> None:
        if kwargs.get("force"):
            self.force_clicks += 1
        self.clicks += 1


class _OverlayTriggerLocator(_TriggerLocator):
    """Mimics Ant Design: a normal click is intercepted; only force works."""

    async def click(self, *args: Any, **kwargs: Any) -> None:
        if not kwargs.get("force"):
            raise TimeoutError("selection-item <span> intercepts pointer events")
        self.force_clicks += 1
        self.clicks += 1


class _NativeSelectLocator(_TriggerLocator):
    def __init__(self) -> None:
        super().__init__("SELECT")
        self.select_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def select_option(self, *args: Any, **kwargs: Any) -> None:
        self.select_calls.append((args, kwargs))


class _ComboPage:
    """Returns the trigger from .locator(); serves options from get_by_role()."""

    def __init__(self, trigger, options: dict[tuple[str, str, bool], _OptionLocator]) -> None:
        self._trigger = trigger
        self._options = options
        self.url = "http://example.test/start"
        self.get_by_role_calls: list[tuple[str, str, bool]] = []

    def locator(self, _ref: str):
        return self._trigger

    def get_by_role(self, role: str, name: str = "", exact: bool = False) -> _OptionLocator:
        self.get_by_role_calls.append((role, name, exact))
        key = (role, name, exact)
        return self._options.get(key, _OptionLocator(name=name, clickable=False))


def test_native_select_still_uses_select_option():
    trigger = _NativeSelectLocator()
    page = _ComboPage(trigger, {})
    adapter = PlaywrightAdapter(page)

    result = _run(adapter.execute(_plan("India"), _target()))

    assert result.success is True
    assert trigger.clicks == 0
    assert trigger.select_calls and trigger.select_calls[0][0][0] == "India"


def test_custom_combobox_opens_then_clicks_exact_option():
    trigger = _TriggerLocator("DIV")
    option = _OptionLocator(name="Participant", clickable=True)
    page = _ComboPage(trigger, {("option", "Participant", True): option})
    adapter = PlaywrightAdapter(page)

    result = _run(adapter.execute(_plan("Participant"), _target()))

    assert result.success is True
    assert trigger.clicks == 1, "should open the dropdown before selecting"
    assert trigger.force_clicks == 0, "a plain-clickable trigger needs no force"
    assert option.clicked is True
    # Exact-name option match is tried first.
    assert page.get_by_role_calls[0] == ("option", "Participant", True)


def test_custom_combobox_force_opens_when_overlay_intercepts():
    # Ant Design: the inner role=combobox <input> is covered by a selection
    # <span>, so a normal click is intercepted — the adapter must force it open.
    trigger = _OverlayTriggerLocator("INPUT")
    option = _OptionLocator(name="Participant", clickable=True)
    page = _ComboPage(trigger, {("option", "Participant", True): option})
    adapter = PlaywrightAdapter(page)

    result = _run(adapter.execute(_plan("Participant"), _target()))

    assert result.success is True
    assert trigger.force_clicks == 1, "overlay interception must fall back to force click"
    assert option.clicked is True


def test_custom_combobox_falls_back_to_non_exact_option():
    trigger = _TriggerLocator("BUTTON")
    option = _OptionLocator(name="Tracker", clickable=True)
    # Only the non-exact lookup yields a clickable option.
    page = _ComboPage(trigger, {("option", "Tracker", False): option})
    adapter = PlaywrightAdapter(page)

    result = _run(adapter.execute(_plan("Tracker"), _target()))

    assert result.success is True
    assert option.clicked is True
    assert ("option", "Tracker", True) in page.get_by_role_calls
    assert ("option", "Tracker", False) in page.get_by_role_calls


def test_custom_combobox_no_matching_option_fails_clearly():
    trigger = _TriggerLocator("DIV")
    page = _ComboPage(trigger, {})  # nothing matches
    adapter = PlaywrightAdapter(page)

    result = _run(adapter.execute(_plan("Nope"), _target()))

    assert result.success is False
    assert "Nope" in (result.error or "")
