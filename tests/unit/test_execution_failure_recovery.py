"""
tests/unit/test_execution_failure_recovery.py
=============================================
Regression: an AI-grounded target that resolves confidently but fails to
EXECUTE must be recovered by the deterministic DOM handlers.

Repro of the real-world flake: on a custom Ant multi-select, llm_grounding
returns role=combobox[name="Recommendation Tags"] at high confidence, but that
locator doesn't resolve on the page, so select_option times out. Before this
fix the step just failed (the DOM select-trigger fallback only ran when
*grounding* raised, not when execution failed).
"""

from __future__ import annotations

import asyncio

from bubblegum.core import sdk
from bubblegum.core.schemas import ExecutionOptions, ResolvedTarget, StepIntent


class _ExecResult:
    def __init__(self, success, error=None):
        self.success = success
        self.error = error


def _intent(action="select"):
    return StepIntent(
        instruction='Select "Aerobic" from "Recommendation Tags" drop down',
        channel="web",
        platform="chromium",
        action_type=action,
        target_phrase="Recommendation Tags",
        input_value="Aerobic",
        context={},
        options=ExecutionOptions(),
    )


def test_recovers_when_grounded_target_fails_but_dom_handler_succeeds(monkeypatch):
    failed = ResolvedTarget(ref='role=combobox[name="Recommendation Tags"]', confidence=0.775,
                            resolver_name="llm_grounding", metadata={"role": "combobox"})
    good = ResolvedTarget(ref='css=[data-testid="recommendation-tag-select-0"]', confidence=0.6,
                          resolver_name="select_trigger_dom", metadata={"role": "combobox"})

    # The DOM select-trigger handler finds the real Ant select…
    async def fake_select_trigger(adapter, channel, intent):
        return good
    monkeypatch.setattr(sdk, "_maybe_resolve_select_trigger", fake_select_trigger)
    monkeypatch.setattr(sdk, "_maybe_resolve_clickable", lambda *a, **k: _none())
    monkeypatch.setattr(sdk, "_maybe_resolve_input", lambda *a, **k: _none())

    # …and it executes successfully (unlike the original combobox ref).
    class _Adapter:
        async def execute(self, plan, target):
            return _ExecResult(target.ref == good.ref, None if target.ref == good.ref else "timeout")

    result = asyncio.run(
        sdk._recover_failed_execution(_Adapter(), "web", _intent().instruction, _intent(), ExecutionOptions(), failed)
    )
    assert result is not None
    recovered_target, exec_result = result
    assert exec_result.success is True
    assert recovered_target.ref == good.ref
    assert recovered_target.metadata["healing"]["kind"] == "execution_recovery"
    assert recovered_target.metadata["healing"]["from_ref"] == failed.ref


def test_no_recovery_when_dom_handler_returns_same_ref(monkeypatch):
    failed = ResolvedTarget(ref="css=#same", confidence=0.7, resolver_name="llm_grounding", metadata={})

    async def same_ref(adapter, channel, intent):
        return ResolvedTarget(ref="css=#same", confidence=0.6, resolver_name="select_trigger_dom", metadata={})
    monkeypatch.setattr(sdk, "_maybe_resolve_select_trigger", same_ref)
    monkeypatch.setattr(sdk, "_maybe_resolve_clickable", lambda *a, **k: _none())
    monkeypatch.setattr(sdk, "_maybe_resolve_input", lambda *a, **k: _none())

    class _Adapter:
        async def execute(self, plan, target):
            return _ExecResult(True)   # would "succeed", but we must not retry the same ref

    result = asyncio.run(
        sdk._recover_failed_execution(_Adapter(), "web", "x", _intent(), ExecutionOptions(), failed)
    )
    assert result is None      # same ref skipped -> nothing to recover with


def test_no_recovery_on_mobile(monkeypatch):
    failed = ResolvedTarget(ref="x", confidence=0.7, resolver_name="llm_grounding", metadata={})

    class _Adapter:
        async def execute(self, plan, target):
            return _ExecResult(True)

    result = asyncio.run(
        sdk._recover_failed_execution(_Adapter(), "mobile", "x", _intent(), ExecutionOptions(), failed)
    )
    assert result is None


def test_returns_none_when_no_dom_candidate(monkeypatch):
    failed = ResolvedTarget(ref="x", confidence=0.7, resolver_name="llm_grounding", metadata={})
    monkeypatch.setattr(sdk, "_maybe_resolve_select_trigger", lambda *a, **k: _none())
    monkeypatch.setattr(sdk, "_maybe_resolve_clickable", lambda *a, **k: _none())
    monkeypatch.setattr(sdk, "_maybe_resolve_input", lambda *a, **k: _none())

    class _Adapter:
        async def execute(self, plan, target):
            return _ExecResult(False, "timeout")

    result = asyncio.run(
        sdk._recover_failed_execution(_Adapter(), "web", "x", _intent(), ExecutionOptions(), failed)
    )
    assert result is None


def test_recovers_type_into_modal_field_via_input_dom(monkeypatch):
    # Repro of the popup-input flake: grounding picks a disabled same-named field
    # behind the modal (role=spinbutton[name="Points"]) which fails to fill;
    # the DOM input finder (now enabled-only) returns the modal's real field.
    failed = ResolvedTarget(ref='role=spinbutton[name="Points"]', confidence=0.72,
                            resolver_name="llm_grounding", metadata={"role": "spinbutton"})
    good = ResolvedTarget(ref='css=#pointsField', confidence=0.7,
                          resolver_name="input_dom", metadata={"role": "textbox"})

    async def fake_input(adapter, channel, intent):
        return good
    monkeypatch.setattr(sdk, "_maybe_resolve_select_trigger", lambda *a, **k: _none())
    monkeypatch.setattr(sdk, "_maybe_resolve_clickable", lambda *a, **k: _none())
    monkeypatch.setattr(sdk, "_maybe_resolve_input", fake_input)

    class _Adapter:
        async def execute(self, plan, target):
            return _ExecResult(target.ref == good.ref, None if target.ref == good.ref else "disabled")

    result = asyncio.run(
        sdk._recover_failed_execution(
            _Adapter(), "web", 'Enter "150" into Points', _intent("type"), ExecutionOptions(), failed,
        )
    )
    assert result is not None
    recovered_target, exec_result = result
    assert exec_result.success is True
    assert recovered_target.ref == good.ref


async def _none():
    return None
