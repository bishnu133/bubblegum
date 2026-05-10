import asyncio

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.schemas import ActionPlan, ExecutionOptions, ResolvedTarget


class _FakeElement:
    def __init__(self, displayed=True):
        self._displayed = displayed
        self.click_calls = 0

    def is_displayed(self):
        return self._displayed

    def click(self):
        self.click_calls += 1


class _FakeDriver:
    capabilities = {"platformName": "Android"}


def _run(monkeypatch, wait_for=None, retry_count=0, first_error=None, displayed=True, timeout_ms=500):
    adapter = AppiumAdapter(_FakeDriver())
    calls = {"n": 0}
    element = _FakeElement(displayed=displayed)

    def fake_find(ref):
        calls["n"] += 1
        if first_error and calls["n"] == 1:
            raise first_error
        return element

    monkeypatch.setattr(adapter, "_find_element", fake_find)
    plan = ActionPlan(
        action_type="click",
        target_hint="x",
        options=ExecutionOptions(retry_count=retry_count, wait_for=wait_for, timeout_ms=timeout_ms),
    )
    target = ResolvedTarget(ref='{"by":"xpath","value":"//x"}', confidence=1.0, resolver_name="test")
    result = asyncio.run(adapter.execute(plan, target))
    return result, calls, target


def test_wait_present_success(monkeypatch):
    result, calls, _ = _run(monkeypatch, wait_for="present")
    assert result.success is True
    assert calls["n"] == 1


def test_wait_visible_success(monkeypatch):
    result, calls, _ = _run(monkeypatch, wait_for="visible", displayed=True)
    assert result.success is True
    assert calls["n"] == 1


def test_no_wait_for_preserves_existing_path(monkeypatch):
    result, calls, _ = _run(monkeypatch, wait_for=None)
    assert result.success is True
    assert calls["n"] == 1


def test_unsupported_wait_mode_fails_clearly(monkeypatch):
    result, _, _ = _run(monkeypatch, wait_for="enabled")
    assert result.success is False
    assert "Unsupported wait_for mode for Appium" in (result.error or "")


def test_retry_behavior_still_works_with_wait(monkeypatch):
    result, calls, target = _run(
        monkeypatch,
        wait_for="present",
        retry_count=1,
        first_error=Exception("no such element"),
    )
    assert result.success is True
    assert calls["n"] == 2
    assert target.metadata["retry_attempts"] == 1


def test_wait_visible_timeout_uses_timeout_ms(monkeypatch):
    adapter = AppiumAdapter(_FakeDriver())
    element = _FakeElement(displayed=False)
    monkeypatch.setattr(adapter, "_find_element", lambda ref: element)

    plan = ActionPlan(
        action_type="click",
        target_hint="x",
        options=ExecutionOptions(wait_for="visible", timeout_ms=0),
    )
    target = ResolvedTarget(ref='{"by":"xpath","value":"//x"}', confidence=1.0, resolver_name="test")

    result = asyncio.run(adapter.execute(plan, target))
    assert result.success is False
    assert "Element not visible" in (result.error or "")
