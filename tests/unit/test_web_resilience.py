"""Web resilience improvements (async PlaywrightAdapter + SDK re-ground).

Covers, with browser-free fakes (same approach as test_phase22e6_nav_wait_skip):

  1. Bounded, configurable post-click navigation wait (nav_wait_ms) — and the
     two-phase "detect commit, then wait for load" behaviour.
  2. <select> label fallback when the visible option differs from its value.
  3. Strict-mode retry: an action against a multi-match ref retries on .first
     instead of failing the step.
  4. iframe support: merged frame snapshots in collect_context, and execution /
     extraction routing into the owning child frame.
  5. SDK re-grounding: act() re-collects context and retries when the first
     resolution finds nothing (late-rendered SPA elements).
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter
from bubblegum.core.grounding.errors import ResolutionFailedError
from bubblegum.core.schemas import (
    ActionPlan,
    ContextRequest,
    ExecutionOptions,
    ResolvedTarget,
    StepIntent,
)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeLocator:
    """Configurable async locator stub recording the calls made against it."""

    def __init__(
        self,
        *,
        count: int = 1,
        strict_on_click: bool = False,
        select_value_fails: bool = False,
        inner_text: str = "",
    ) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.select_calls: list[dict[str, Any]] = []
        self._count = count
        self._strict_on_click = strict_on_click
        self._select_value_fails = select_value_fails
        self._inner_text = inner_text
        self._first: _FakeLocator | None = None

    @property
    def first(self) -> "_FakeLocator":
        if self._first is None:
            self._first = _FakeLocator(count=1, inner_text=self._inner_text)
        return self._first

    async def click(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("click", args, kwargs))
        if self._strict_on_click:
            raise Exception("Error: strict mode violation: locator resolved to 2 elements")

    async def fill(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("fill", args, kwargs))

    async def select_option(self, *args: Any, **kwargs: Any) -> None:
        self.select_calls.append({"args": args, "kwargs": kwargs})
        if "label" not in kwargs and self._select_value_fails:
            raise Exception("did not find option matching the value")

    async def wait_for(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("wait_for", args, kwargs))

    async def scroll_into_view_if_needed(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("scroll", args, kwargs))

    async def count(self) -> int:
        return self._count

    async def inner_text(self, *args: Any, **kwargs: Any) -> str:
        return self._inner_text


class _FakePage:
    """Frameless page. Records wait_for_url / wait_for_load_state calls."""

    def __init__(self, locator: _FakeLocator, *, navigates: bool = False,
                 url: str = "http://example.test/start") -> None:
        self._locator = locator
        self.url = url
        self._navigates = navigates
        self.wait_for_url_calls: list[dict[str, Any]] = []
        self.load_state_calls: list[dict[str, Any]] = []

    def locator(self, ref: str) -> _FakeLocator:
        return self._locator

    def get_by_role(self, role: str, name: str | None = None) -> _FakeLocator:
        return self._locator

    def get_by_text(self, text: str, exact: bool = False) -> _FakeLocator:
        return self._locator

    async def wait_for_url(self, predicate, *, wait_until=None, timeout=None) -> None:
        self.wait_for_url_calls.append({"wait_until": wait_until, "timeout": timeout})
        if not self._navigates:
            raise TimeoutError("no navigation")
        self.url = "http://example.test/next"

    async def wait_for_load_state(self, state=None, *, timeout=None) -> None:
        self.load_state_calls.append({"state": state, "timeout": timeout})


class _FakeFrame:
    def __init__(self, locator: _FakeLocator, *, body_snapshot: str = "") -> None:
        self._locator = locator
        self._body = _FakeLocator(inner_text=body_snapshot)
        self._body_snapshot = body_snapshot

    def locator(self, ref: str):
        if ref == "body":
            class _Body:
                def __init__(self, snap: str) -> None:
                    self._snap = snap

                async def aria_snapshot(self) -> str:
                    return self._snap

            return _Body(self._body_snapshot)
        return self._locator

    def get_by_role(self, role: str, name: str | None = None) -> _FakeLocator:
        return self._locator

    def get_by_text(self, text: str, exact: bool = False) -> _FakeLocator:
        return self._locator


class _FakeFramePage:
    """Page with one child frame. Main-frame matches are configurable."""

    def __init__(self, main_locator: _FakeLocator, child_frame: _FakeFrame,
                 *, main_body_snapshot: str = "") -> None:
        self._main_locator = main_locator
        self.main_frame = object()
        self._child = child_frame
        self.frames = [self.main_frame, child_frame]
        self.url = "http://example.test/"
        self._main_body_snapshot = main_body_snapshot

    def locator(self, ref: str):
        if ref == "body":
            class _Body:
                def __init__(self, snap: str) -> None:
                    self._snap = snap

                async def aria_snapshot(self) -> str:
                    return self._snap

            return _Body(self._main_body_snapshot)
        return self._main_locator

    def get_by_role(self, role: str, name: str | None = None) -> _FakeLocator:
        return self._main_locator

    def get_by_text(self, text: str, exact: bool = False) -> _FakeLocator:
        return self._main_locator


def _click_plan(**opt) -> ActionPlan:
    return ActionPlan(action_type="click", target_hint="x", options=ExecutionOptions(**opt))


# ---------------------------------------------------------------------------
# 1. Bounded, configurable navigation wait
# ---------------------------------------------------------------------------


def test_nav_wait_uses_configured_timeout_and_skips_load_state_when_no_nav():
    locator = _FakeLocator()
    page = _FakePage(locator, navigates=False)
    adapter = PlaywrightAdapter(page)
    target = ResolvedTarget(ref='role=button[name="Add"]', confidence=1.0, resolver_name="t")

    result = _run(adapter.execute(_click_plan(nav_wait_ms=1500), target))

    assert result.success is True
    assert len(page.wait_for_url_calls) == 1
    assert page.wait_for_url_calls[0]["timeout"] == 1500
    assert page.wait_for_url_calls[0]["wait_until"] == "commit"
    # No navigation committed → the load-state settle phase is skipped.
    assert page.load_state_calls == []


def test_nav_wait_waits_for_load_state_when_navigation_commits():
    locator = _FakeLocator()
    page = _FakePage(locator, navigates=True)
    adapter = PlaywrightAdapter(page)
    target = ResolvedTarget(ref='role=button[name="Login"]', confidence=1.0, resolver_name="t")

    result = _run(adapter.execute(_click_plan(timeout_ms=9000), target))

    assert result.success is True
    assert len(page.wait_for_url_calls) == 1
    # Phase 2 ran with the full action timeout.
    assert page.load_state_calls == [{"state": "domcontentloaded", "timeout": 9000}]


def test_nav_wait_zero_skips_probe_entirely():
    locator = _FakeLocator()
    page = _FakePage(locator, navigates=False)
    adapter = PlaywrightAdapter(page)
    target = ResolvedTarget(ref='role=button[name="Save"]', confidence=1.0, resolver_name="t")

    result = _run(adapter.execute(_click_plan(nav_wait_ms=0), target))

    assert result.success is True
    assert page.wait_for_url_calls == []


# ---------------------------------------------------------------------------
# 2. <select> label fallback
# ---------------------------------------------------------------------------


def test_select_falls_back_to_label_when_value_match_fails():
    locator = _FakeLocator(select_value_fails=True)
    page = _FakePage(locator)
    adapter = PlaywrightAdapter(page)
    plan = ActionPlan(action_type="select", target_hint="Country", input_value="France",
                      options=ExecutionOptions())
    target = ResolvedTarget(ref="#country", confidence=1.0, resolver_name="t")

    result = _run(adapter.execute(plan, target))

    assert result.success is True
    # First attempt by value (positional), second by label.
    assert locator.select_calls[0]["args"] == ("France",)
    assert locator.select_calls[1]["kwargs"].get("label") == "France"


def test_select_uses_value_directly_when_it_matches():
    locator = _FakeLocator(select_value_fails=False)
    page = _FakePage(locator)
    adapter = PlaywrightAdapter(page)
    plan = ActionPlan(action_type="select", target_hint="Country", input_value="FR",
                      options=ExecutionOptions())
    target = ResolvedTarget(ref="#country", confidence=1.0, resolver_name="t")

    result = _run(adapter.execute(plan, target))

    assert result.success is True
    assert len(locator.select_calls) == 1
    assert locator.select_calls[0]["args"] == ("FR",)


# ---------------------------------------------------------------------------
# 3. Strict-mode retry on .first
# ---------------------------------------------------------------------------


def test_strict_mode_violation_retries_on_first_match():
    locator = _FakeLocator(strict_on_click=True)
    page = _FakePage(locator, navigates=False)
    adapter = PlaywrightAdapter(page)
    target = ResolvedTarget(ref='text="Login"', confidence=1.0, resolver_name="t")

    result = _run(adapter.execute(_click_plan(), target))

    assert result.success is True
    # The original locator raised; the retry happened on .first (which clicked).
    assert ("click", (), {"timeout": 10_000}) in locator.calls
    assert locator.first.calls and locator.first.calls[0][0] == "click"
    assert target.metadata.get("strict_mode_fallback_first") is True


# ---------------------------------------------------------------------------
# 4. iframe support
# ---------------------------------------------------------------------------


def test_collect_context_merges_child_frame_snapshots():
    main_locator = _FakeLocator()
    child = _FakeFrame(_FakeLocator(), body_snapshot='- button "Pay"')
    page = _FakeFramePage(main_locator, child, main_body_snapshot='- heading "Checkout"')
    adapter = PlaywrightAdapter(page)

    ctx = _run(adapter.collect_context(ContextRequest(include_screenshot=False)))

    assert "Checkout" in ctx.a11y_snapshot
    assert 'button "Pay"' in ctx.a11y_snapshot


def test_collect_context_skips_frames_when_disabled():
    main_locator = _FakeLocator()
    child = _FakeFrame(_FakeLocator(), body_snapshot='- button "Pay"')
    page = _FakeFramePage(main_locator, child, main_body_snapshot='- heading "Checkout"')
    adapter = PlaywrightAdapter(page)

    ctx = _run(adapter.collect_context(
        ContextRequest(include_screenshot=False, include_frames=False)
    ))

    assert "Checkout" in ctx.a11y_snapshot
    assert "Pay" not in ctx.a11y_snapshot


def test_execution_routes_into_child_frame_when_main_has_no_match():
    # Main frame matches nothing (count=0); child frame has the element.
    main_locator = _FakeLocator(count=0)
    child_locator = _FakeLocator(count=1)
    child = _FakeFrame(child_locator)
    page = _FakeFramePage(main_locator, child)
    adapter = PlaywrightAdapter(page)
    target = ResolvedTarget(ref='role=button[name="Pay"]', confidence=1.0, resolver_name="t")

    result = _run(adapter.execute(_click_plan(nav_wait_ms=0), target))

    assert result.success is True
    # The click landed on the child-frame locator, not the empty main one.
    assert any(c[0] == "click" for c in child_locator.calls)
    assert main_locator.calls == []


def test_extract_text_reads_from_child_frame():
    main_locator = _FakeLocator(count=0)
    child_locator = _FakeLocator(count=1, inner_text="$42.00")
    child = _FakeFrame(child_locator)
    page = _FakeFramePage(main_locator, child)
    adapter = PlaywrightAdapter(page)

    value = _run(adapter.extract_text('role=heading[name="Total"]'))
    assert value == "$42.00"


# ---------------------------------------------------------------------------
# 5. SDK re-grounding for late-rendered elements
# ---------------------------------------------------------------------------


def test_ground_with_wait_retries_and_recollects_context(monkeypatch):
    from bubblegum.core import sdk

    class _Adapter:
        def __init__(self) -> None:
            self.collect_calls = 0

        async def collect_context(self, request):
            self.collect_calls += 1
            from bubblegum.core.schemas import UIContext
            return UIContext(a11y_snapshot='- button "Later"', screen_signature="sig")

    adapter = _Adapter()
    intent = StepIntent(
        instruction="Click Later",
        channel="web",
        platform="web",
        action_type="click",
        options=ExecutionOptions(resolve_retries=2, resolve_retry_interval_ms=0),
    )

    attempts = {"n": 0}
    sentinel = (ResolvedTarget(ref="#later", confidence=0.95, resolver_name="t"), [])

    async def _fake_ground(_intent):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise ResolutionFailedError(step="Click Later", message="not yet")
        return sentinel

    monkeypatch.setattr(sdk._engine, "ground", _fake_ground)

    target, _traces = _run(sdk._ground_with_wait(adapter, intent))

    assert target.ref == "#later"
    assert attempts["n"] == 2
    # Context was re-collected before the successful second attempt.
    assert adapter.collect_calls == 1


def test_ground_with_wait_reraises_after_exhausting_retries(monkeypatch):
    from bubblegum.core import sdk

    class _Adapter:
        async def collect_context(self, request):
            from bubblegum.core.schemas import UIContext
            return UIContext(a11y_snapshot="", screen_signature="sig")

    intent = StepIntent(
        instruction="Click Ghost",
        channel="web",
        platform="web",
        action_type="click",
        options=ExecutionOptions(resolve_retries=1, resolve_retry_interval_ms=0),
    )

    async def _always_fail(_intent):
        raise ResolutionFailedError(step="Click Ghost", message="never")

    monkeypatch.setattr(sdk._engine, "ground", _always_fail)

    with pytest.raises(ResolutionFailedError):
        _run(sdk._ground_with_wait(_Adapter(), intent))
