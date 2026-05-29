"""End-to-end: act() resolves target + value from plain English alone.

Regression guard for the original pain point — callers had to pass
selector=... and input_value=... which defeated the library's purpose.
A fake adapter records the ActionPlan and ResolvedTarget produced from a bare
NL instruction.
"""

from __future__ import annotations

import pytest

from bubblegum.core import sdk
from bubblegum.core.schemas import ArtifactRef, ExecutionResult, UIContext, ValidationResult

_LOGIN_A11Y = "\n".join(
    [
        '- textbox "Username"',
        '- textbox "Password"',
        '- button "Login"',
    ]
)


class FakeAdapter:
    def __init__(self):
        self.executed_plan = None
        self.executed_target = None

    async def collect_context(self, _request):
        return UIContext(a11y_snapshot=_LOGIN_A11Y, screen_signature="sig-1")

    async def execute(self, plan, target):
        self.executed_plan = plan
        self.executed_target = target
        return ExecutionResult(success=True, duration_ms=1)

    async def validate(self, _plan):
        return ValidationResult(passed=True)

    async def screenshot(self):
        return ArtifactRef(type="screenshot", path="/tmp/x.png")


@pytest.mark.asyncio
async def test_act_types_value_into_field_from_nl_only(monkeypatch):
    adapter = FakeAdapter()
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)

    result = await sdk.act('Enter "tomsmith" into Username', channel="web", page=object())

    assert result.status == "passed"
    # The value was parsed out of the instruction, not the target.
    assert adapter.executed_plan.input_value == "tomsmith"
    assert adapter.executed_plan.action_type == "type"
    # The resolved element is the Username field, NOT something named "tomsmith".
    assert "Username" in adapter.executed_target.ref


@pytest.mark.asyncio
async def test_act_click_from_nl_only(monkeypatch):
    adapter = FakeAdapter()
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)

    result = await sdk.act("Click Login", channel="web", page=object())

    assert result.status == "passed"
    assert adapter.executed_plan.action_type == "click"
    assert "Login" in adapter.executed_target.ref
