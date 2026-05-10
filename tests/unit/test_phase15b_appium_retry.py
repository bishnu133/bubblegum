import asyncio

from bubblegum.adapters.mobile.appium.adapter import AppiumAdapter
from bubblegum.core.schemas import ActionPlan, ExecutionOptions, ResolvedTarget


class _FakeElement:
    def click(self):
        return None


class _FakeDriver:
    capabilities = {"platformName": "Android"}


def test_appium_transient_fail_once_then_pass_retries_once(monkeypatch):
    adapter = AppiumAdapter(_FakeDriver())
    calls = {"n": 0}

    def fake_find(ref):
        calls["n"] += 1
        if calls["n"] == 1:
            raise Exception("stale element reference")
        return _FakeElement()

    monkeypatch.setattr(adapter, "_find_element", fake_find)

    plan = ActionPlan(action_type="click", target_hint="x", options=ExecutionOptions(retry_count=1))
    target = ResolvedTarget(ref='{"by":"xpath","value":"//x"}', confidence=1.0, resolver_name="test")

    result = asyncio.run(adapter.execute(plan, target))

    assert result.success is True
    assert calls["n"] == 2
    assert target.metadata["retry_attempts"] == 1
    assert target.metadata["retry_transient"] is True
    assert target.metadata["retry_adapter"] == "appium"


def test_appium_permanent_error_not_retried(monkeypatch):
    adapter = AppiumAdapter(_FakeDriver())
    calls = {"n": 0}

    def fake_find(ref):
        calls["n"] += 1
        raise Exception("invalid selector strategy")

    monkeypatch.setattr(adapter, "_find_element", fake_find)

    plan = ActionPlan(action_type="click", target_hint="x", options=ExecutionOptions(retry_count=1))
    target = ResolvedTarget(ref='{"by":"xpath","value":"//x"}', confidence=1.0, resolver_name="test")

    result = asyncio.run(adapter.execute(plan, target))

    assert result.success is False
    assert calls["n"] == 1
    assert target.metadata["retry_attempts"] == 0
    assert target.metadata["retry_transient"] is False


def test_appium_retry_budget_capped_to_one(monkeypatch):
    adapter = AppiumAdapter(_FakeDriver())
    calls = {"n": 0}

    def fake_find(ref):
        calls["n"] += 1
        raise Exception("no such element")

    monkeypatch.setattr(adapter, "_find_element", fake_find)

    plan = ActionPlan(action_type="click", target_hint="x", options=ExecutionOptions(retry_count=10))
    target = ResolvedTarget(ref='{"by":"xpath","value":"//x"}', confidence=1.0, resolver_name="test")

    result = asyncio.run(adapter.execute(plan, target))

    assert result.success is False
    assert calls["n"] == 2
    assert target.metadata["retry_attempts"] == 1
