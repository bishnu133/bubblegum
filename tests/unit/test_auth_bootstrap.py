from __future__ import annotations

import pytest

from bubblegum.core import sdk
from bubblegum.core.schemas import ArtifactRef, ExecutionResult, UIContext, ValidationResult
from bubblegum.session import BubblegumSession


_A11Y = "\n".join(['- button "Login"', '- textbox "Username"'])


class _FakeAdapter:
    def __init__(self, calls=None):
        self._calls = calls if calls is not None else []

    async def collect_context(self, _req):
        self._calls.append("collect_context")
        return UIContext(a11y_snapshot=_A11Y, screen_signature="sig")

    async def execute(self, plan, target):
        return ExecutionResult(success=True, duration_ms=1)

    async def validate(self, _plan):
        return ValidationResult(passed=True)

    async def screenshot(self):
        return ArtifactRef(type="screenshot", path="/tmp/x.png", timestamp="2026-01-01T00:00:00+00:00")


# ---------------------------------------------------------------------------
# bootstrap runs on entry, receives the handle, is idempotent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_bootstrap_runs_once_with_page_handle():
    page = object()
    seen = []

    async def boot(handle):
        seen.append(handle)

    async with BubblegumSession.web(page, bootstrap=boot) as s:
        assert s._bootstrapped is True

    assert seen == [page]  # called exactly once, with the wrapped page


@pytest.mark.asyncio
async def test_sync_bootstrap_supported():
    page = object()
    seen = []

    def boot(handle):  # plain sync callable
        seen.append(handle)

    async with BubblegumSession.web(page, bootstrap=boot):
        pass

    assert seen == [page]


@pytest.mark.asyncio
async def test_mobile_bootstrap_receives_driver():
    driver = object()
    seen = []

    async def boot(handle):
        seen.append(handle)

    async with BubblegumSession.mobile(driver, bootstrap=boot):
        pass

    assert seen == [driver]


@pytest.mark.asyncio
async def test_bootstrap_is_idempotent():
    page = object()
    count = {"n": 0}

    async def boot(_handle):
        count["n"] += 1

    s = BubblegumSession.web(page, bootstrap=boot)
    await s._run_bootstrap()
    await s._run_bootstrap()
    async with s:  # __aenter__ calls it again
        pass
    assert count["n"] == 1


@pytest.mark.asyncio
async def test_no_bootstrap_is_a_noop():
    async with BubblegumSession.web(object()) as s:
        assert s._bootstrapped is False  # nothing to run


# ---------------------------------------------------------------------------
# ordering + error propagation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bootstrap_runs_before_first_step(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: _FakeAdapter(calls))

    async def boot(_handle):
        calls.append("bootstrap")

    async with BubblegumSession.web(object(), bootstrap=boot) as s:
        await s.act("Click Login")

    assert calls[0] == "bootstrap"
    assert "collect_context" in calls
    assert calls.index("bootstrap") < calls.index("collect_context")


@pytest.mark.asyncio
async def test_bootstrap_error_propagates():
    async def boot(_handle):
        raise RuntimeError("login API down")

    with pytest.raises(RuntimeError, match="login API down"):
        async with BubblegumSession.web(object(), bootstrap=boot):
            pass
