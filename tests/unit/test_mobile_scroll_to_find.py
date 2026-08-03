"""M-A: selector-less scroll-to-find on the mobile channel.

When a plain-English step names a control that starts below the fold, grounding
finds nothing on the first screen. ``_maybe_scroll_to_target`` swipes one page,
re-collects the hierarchy, and re-grounds — up to a bounded number of times —
so the same natural-language step ("Tap Accept") resolves without a selector.

These tests drive the helper directly with a fake Appium adapter (no device,
no Appium server). Full on-device coverage lives in the env-gated
``tests/real_env/android|ios`` suites.
"""

from __future__ import annotations

import asyncio

import pytest

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core import sdk
from bubblegum.core.grounding.errors import LowConfidenceError, ResolutionFailedError
from bubblegum.core.schemas import ExecutionOptions, ResolvedTarget, StepIntent, UIContext


def _run(coro):
    return asyncio.run(coro)


_CANDIDATE_PLAN = {
    "status": "candidate",
    "scroll_needed": True,
    "scroll_direction": "down",
}


class _ScrollFakeAdapter:
    """Fake AppiumAdapter: counts swipes and serves a scroll-candidate plan.

    ``reveal_after`` is how many swipes it takes before the (monkeypatched)
    grounder should succeed — the adapter itself only records the swipe count so
    the grounder stub can decide when the target has scrolled into view.
    """

    def __init__(self, *, plan: dict | None = _CANDIDATE_PLAN) -> None:
        self.scrolls = 0
        self.collect_calls = 0
        self._plan = plan

    async def scroll_screen(self, direction: str = "down") -> dict:
        self.scrolls += 1
        return {"direction": direction}

    async def collect_context(self, request):
        self.collect_calls += 1
        app_state = {"channel": "mobile"}
        if self._plan is not None:
            app_state["scroll_discovery"] = dict(self._plan)
        return UIContext(
            hierarchy_xml=f"<hierarchy sig='{self.scrolls}'/>",
            screen_signature=f"sig-{self.scrolls}",
            app_state=app_state,
        )


def _mobile_intent(*, action_type: str = "tap", plan: dict | None = _CANDIDATE_PLAN) -> StepIntent:
    intent = StepIntent(
        instruction="Tap Accept",
        channel="mobile",
        platform="android",
        action_type=action_type,
        target_phrase="Accept",
        # 0 retries so each scroll performs exactly one grounding attempt.
        options=ExecutionOptions(resolve_retries=0, resolve_retry_interval_ms=0),
    )
    # Seed the initial app_state the way collect_context would have on the first
    # (pre-scroll) snapshot — this is what the helper reads before scrolling.
    if plan is not None:
        intent.context["app_state"] = {"scroll_discovery": dict(plan), "channel": "mobile"}
    return intent


def _found_target() -> ResolvedTarget:
    return ResolvedTarget(
        ref='{"by":"xpath","value":"//node[@text=\'Accept\']"}',
        confidence=0.92,
        resolver_name="appium_hierarchy",
    )


def _patch_ground_reveal_after(monkeypatch, adapter, reveal_after: int):
    """Grounder stub: fails until ``adapter.scrolls`` reaches ``reveal_after``."""

    async def _fake_ground(_intent):
        if adapter.scrolls >= reveal_after:
            return _found_target(), []
        raise ResolutionFailedError(step="Tap Accept", message="off-screen")

    monkeypatch.setattr(sdk._engine, "ground", _fake_ground)


def test_scroll_to_find_resolves_after_scrolls(monkeypatch):
    adapter = _ScrollFakeAdapter()
    intent = _mobile_intent()
    _patch_ground_reveal_after(monkeypatch, adapter, reveal_after=2)

    target = _run(sdk._maybe_scroll_to_target(adapter, "mobile", intent))

    assert target is not None
    assert target.resolver_name == "appium_hierarchy"
    assert adapter.scrolls == 2
    diag = target.metadata["scroll_to_find"]
    assert diag["found_after_scroll"] is True
    assert diag["attempts"] == 2
    assert diag["direction"] == "down"


def test_scroll_to_find_returns_none_when_never_found(monkeypatch):
    adapter = _ScrollFakeAdapter()
    intent = _mobile_intent()
    # reveal_after far beyond the cap → never resolves.
    _patch_ground_reveal_after(monkeypatch, adapter, reveal_after=999)

    target = _run(sdk._maybe_scroll_to_target(adapter, "mobile", intent))

    assert target is None
    # Bounded by scroll_to_find_max_scrolls (default 4).
    assert adapter.scrolls == sdk._config.grounding.scroll_to_find_max_scrolls


def test_scroll_to_find_is_noop_on_web(monkeypatch):
    adapter = _ScrollFakeAdapter()
    intent = _mobile_intent()
    _patch_ground_reveal_after(monkeypatch, adapter, reveal_after=1)

    target = _run(sdk._maybe_scroll_to_target(adapter, "web", intent))

    assert target is None
    assert adapter.scrolls == 0  # never scrolled the web channel


def test_scroll_to_find_skips_without_scrollable_plan(monkeypatch):
    # No scroll_discovery plan / not a candidate → nothing to scroll.
    adapter = _ScrollFakeAdapter(plan=None)
    intent = _mobile_intent(plan=None)
    _patch_ground_reveal_after(monkeypatch, adapter, reveal_after=1)

    target = _run(sdk._maybe_scroll_to_target(adapter, "mobile", intent))

    assert target is None
    assert adapter.scrolls == 0


