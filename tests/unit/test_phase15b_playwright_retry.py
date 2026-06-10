import asyncio

from bubblegum.adapters.web.playwright.adapter import PlaywrightAdapter
from bubblegum.core.schemas import ActionPlan, ExecutionOptions, ResolvedTarget


class _FakeLocator:
    def __init__(self, failures):
        self.failures = list(failures)
        self.calls = 0

    async def click(self, timeout):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)


class _FakePage:
    def __init__(self, locator):
        self._locator = locator
        # _do_click records the URL before clicking and probes wait_for_url to
        # detect navigation. The fake reports a static URL and a no-op
        # wait_for_url (no navigation), which the adapter swallows.
        self.url = "about:blank"

    def locator(self, ref):
        return self._locator

    async def wait_for_url(self, *args, **kwargs):
        return None


def test_playwright_transient_fail_once_then_pass_retries_once():
    locator = _FakeLocator([Exception("Timeout while waiting for element")])
    adapter = PlaywrightAdapter(_FakePage(locator))
    plan = ActionPlan(action_type="click", target_hint="x", options=ExecutionOptions(retry_count=1))
    target = ResolvedTarget(ref="#login", confidence=1.0, resolver_name="test")

    result = asyncio.run(adapter.execute(plan, target))

    assert result.success is True
    assert locator.calls == 2
    assert target.metadata["retry_attempts"] == 1
    assert target.metadata["retry_transient"] is True
    assert target.metadata["retry_adapter"] == "playwright"


def test_playwright_permanent_error_not_retried():
    locator = _FakeLocator([Exception("invalid selector syntax")])
    adapter = PlaywrightAdapter(_FakePage(locator))
    plan = ActionPlan(action_type="click", target_hint="x", options=ExecutionOptions(retry_count=1))
    target = ResolvedTarget(ref="#bad", confidence=1.0, resolver_name="test")

    result = asyncio.run(adapter.execute(plan, target))

    assert result.success is False
    assert locator.calls == 1
    assert target.metadata["retry_attempts"] == 0
    assert target.metadata["retry_transient"] is False


def test_playwright_retry_budget_capped_to_one():
    locator = _FakeLocator([
        Exception("target closed"),
        Exception("target closed"),
    ])
    adapter = PlaywrightAdapter(_FakePage(locator))
    plan = ActionPlan(action_type="click", target_hint="x", options=ExecutionOptions(retry_count=5))
    target = ResolvedTarget(ref="#login", confidence=1.0, resolver_name="test")

    result = asyncio.run(adapter.execute(plan, target))

    assert result.success is False
    assert locator.calls == 2
    assert target.metadata["retry_attempts"] == 1
