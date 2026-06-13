from __future__ import annotations

import pytest

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter
from bubblegum.core import sdk
from bubblegum.core.config import BubblegumConfig
from bubblegum.core.planner.intent import build_options
from bubblegum.core.schemas import (
    ArtifactRef,
    ExecutionResult,
    UIContext,
    ValidationResult,
)
from bubblegum.session import BubblegumSession


# ---------------------------------------------------------------------------
# Config + options threading
# ---------------------------------------------------------------------------


def test_grounding_config_has_stability_defaults():
    g = BubblegumConfig().grounding
    assert g.stability_wait_enabled is True
    assert g.stability_quiet_ms == 400
    assert g.stability_timeout_ms == 5_000
    assert any("progressbar" in s for s in g.stability_spinner_selectors)


def test_build_options_threads_config_defaults():
    opts = build_options(
        {}, ai_enabled=True, max_cost_level="medium", memory_ttl_days=7, memory_max_failures=3,
        stability_wait_enabled=True, stability_quiet_ms=250, stability_timeout_ms=3000,
        stability_spinner_selectors=[".spin"],
    )
    assert opts.stability_wait is True
    assert opts.stability_quiet_ms == 250
    assert opts.stability_timeout_ms == 3000
    assert opts.stability_spinner_selectors == [".spin"]


def test_build_options_per_call_override_wins():
    opts = build_options(
        {"stability_wait": False, "stability_quiet_ms": 50},
        ai_enabled=True, max_cost_level="medium", memory_ttl_days=7, memory_max_failures=3,
        stability_wait_enabled=True, stability_quiet_ms=400, stability_timeout_ms=5000,
    )
    assert opts.stability_wait is False
    assert opts.stability_quiet_ms == 50


# ---------------------------------------------------------------------------
# Mobile wait_until_stable — hierarchy-dump polling
# ---------------------------------------------------------------------------


class _ConstDriver:
    capabilities = {"platformName": "Android"}
    page_source = "<hierarchy><node/></hierarchy>"


class _ChangingDriver:
    capabilities = {"platformName": "Android"}

    def __init__(self):
        self._n = 0

    @property
    def page_source(self):
        self._n += 1
        return f"<hierarchy n='{self._n}'/>"


class _RaisingDriver:
    capabilities = {"platformName": "Android"}

    @property
    def page_source(self):
        raise RuntimeError("page_source unavailable")


@pytest.mark.asyncio
async def test_mobile_wait_stable_when_hierarchy_unchanged():
    adapter = AppiumAdapter(_ConstDriver())
    diag = await adapter.wait_until_stable(quiet_ms=40, timeout_ms=1000)
    assert diag["outcome"] == "stable"
    assert diag["adapter"] == "appium"


@pytest.mark.asyncio
async def test_mobile_wait_times_out_when_hierarchy_keeps_changing():
    adapter = AppiumAdapter(_ChangingDriver())
    diag = await adapter.wait_until_stable(quiet_ms=50, timeout_ms=150)
    assert diag["outcome"] == "timeout"


@pytest.mark.asyncio
async def test_mobile_wait_reports_error_on_page_source_failure():
    adapter = AppiumAdapter(_RaisingDriver())
    diag = await adapter.wait_until_stable(quiet_ms=40, timeout_ms=500)
    assert diag["outcome"] == "error"
    assert "page_source" in diag["error"]


# ---------------------------------------------------------------------------
# Web wait_until_stable — orchestration with a fake page (no real browser)
# ---------------------------------------------------------------------------


class _FakeWebPage:
    def __init__(self, *, eval_result=None, networkidle_raises=False, eval_raises=False):
        self._eval_result = eval_result or {"stable": True, "domQuiet": True, "spinnerGone": True, "waitedMs": 120}
        self._networkidle_raises = networkidle_raises
        self._eval_raises = eval_raises
        self.load_states = []
        self.evaluated = []

    async def wait_for_load_state(self, state, timeout=None):
        self.load_states.append((state, timeout))
        if self._networkidle_raises:
            raise RuntimeError("never idle")

    async def evaluate(self, expr, arg=None):
        self.evaluated.append((expr, arg))
        if self._eval_raises:
            raise RuntimeError("evaluate failed")
        return self._eval_result


