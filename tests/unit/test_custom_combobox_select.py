"""Custom (non-native) combobox selection in the Playwright adapter.

Ant Design / MUI / Angular CDK / React-Select render div/button-based
comboboxes (role="combobox") whose options live in a portal-rendered listbox.
Playwright's ``select_option()`` only drives a real ``<select>``, so
``_do_select`` must instead open the trigger and click the matching option.

These tests use lightweight fakes (no browser) to assert the dispatch:
  - native <select>           -> select_option (unchanged legacy path)
  - role=option widget        -> get_by_role(...).click
  - overlay-intercepted open  -> force click
  - role-less Ant option rows -> matched by .ant-select-item-option + title/text
  - no match                  -> clear error
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


class _FlexLocator:
    """A locator that can chain like a real Playwright Locator.

    ``clickable`` decides whether ``click`` succeeds. ``by_text`` / ``by_title``
    map (value, exact) -> child _FlexLocator so container-style lookups resolve.
    """

    def __init__(self, *, name: str = "", clickable: bool = False,
                 by_text: dict | None = None, by_title: dict | None = None) -> None:
        self.name = name
        self._clickable = clickable
        self._by_text = by_text or {}
        self._by_title = by_title or {}
        self.clicked = False

    @property
    def first(self) -> "_FlexLocator":
        return self

    async def count(self) -> int:
        return 1 if self._clickable else 0

    async def wait_for(self, *args: Any, **kwargs: Any) -> None:
        if not self._clickable:
            raise TimeoutError("not visible")

    async def click(self, *args: Any, **kwargs: Any) -> None:
        if not self._clickable:
            raise TimeoutError(f"no match for {self.name!r}")
        self.clicked = True

    def get_by_text(self, text: str, exact: bool = False) -> "_FlexLocator":
        return self._by_text.get((text, exact), _FlexLocator(name=f"text:{text}"))

    def get_by_title(self, title: str, exact: bool = False) -> "_FlexLocator":
        return self._by_title.get((title, exact), _FlexLocator(name=f"title:{title}"))


class _TriggerLocator:
    def __init__(self, tag: str, attrs: dict[str, str] | None = None) -> None:
        self._tag = tag
        self._attrs = attrs or {}
        self.clicks = 0
        self.force_clicks = 0

    @property
    def first(self) -> "_TriggerLocator":
        return self

    async def evaluate(self, _expr: str, *args: Any, **kwargs: Any) -> str:
        return self._tag

    async def get_attribute(self, name: str) -> str | None:
        return self._attrs.get(name)

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
    """Routes locator()/get_by_role() to fakes.

    - ``.locator("#widget")`` -> the trigger (the resolved combobox).
    - ``.locator(css[, has_text])`` -> ``css_map`` entry, else an empty
      (non-clickable) _FlexLocator. ``[id="..."]`` returns ``container``.
    - ``.get_by_role(role, name, exact)`` -> ``role_map`` entry, else empty.
    """

    def __init__(self, trigger, *,
                 role_map: dict[tuple[str, str, bool], _FlexLocator] | None = None,
                 css_map: dict[str, _FlexLocator] | None = None,
                 container: _FlexLocator | None = None) -> None:
        self._trigger = trigger
        self._role_map = role_map or {}
        self._css_map = css_map or {}
        self._container = container
        self.url = "http://example.test/start"
        self.get_by_role_calls: list[tuple[str, str, bool]] = []
        self.locator_refs: list[str] = []

    def locator(self, ref: str, has_text: str | None = None, **_: Any):
        self.locator_refs.append(ref)
        key = ref if has_text is None else f"{ref}||has_text={has_text}"
        if key in self._css_map:
            return self._css_map[key]
        if ref in self._css_map:
            return self._css_map[ref]
        if ref == "#widget":
            return self._trigger
        if ref.startswith('[id=') and self._container is not None:
            return self._container
        return _FlexLocator(name=ref)

    def get_by_role(self, role: str, name: str = "", exact: bool = False) -> _FlexLocator:
        self.get_by_role_calls.append((role, name, exact))
        return self._role_map.get((role, name, exact), _FlexLocator(name=f"role:{role}:{name}"))


def test_native_select_still_uses_select_option():
    trigger = _NativeSelectLocator()
    page = _ComboPage(trigger)
    adapter = PlaywrightAdapter(page)

    result = _run(adapter.execute(_plan("India"), _target()))

    assert result.success is True
    assert trigger.clicks == 0
    assert trigger.select_calls and trigger.select_calls[0][0][0] == "India"


def test_role_option_widget_opens_then_clicks_exact_option():
    trigger = _TriggerLocator("DIV")
    option = _FlexLocator(name="Participant", clickable=True)
    page = _ComboPage(trigger, role_map={("option", "Participant", True): option})
    adapter = PlaywrightAdapter(page)

    result = _run(adapter.execute(_plan("Participant"), _target()))

    assert result.success is True
    assert trigger.clicks == 1, "should open the dropdown before selecting"
    assert trigger.force_clicks == 0, "a plain-clickable trigger needs no force"
    assert option.clicked is True
    assert page.get_by_role_calls[0] == ("option", "Participant", True)


def test_force_opens_when_overlay_intercepts():
    # Ant Design: the inner role=combobox <input> is covered by a selection
    # <span>, so a normal click is intercepted — the adapter must force it open.
    trigger = _OverlayTriggerLocator("INPUT")
    option = _FlexLocator(name="Participant", clickable=True)
    page = _ComboPage(trigger, role_map={("option", "Participant", True): option})
    adapter = PlaywrightAdapter(page)

    result = _run(adapter.execute(_plan("Participant"), _target()))

    assert result.success is True
    assert trigger.force_clicks == 1, "overlay interception must fall back to force click"
    assert option.clicked is True


def test_role_less_ant_option_matched_by_class_and_title():
    # The real failing case: option rows are role-less
    # <div class="ant-select-item-option" title="Participant">, so role lookups
    # miss and resolution must target the option class by title.
    trigger = _OverlayTriggerLocator("INPUT", attrs={"aria-controls": "search-type-selector_list"})
    option = _FlexLocator(name="ant-option", clickable=True)
    page = _ComboPage(
        trigger,
        css_map={'.ant-select-item-option[title="Participant"]': option},
    )
    adapter = PlaywrightAdapter(page)

    result = _run(adapter.execute(_plan("Participant"), _target()))

    assert result.success is True
    assert option.clicked is True
    assert '.ant-select-item-option[title="Participant"]' in page.locator_refs


def test_role_less_option_matched_in_owned_listbox_by_text():
    # No option-class match, but the trigger owns a listbox whose rows carry the
    # text — resolution scopes to that container.
    trigger = _OverlayTriggerLocator("INPUT", attrs={"aria-owns": "type_list"})
    option = _FlexLocator(name="QR", clickable=True)
    container = _FlexLocator(name="listbox", by_text={("QR", True): option})
    page = _ComboPage(trigger, container=container)
    adapter = PlaywrightAdapter(page)

    result = _run(adapter.execute(_plan("QR"), _target()))

    assert result.success is True
    assert option.clicked is True
    assert '[id="type_list"]' in page.locator_refs


def test_no_matching_option_fails_clearly():
    trigger = _TriggerLocator("DIV")
    page = _ComboPage(trigger)  # nothing matches anywhere
    adapter = PlaywrightAdapter(page)

    result = _run(adapter.execute(_plan("Nope"), _target()))

    assert result.success is False
    assert "Nope" in (result.error or "")
