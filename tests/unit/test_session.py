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
# Soft assertions (W3)
# ---------------------------------------------------------------------------


class FailVerifyAdapter(FakeAdapter):
    """Grounds targets normally but every assertion fails."""

    async def validate(self, _plan):
        return ValidationResult(passed=False, actual_value="nope")


@pytest.mark.asyncio
async def test_soft_verify_does_not_raise_and_is_tagged(monkeypatch):
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: FailVerifyAdapter())
    s = BubblegumSession.web(object())

    result = await s.verify("Dashboard visible", soft=True)

    assert result.status == "failed"
    assert s.soft_failures() == [result]
    # Tag flows into target metadata for report surfaces.
    assert result.target is not None
    assert result.target.metadata.get("soft") is True


@pytest.mark.asyncio
async def test_soft_assertions_block_collects_all_failures(monkeypatch):
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: FailVerifyAdapter())
    s = BubblegumSession.web(object())

    with s.soft_assertions():
        await s.verify("Login visible")
        await s.verify("Username visible")
        await s.verify("Dashboard visible")

    # All three failures recorded, nothing raised mid-block.
    assert len(s.results()) == 3
    assert all(r.status == "failed" for r in s.results())
    assert len(s.soft_failures()) == 3

    with pytest.raises(AssertionError) as exc:
        s.assert_all_passed()
    message = str(exc.value)
    assert "3 step(s) failed (3 soft)" in message
    assert message.count("[soft]") == 3


@pytest.mark.asyncio
async def test_soft_default_restored_after_block(monkeypatch):
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: FailVerifyAdapter())
    s = BubblegumSession.web(object())

    with s.soft_assertions():
        await s.verify("Login visible")
    # Outside the block, verifies are hard again (not tracked as soft).
    await s.verify("Username visible")

    assert len(s.soft_failures()) == 1


@pytest.mark.asyncio
async def test_per_call_soft_false_overrides_block(monkeypatch):
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: FailVerifyAdapter())
    s = BubblegumSession.web(object())

    with s.soft_assertions():
        await s.verify("Login visible")              # soft (inherits block)
        await s.verify("Username visible", soft=False)  # explicit hard override

    assert len(s.soft_failures()) == 1


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
