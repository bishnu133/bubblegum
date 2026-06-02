"""Unit tests for BubblegumSession."""

from __future__ import annotations

import pytest

from bubblegum.session import BubblegumSession
from bubblegum.core import sdk
from bubblegum.core.schemas import ArtifactRef, ExecutionResult, StepResult, UIContext, ValidationResult, ErrorInfo

_A11Y = "\n".join(["- button \"Login\"", "- textbox \"Username\"", "- heading \"Dashboard\""])


class FakeAdapter:
    async def collect_context(self, _req):
        return UIContext(a11y_snapshot=_A11Y, screen_signature="sig")

    async def execute(self, plan, target):
        return ExecutionResult(success=True, duration_ms=1)

    async def validate(self, _plan):
        return ValidationResult(passed=True)

    async def screenshot(self):
        return ArtifactRef(type="screenshot", path="/tmp/x.png", timestamp="2026-01-01T00:00:00+00:00")


class FailAdapter(FakeAdapter):
    async def execute(self, plan, target):
        return ExecutionResult(success=False, duration_ms=1, error="boom")


# ---------------------------------------------------------------------------
# Factory methods
# ---------------------------------------------------------------------------

def test_web_factory_sets_channel():
    page = object()
    s = BubblegumSession.web(page)
    assert s._channel == "web"
    assert s._page is page


def test_mobile_factory_sets_channel():
    driver = object()
    s = BubblegumSession.mobile(driver)
    assert s._channel == "mobile"
    assert s._driver is driver


def test_web_requires_page():
    with pytest.raises(ValueError, match="page"):
        BubblegumSession(channel="web")


def test_mobile_requires_driver():
    with pytest.raises(ValueError, match="driver"):
        BubblegumSession(channel="mobile")


# ---------------------------------------------------------------------------
# act / verify / extract accumulate results
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_accumulates_results(monkeypatch):
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: FakeAdapter())
    s = BubblegumSession.web(object())

    await s.act("Click Login")
    await s.act('Enter "x" into Username')
    await s.verify("Dashboard visible")

    assert len(s.results()) == 3
    assert all(r.status == "passed" for r in s.results())


@pytest.mark.asyncio
async def test_summary_counts(monkeypatch):
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: FakeAdapter())
    s = BubblegumSession.web(object())

    await s.act("Click Login")
    await s.act("Click Login")

    summ = s.summary()
    assert summ["total"] == 2
    assert summ["passed"] == 2
    assert summ["failed"] == 0


# ---------------------------------------------------------------------------
# assert_all_passed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_assert_all_passed_passes_when_no_failures(monkeypatch):
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: FakeAdapter())
    s = BubblegumSession.web(object())
    await s.act("Click Login")
    s.assert_all_passed()  # should not raise


@pytest.mark.asyncio
async def test_assert_all_passed_raises_on_failure(monkeypatch):
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: FailAdapter())
    s = BubblegumSession.web(object())
    await s.act("Click Login")
    with pytest.raises(AssertionError, match="1 step"):
        s.assert_all_passed()


# ---------------------------------------------------------------------------
# dry_run session-level flag
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_dry_run_propagates(monkeypatch):
    adapter = FakeAdapter()
    execute_called = []

    original_execute = adapter.execute
    async def tracking_execute(plan, target):
        execute_called.append(True)
        return await original_execute(plan, target)
    adapter.execute = tracking_execute

    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)
    s = BubblegumSession.web(object(), dry_run=True)
    result = await s.act("Click Login")

    assert result.status == "dry_run"
    assert execute_called == []


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_context_manager(monkeypatch):
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: FakeAdapter())
    async with BubblegumSession.web(object()) as s:
        await s.act("Click Login")
    assert len(s.results()) == 1
