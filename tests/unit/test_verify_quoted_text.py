"""verify() prefers quoted text as the literal assertion target.

A descriptive verify like 'the page shows an "Update account status" button'
should check for the quoted text, not the whole sentence. Multiple quoted
segments must all be visible. Uses a fake adapter (no browser).
"""

from __future__ import annotations

import asyncio

import bubblegum.core.sdk as sdk
from bubblegum.core.schemas import ValidationPlan, ValidationResult


def _run(coro):
    return asyncio.run(coro)


class _Adapter:
    """text_visible adapter: passes when expected_value is in ``visible_text``."""

    def __init__(self, visible_text: set[str]):
        self.visible = visible_text
        self.checked: list[str] = []

    async def collect_context(self, *_a, **_k):
        from bubblegum.core.schemas import UIContext
        return UIContext(channel="web")

    async def validate(self, plan: ValidationPlan) -> ValidationResult:
        self.checked.append(plan.expected_value)
        ok = plan.expected_value in self.visible
        return ValidationResult(passed=ok, actual_value=plan.expected_value if ok else "not found")


def _verify(monkeypatch, instruction, visible, **kwargs):
    adapter = _Adapter(set(visible))
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)
    # Resolve grounding to a dummy target so verify reaches the validation step.
    from bubblegum.core.schemas import ResolvedTarget

    async def _fake_ground(_adapter, _intent):
        return ResolvedTarget(ref="page", confidence=0.9, resolver_name="t"), []
    monkeypatch.setattr(sdk, "_ground_with_wait", _fake_ground)
    res = _run(sdk.verify(instruction, channel="web", page=object(), **kwargs))
    return res, adapter


def test_quoted_text_is_checked_not_whole_sentence(monkeypatch):
    res, adapter = _verify(
        monkeypatch,
        'the Participant profile page is shown with an "Update account status" button',
        visible={"Update account status"},
    )
    assert res.status == "passed"
    assert adapter.checked == ["Update account status"]


def test_multiple_quoted_segments_all_must_be_visible(monkeypatch):
    res, _ = _verify(
        monkeypatch,
        'the header shows "Active" and "Verified"',
        visible={"Active", "Verified"},
    )
    assert res.status == "passed"


def test_multiple_quoted_segments_fail_if_one_missing(monkeypatch):
    res, _ = _verify(
        monkeypatch,
        'the header shows "Active" and "Verified"',
        visible={"Active"},  # "Verified" missing
    )
    assert res.status == "failed"
    assert "Verified" in (res.error.message or "")


def test_unquoted_verify_keeps_legacy_behaviour(monkeypatch):
    # No quotes: falls back to extract_expected (strips trailing "is visible").
    res, adapter = _verify(monkeypatch, "Hello World is visible", visible={"Hello World"})
    assert res.status == "passed"
    assert adapter.checked == ["Hello World"]


def test_explicit_expected_value_wins_over_quotes(monkeypatch):
    res, adapter = _verify(
        monkeypatch, 'shows "Active"', visible={"override"}, expected_value="override")
    assert res.status == "passed"
    assert adapter.checked == ["override"]
