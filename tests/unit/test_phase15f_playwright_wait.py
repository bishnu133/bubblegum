import asyncio

from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter
from bubblegum.core.schemas import ActionPlan, ExecutionOptions, ResolvedTarget


class _FakeHandle:
    def __init__(self, enabled=True):
        self._enabled = enabled

    async def is_enabled(self):
        return self._enabled


class _FakeLocator:
    def __init__(self, failures=None, enabled=True):
        self.failures = list(failures or [])
        self.calls = 0
        self.wait_calls = []
        self.handle = _FakeHandle(enabled=enabled)

    async def wait_for(self, state, timeout):
        self.wait_calls.append((state, timeout))

    async def element_handle(self, timeout):
        self.wait_calls.append(("element_handle", timeout))
        return self.handle

    async def click(self, timeout):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)


class _FakePage:
    def __init__(self, locator):
        self._locator = locator

    def locator(self, ref):
        return self._locator


def _run(wait_for=None, retry_count=0, failures=None, enabled=True):
    locator = _FakeLocator(failures=failures, enabled=enabled)
    adapter = PlaywrightAdapter(_FakePage(locator))
    plan = ActionPlan(
        action_type="click",
        target_hint="x",
        options=ExecutionOptions(retry_count=retry_count, wait_for=wait_for, timeout_ms=1234),
    )
    target = ResolvedTarget(ref="#login", confidence=1.0, resolver_name="test")
    result = asyncio.run(adapter.execute(plan, target))
    return result, locator, target


def test_wait_visible_success():
    result, locator, target = _run(wait_for="visible")
    assert result.success is True
    assert ("visible", 1234) in locator.wait_calls
    assert target.metadata["wait_used"] is True
    assert target.metadata["wait_mode"] == "visible"
    assert target.metadata["wait_outcome"] == "success"
    assert target.metadata["wait_adapter"] == "playwright"


def test_wait_attached_success():
    result, locator, _ = _run(wait_for="attached")
    assert result.success is True
    assert ("attached", 1234) in locator.wait_calls


def test_wait_enabled_success():
    result, locator, _ = _run(wait_for="enabled")
    assert result.success is True
    assert ("attached", 1234) in locator.wait_calls
    assert ("element_handle", 1234) in locator.wait_calls


def test_no_wait_for_preserves_existing_path():
    result, locator, target = _run(wait_for=None)
    assert result.success is True
    assert locator.calls == 1
    assert locator.wait_calls == []
    assert "wait_used" not in target.metadata


def test_unsupported_wait_mode_fails_clearly():
    result, _, target = _run(wait_for="hidden")
    assert result.success is False
    assert "Unsupported wait_for mode for Playwright" in (result.error or "")
    assert target.metadata["wait_outcome"] == "failed"


def test_retry_behavior_still_works_with_wait():
    result, locator, target = _run(
        wait_for="visible",
        retry_count=1,
        failures=[Exception("Timeout while waiting for element")],
    )
    assert result.success is True
    assert locator.calls == 2
    assert target.metadata["retry_attempts"] == 1


def test_unsupported_action_type_does_not_succeed_silently():
    locator = _FakeLocator()
    adapter = PlaywrightAdapter(_FakePage(locator))
    plan = ActionPlan(
        action_type="verify",
        target_hint="x",
        options=ExecutionOptions(timeout_ms=1234),
    )
    target = ResolvedTarget(ref="#login", confidence=1.0, resolver_name="test")
    result = asyncio.run(adapter.execute(plan, target))
    assert result.success is False
    assert "Unsupported action_type for Playwright execute" in (result.error or "")