@pytest.mark.asyncio
async def test_web_wait_stable_happy_path():
    page = _FakeWebPage()
    adapter = PlaywrightAdapter(page)
    diag = await adapter.wait_until_stable(quiet_ms=400, timeout_ms=5000, spinner_selectors=[".spinner"])
    assert diag["outcome"] == "stable"
    assert diag["network_idle"] is True
    assert diag["spinner_gone"] is True
    assert page.load_states == [("networkidle", 5000)]
    # selectors are passed into the in-page probe
    assert page.evaluated[0][1]["spinnerSelectors"] == [".spinner"]


@pytest.mark.asyncio
async def test_web_wait_marks_network_not_idle_but_still_checks_dom():
    page = _FakeWebPage(networkidle_raises=True)
    adapter = PlaywrightAdapter(page)
    diag = await adapter.wait_until_stable(quiet_ms=100, timeout_ms=1000)
    assert diag["network_idle"] is False
    assert diag["outcome"] == "stable"  # DOM probe still ran and reported stable


@pytest.mark.asyncio
async def test_web_wait_reports_error_when_probe_raises():
    page = _FakeWebPage(eval_raises=True)
    adapter = PlaywrightAdapter(page)
    diag = await adapter.wait_until_stable(quiet_ms=100, timeout_ms=1000)
    assert diag["outcome"] == "error"


@pytest.mark.asyncio
async def test_web_wait_timeout_outcome():
    page = _FakeWebPage(eval_result={"stable": False, "domQuiet": False, "spinnerGone": True, "waitedMs": 5000})
    adapter = PlaywrightAdapter(page)
    diag = await adapter.wait_until_stable(quiet_ms=100, timeout_ms=500)
    assert diag["outcome"] == "timeout"


# ---------------------------------------------------------------------------
# sdk hook: stability wait runs before context collection, honors the toggle
# ---------------------------------------------------------------------------

_A11Y = "\n".join(['- button "Login"', '- textbox "Username"'])


class _OrderRecordingAdapter:
    def __init__(self, calls):
        self._calls = calls

    async def wait_until_stable(self, *, quiet_ms, timeout_ms, spinner_selectors=None):
        self._calls.append("wait_until_stable")
        return {"adapter": "fake", "outcome": "stable"}

    async def collect_context(self, _req):
        self._calls.append("collect_context")
        return UIContext(a11y_snapshot=_A11Y, screen_signature="sig")

    async def execute(self, plan, target):
        return ExecutionResult(success=True, duration_ms=1)

    async def validate(self, _plan):
        return ValidationResult(passed=True)

    async def screenshot(self):
        return ArtifactRef(type="screenshot", path="/tmp/x.png", timestamp="2026-01-01T00:00:00+00:00")


@pytest.mark.asyncio
async def test_stability_runs_before_context_on_act(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: _OrderRecordingAdapter(calls))
    s = BubblegumSession.web(object())

    await s.act("Click Login")

    assert calls.index("wait_until_stable") < calls.index("collect_context")


@pytest.mark.asyncio
async def test_stability_skipped_when_disabled(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: _OrderRecordingAdapter(calls))
    s = BubblegumSession.web(object())

    await s.act("Click Login", stability_wait=False)

    assert "wait_until_stable" not in calls
    assert "collect_context" in calls


class _NoWaitAdapter(_OrderRecordingAdapter):
    # Adapter that does NOT implement wait_until_stable.
    wait_until_stable = None


@pytest.mark.asyncio
async def test_act_works_when_adapter_lacks_wait_until_stable(monkeypatch):
    calls: list[str] = []
    adapter = _NoWaitAdapter(calls)
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)
    s = BubblegumSession.web(object())

    result = await s.act("Click Login")
    assert result.status == "passed"
    assert "wait_until_stable" not in calls