def test_scroll_to_find_disabled_by_config(monkeypatch):
    adapter = _ScrollFakeAdapter()
    intent = _mobile_intent()
    _patch_ground_reveal_after(monkeypatch, adapter, reveal_after=1)
    monkeypatch.setattr(sdk._config.grounding, "scroll_to_find", False)

    target = _run(sdk._maybe_scroll_to_target(adapter, "mobile", intent))

    assert target is None
    assert adapter.scrolls == 0


def test_scroll_skipped_on_low_confidence_miss(monkeypatch):
    # An on-screen but low-confidence candidate means the target is already
    # visible — scrolling can't help and would tie up an attached Appium session.
    adapter = _ScrollFakeAdapter()
    intent = _mobile_intent()
    _patch_ground_reveal_after(monkeypatch, adapter, reveal_after=1)

    err = LowConfidenceError(step="Tap Accept", candidates=[], best_confidence=0.4)
    target = _run(sdk._maybe_scroll_to_target(adapter, "mobile", intent, err))

    assert target is None
    assert adapter.scrolls == 0  # never scrolled


def test_scroll_runs_on_resolution_failed_miss(monkeypatch):
    adapter = _ScrollFakeAdapter()
    intent = _mobile_intent()
    _patch_ground_reveal_after(monkeypatch, adapter, reveal_after=2)

    err = ResolutionFailedError(step="Tap Accept", message="nothing found")
    target = _run(sdk._maybe_scroll_to_target(adapter, "mobile", intent, err))

    assert target is not None
    assert adapter.scrolls == 2


def test_scroll_stops_when_screen_does_not_change(monkeypatch):
    # A screen whose signature never changes after a swipe = nothing left to
    # scroll → stop after the first swipe instead of burning all attempts.
    class _StaticScreenAdapter(_ScrollFakeAdapter):
        async def collect_context(self, request):
            self.collect_calls += 1
            return UIContext(
                hierarchy_xml="<hierarchy/>",
                screen_signature="constant-sig",
                app_state={"channel": "mobile", "scroll_discovery": dict(_CANDIDATE_PLAN)},
            )

    adapter = _StaticScreenAdapter()
    intent = _mobile_intent()
    intent.context["screen_signature"] = "constant-sig"
    _patch_ground_reveal_after(monkeypatch, adapter, reveal_after=999)

    err = ResolutionFailedError(step="Tap Accept", message="nothing found")
    target = _run(sdk._maybe_scroll_to_target(adapter, "mobile", intent, err))

    assert target is None
    assert adapter.scrolls == 1  # stopped after the first unchanged swipe


def test_scroll_to_find_stops_early_when_nothing_left_to_scroll(monkeypatch):
    # After the first swipe the plan flips to "unsupported" (bottom reached),
    # so the loop stops rather than swiping to the cap.
    class _BottomAdapter(_ScrollFakeAdapter):
        async def collect_context(self, request):
            self.collect_calls += 1
            status = "candidate" if self.scrolls < 1 else "unsupported"
            return UIContext(
                hierarchy_xml="<hierarchy/>",
                screen_signature=f"sig-{self.scrolls}",
                app_state={"channel": "mobile", "scroll_discovery": {"status": status}},
            )

    adapter = _BottomAdapter()
    intent = _mobile_intent()
    _patch_ground_reveal_after(monkeypatch, adapter, reveal_after=999)

    target = _run(sdk._maybe_scroll_to_target(adapter, "mobile", intent))

    assert target is None
    assert adapter.scrolls == 1  # stopped after the plan said unsupported


# ----------------------------------------------------------------------
# AppiumAdapter.scroll_screen geometry (fake driver — no Appium server)
# ----------------------------------------------------------------------


class _FakeDriver:
    def __init__(self, *, window=(1000, 2000), fail_size=False) -> None:
        self.capabilities = {"platformName": "Android"}
        self._window = window
        self._fail_size = fail_size
        self.swipes: list[tuple] = []

    def get_window_size(self):
        if self._fail_size:
            raise RuntimeError("no window size")
        return {"width": self._window[0], "height": self._window[1]}

    def swipe(self, sx, sy, ex, ey, dur):
        self.swipes.append((sx, sy, ex, ey, dur))


def test_scroll_screen_down_swipes_up_from_window_size():
    driver = _FakeDriver(window=(1000, 2000))
    adapter = AppiumAdapter(driver)

    diag = _run(adapter.scroll_screen("down"))

    assert diag["direction"] == "down"
    (sx, sy, ex, ey, _dur) = driver.swipes[-1]
    assert sx == ex == 500          # centred horizontally
    assert sy > ey                  # swipe upward reveals content below


def test_scroll_screen_up_reverses_direction():
    driver = _FakeDriver(window=(1000, 2000))
    adapter = AppiumAdapter(driver)

    _run(adapter.scroll_screen("up"))

    (sx, sy, ex, ey, _dur) = driver.swipes[-1]
    assert sy < ey                  # swipe downward reveals content above


def test_scroll_screen_falls_back_when_window_size_unavailable():
    driver = _FakeDriver(fail_size=True)
    adapter = AppiumAdapter(driver)

    diag = _run(adapter.scroll_screen("down"))

    assert diag["direction"] == "down"
    assert driver.swipes, "a swipe should still be issued using the fallback size"
