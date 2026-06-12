"""The SDK re-grounding loop is channel-agnostic — it benefits mobile too.

When the first resolution finds nothing (an element not yet in the Appium
hierarchy), act()/verify()/extract() re-collect context from the mobile adapter
and retry. This proves that mechanism on the mobile channel with a fake Appium
adapter (no device required). Full on-device e2e runs via the env-gated
tests/real_env/android|ios suites.
"""

from __future__ import annotations

import asyncio

import pytest

from bubblegum.core import sdk
from bubblegum.core.grounding.errors import ResolutionFailedError
from bubblegum.core.schemas import ExecutionOptions, ResolvedTarget, StepIntent, UIContext


def _run(coro):
    return asyncio.run(coro)


class _FakeMobileAdapter:
    """Stand-in for AppiumAdapter: serves an empty hierarchy first, then one
    containing the target (as if the screen finished rendering)."""

    def __init__(self) -> None:
        self.collect_calls = 0
        # By the time the SDK re-collects (on retry), the screen has rendered.
        self._rendered = '<hierarchy><node text="Continue"/></hierarchy>'

    async def collect_context(self, request):
        self.collect_calls += 1
        return UIContext(hierarchy_xml=self._rendered, screen_signature="m-sig")


def _mobile_intent() -> StepIntent:
    return StepIntent(
        instruction="Tap Continue",
        channel="mobile",
        platform="android",
        action_type="tap",
        target_phrase="Continue",
        options=ExecutionOptions(resolve_retries=2, resolve_retry_interval_ms=0),
    )


def test_mobile_reground_recollects_and_retries(monkeypatch):
    adapter = _FakeMobileAdapter()
    intent = _mobile_intent()

    attempts = {"n": 0}
    sentinel = (ResolvedTarget(ref='{"by":"xpath","value":"//node"}', confidence=0.9,
                               resolver_name="appium_hierarchy"), [])

    async def _fake_ground(_intent):
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise ResolutionFailedError(step="Tap Continue", message="not yet")
        return sentinel

    monkeypatch.setattr(sdk._engine, "ground", _fake_ground)

    target, _ = _run(sdk._ground_with_wait(adapter, intent))

    assert target.resolver_name == "appium_hierarchy"
    assert attempts["n"] == 2
    # Context was re-collected for the retry, and the mobile merge ran (it adds
    # the mobile memory signature only on the mobile channel).
    assert adapter.collect_calls == 1
    assert "mobile_memory_signature" in intent.context
    assert intent.context["hierarchy_xml"] == '<hierarchy><node text="Continue"/></hierarchy>'
