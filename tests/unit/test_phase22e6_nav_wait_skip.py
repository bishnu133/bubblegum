"""Phase 22E-6: skip the post-click wait_for_url probe for non-navigating roles.

Clicking a toggle-style control (radio / checkbox / switch / option / tab ...)
never navigates, so the cosmetic 5 s wait_for_url probe in _do_click would
always burn its full timeout. The adapter must skip the probe when the
resolved target's role is in the known non-navigating set, and keep it for
everything else (buttons, links, CSS refs with unknown role).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from bubblegum.adapters.web.playwright.adapter import (
    _NON_NAVIGATING_ROLES,
    PlaywrightAdapter,
    _target_role,
)
from bubblegum.core.schemas import ActionPlan, ExecutionOptions, ResolvedTarget


class _FakeLocator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    async def click(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("click", args, kwargs))


class _FakePage:
    """Records wait_for_url calls so tests can assert the probe was skipped."""

    def __init__(self, locator: _FakeLocator, url: str = "http://example.test/start") -> None:
        self._locator = locator
        self.url = url
        self.wait_for_url_calls = 0

    def locator(self, ref: str) -> _FakeLocator:
        return self._locator

    def get_by_role(self, role: str, name: str | None = None) -> _FakeLocator:
        return self._locator

    def get_by_text(self, text: str, exact: bool = False) -> _FakeLocator:
        return self._locator

    async def wait_for_url(self, *args: Any, **kwargs: Any) -> None:
        self.wait_for_url_calls += 1
        # No navigation occurred — the adapter's try/except swallows this.
        raise TimeoutError("no navigation")


def _run(coro):
    return asyncio.run(coro)


def _click_plan() -> ActionPlan:
    return ActionPlan(action_type="click", target_hint="x", options=ExecutionOptions())


def _execute(target: ResolvedTarget) -> tuple[_FakePage, _FakeLocator, Any]:
    locator = _FakeLocator()
    page = _FakePage(locator)
    adapter = PlaywrightAdapter(page)
    result = _run(adapter.execute(_click_plan(), target))
    return page, locator, result


# ---------------------------------------------------------------------------
# Skip path — non-navigating roles
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", sorted(_NON_NAVIGATING_ROLES))
def test_role_ref_skips_nav_wait(role: str):
    target = ResolvedTarget(
        ref=f'role={role}[name="Pick me"]', confidence=1.0, resolver_name="test"
    )

    page, locator, result = _execute(target)

    assert result.success is True
    assert [call[0] for call in locator.calls] == ["click"]
    assert page.wait_for_url_calls == 0
    assert target.metadata["nav_wait_skipped"] is True
    assert target.metadata["nav_wait_skipped_role"] == role


def test_metadata_role_skips_nav_wait_for_css_ref():
    target = ResolvedTarget(
        ref="#agree",
        confidence=1.0,
        resolver_name="test",
        metadata={"role": "checkbox"},
    )

    page, _, result = _execute(target)

    assert result.success is True
    assert page.wait_for_url_calls == 0
    assert target.metadata["nav_wait_skipped"] is True


# ---------------------------------------------------------------------------
# Probe path — navigating / unknown roles keep the wait
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ref",
    [
        'role=button[name="Submit"]',
        'role=link[name="Home"]',
        "#submit-button",
        'text="Login"',
    ],
)
def test_navigable_or_unknown_refs_keep_nav_wait(ref: str):
    target = ResolvedTarget(ref=ref, confidence=1.0, resolver_name="test")

    page, locator, result = _execute(target)

    assert result.success is True
    assert [call[0] for call in locator.calls] == ["click"]
    assert page.wait_for_url_calls == 1
    assert "nav_wait_skipped" not in target.metadata


# ---------------------------------------------------------------------------
# _target_role helper
# ---------------------------------------------------------------------------


def test_target_role_prefers_metadata_over_ref():
    target = ResolvedTarget(
        ref='role=button[name="x"]',
        confidence=1.0,
        resolver_name="test",
        metadata={"role": "Radio "},
    )
    assert _target_role(target) == "radio"


def test_target_role_parses_role_ref_with_and_without_name():
    named = ResolvedTarget(ref='role=tab[name="Details"]', confidence=1.0, resolver_name="test")
    bare = ResolvedTarget(ref="role=tab", confidence=1.0, resolver_name="test")
    assert _target_role(named) == "tab"
    assert _target_role(bare) == "tab"


def test_target_role_none_for_css_ref_and_none_target():
    css = ResolvedTarget(ref="#widget", confidence=1.0, resolver_name="test")
    assert _target_role(css) is None
    assert _target_role(None) is None
