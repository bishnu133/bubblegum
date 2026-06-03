"""Phase 22D-3: Playwright adapter action dispatch table.

Verifies that PlaywrightAdapter routes each action_type to the right Playwright
locator method, with click/type behaviour unchanged from the previous
inline-if dispatch.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter
from bubblegum.core.schemas import ActionPlan, ExecutionOptions, ResolvedTarget


class _FakeLocator:
    """Captures method calls so tests can assert which Playwright method ran."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _record(self, name: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((name, args, kwargs))

    async def click(self, *args: Any, **kwargs: Any) -> None:
        self._record("click", *args, **kwargs)

    async def fill(self, *args: Any, **kwargs: Any) -> None:
        self._record("fill", *args, **kwargs)

    async def select_option(self, *args: Any, **kwargs: Any) -> None:
        self._record("select_option", *args, **kwargs)

    async def set_input_files(self, *args: Any, **kwargs: Any) -> None:
        self._record("set_input_files", *args, **kwargs)

    async def check(self, *args: Any, **kwargs: Any) -> None:
        self._record("check", *args, **kwargs)

    async def uncheck(self, *args: Any, **kwargs: Any) -> None:
        self._record("uncheck", *args, **kwargs)

    async def scroll_into_view_if_needed(self, *args: Any, **kwargs: Any) -> None:
        self._record("scroll_into_view_if_needed", *args, **kwargs)


class _FakePage:
    def __init__(self, locator: _FakeLocator, url: str = "http://example.test/start") -> None:
        self._locator = locator
        self.url = url

    def locator(self, ref: str) -> _FakeLocator:
        return self._locator

    async def wait_for_url(self, *args: Any, **kwargs: Any) -> None:
        # Default: no navigation occurred — raise so the adapter's try/except
        # swallows it, matching the in-page click behaviour.
        raise TimeoutError("no navigation")


def _run(coro):
    return asyncio.run(coro)


def _adapter_with(locator: _FakeLocator) -> tuple[PlaywrightAdapter, _FakePage]:
    page = _FakePage(locator)
    return PlaywrightAdapter(page), page


def _plan(action_type: str, input_value: str | None = None) -> ActionPlan:
    return ActionPlan(
        action_type=action_type,
        target_hint="x",
        input_value=input_value,
        options=ExecutionOptions(),
    )


def _target() -> ResolvedTarget:
    return ResolvedTarget(ref="#widget", confidence=1.0, resolver_name="test")


# ---------------------------------------------------------------------------
# Click / tap regression
# ---------------------------------------------------------------------------


def test_click_invokes_locator_click():
    locator = _FakeLocator()
    adapter, _ = _adapter_with(locator)

    result = _run(adapter.execute(_plan("click"), _target()))

    assert result.success is True
    method_names = [call[0] for call in locator.calls]
    assert method_names == ["click"]


def test_tap_is_alias_of_click():
    locator = _FakeLocator()
    adapter, _ = _adapter_with(locator)

    result = _run(adapter.execute(_plan("tap"), _target()))

    assert result.success is True
    assert [call[0] for call in locator.calls] == ["click"]


# ---------------------------------------------------------------------------
# Type regression
# ---------------------------------------------------------------------------


def test_type_invokes_locator_fill_with_value():
    locator = _FakeLocator()
    adapter, _ = _adapter_with(locator)

    result = _run(adapter.execute(_plan("type", input_value="tomsmith"), _target()))

    assert result.success is True
    assert locator.calls[0][0] == "fill"
    assert locator.calls[0][1][0] == "tomsmith"


def test_type_with_none_value_fills_empty_string():
    locator = _FakeLocator()
    adapter, _ = _adapter_with(locator)

    result = _run(adapter.execute(_plan("type", input_value=None), _target()))

    assert result.success is True
    assert locator.calls[0][0] == "fill"
    assert locator.calls[0][1][0] == ""


# ---------------------------------------------------------------------------
# Select regression
# ---------------------------------------------------------------------------


def test_select_invokes_select_option_with_value():
    locator = _FakeLocator()
    adapter, _ = _adapter_with(locator)

    result = _run(adapter.execute(_plan("select", input_value="India"), _target()))

    assert result.success is True
    assert locator.calls[0][0] == "select_option"
    assert locator.calls[0][1][0] == "India"


# ---------------------------------------------------------------------------
# Upload (new in 22D-3)
# ---------------------------------------------------------------------------


def test_upload_invokes_set_input_files_with_path():
    locator = _FakeLocator()
    adapter, _ = _adapter_with(locator)

    result = _run(adapter.execute(_plan("upload", input_value="/tmp/resume.pdf"), _target()))

    assert result.success is True
    assert locator.calls[0][0] == "set_input_files"
    assert locator.calls[0][1][0] == "/tmp/resume.pdf"


def test_upload_without_value_fails_loudly():
    locator = _FakeLocator()
    adapter, _ = _adapter_with(locator)

    result = _run(adapter.execute(_plan("upload", input_value=None), _target()))

    assert result.success is False
    assert "upload action requires input_value" in (result.error or "")
    # No file-upload call should have happened.
    assert all(call[0] != "set_input_files" for call in locator.calls)


# ---------------------------------------------------------------------------
# Check / uncheck (new in 22D-3)
# ---------------------------------------------------------------------------


def test_check_invokes_locator_check():
    locator = _FakeLocator()
    adapter, _ = _adapter_with(locator)

    result = _run(adapter.execute(_plan("check"), _target()))

    assert result.success is True
    assert [call[0] for call in locator.calls] == ["check"]


def test_uncheck_invokes_locator_uncheck():
    locator = _FakeLocator()
    adapter, _ = _adapter_with(locator)

    result = _run(adapter.execute(_plan("uncheck"), _target()))

    assert result.success is True
    assert [call[0] for call in locator.calls] == ["uncheck"]


# ---------------------------------------------------------------------------
# Scroll regression
# ---------------------------------------------------------------------------


def test_scroll_invokes_scroll_into_view_if_needed():
    locator = _FakeLocator()
    adapter, _ = _adapter_with(locator)

    result = _run(adapter.execute(_plan("scroll"), _target()))

    assert result.success is True
    assert [call[0] for call in locator.calls] == ["scroll_into_view_if_needed"]


# ---------------------------------------------------------------------------
# Dispatch table closure
# ---------------------------------------------------------------------------


def test_dispatch_table_covers_expected_action_types():
    from bubblegum.adapters.web.playwright.adapter import _ACTION_DISPATCH

    expected = {"click", "tap", "type", "select", "upload", "check", "uncheck", "scroll"}
    assert set(_ACTION_DISPATCH.keys()) == expected
