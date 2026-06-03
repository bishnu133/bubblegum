"""Unit tests for dry_run=True mode."""

from __future__ import annotations

import pytest

from bubblegum.core import sdk
from bubblegum.core.schemas import ArtifactRef, ExecutionResult, UIContext, ValidationResult

_A11Y = "\n".join(["- button \"Login\"", "- textbox \"Username\""])


class FakeAdapter:
    def __init__(self):
        self.execute_called = False

    async def collect_context(self, _req):
        return UIContext(a11y_snapshot=_A11Y, screen_signature="sig")

    async def execute(self, plan, target):
        self.execute_called = True
        return ExecutionResult(success=True, duration_ms=1)

    async def validate(self, _plan):
        return ValidationResult(passed=True)

    async def screenshot(self):
        return ArtifactRef(type="screenshot", path="/tmp/x.png", timestamp="2026-01-01T00:00:00Z")


@pytest.mark.asyncio
async def test_dry_run_does_not_call_execute(monkeypatch):
    adapter = FakeAdapter()
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)

    result = await sdk.act("Click Login", channel="web", page=object(), dry_run=True)

    assert result.status == "dry_run"
    assert adapter.execute_called is False


@pytest.mark.asyncio
async def test_dry_run_resolves_target(monkeypatch):
    adapter = FakeAdapter()
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)

    result = await sdk.act("Click Login", channel="web", page=object(), dry_run=True)

    assert result.target is not None
    assert "Login" in result.target.ref
    assert result.confidence > 0


@pytest.mark.asyncio
async def test_dry_run_produces_no_screenshot_artifacts(monkeypatch):
    adapter = FakeAdapter()
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)

    result = await sdk.act("Click Login", channel="web", page=object(), dry_run=True)

    assert result.artifacts == []


@pytest.mark.asyncio
async def test_normal_run_calls_execute(monkeypatch):
    adapter = FakeAdapter()
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)

    result = await sdk.act("Click Login", channel="web", page=object())

    assert result.status == "passed"
    assert adapter.execute_called is True
