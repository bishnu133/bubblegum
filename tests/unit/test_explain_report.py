from __future__ import annotations

import pytest

from bubblegum.core import sdk
from bubblegum.core.schemas import (
    ErrorInfo,
    ExecutionResult,
    ResolvedTarget,
    ResolverTrace,
    StepResult,
    UIContext,
    ValidationResult,
)
from bubblegum.reporting.explain import format_explanation
from bubblegum.session import BubblegumSession


def _winner() -> ResolvedTarget:
    return ResolvedTarget(
        ref='role=button[name="Login"]',
        confidence=0.92,
        resolver_name="accessibility_tree",
        metadata={
            "signals": {
                "text_match": 0.95,
                "role_match": 1.0,
                "visibility": 1.0,
                "uniqueness": 0.80,
                "proximity": 0.70,
                "memory_history": 0.0,
            }
        },
    )


def _runner_up() -> ResolvedTarget:
    return ResolvedTarget(
        ref='role=link[name="Login"]',
        confidence=0.71,
        resolver_name="fuzzy_text",
        metadata={
            "signals": {
                "text_match": 0.80,
                "role_match": 0.70,
                "visibility": 1.0,
                "uniqueness": 0.50,
                "proximity": 0.50,
                "memory_history": 0.0,
            }
        },
    )


def _resolved_result() -> StepResult:
    winner = _winner()
    traces = [
        ResolverTrace(resolver_name="memory_cache", duration_ms=0, candidates=[], can_run=False,
                      reason_skipped="no cached entry"),
        ResolverTrace(resolver_name="accessibility_tree", duration_ms=12, candidates=[winner, _runner_up()], can_run=True),
    ]
    return StepResult(status="passed", action="Click Login", target=winner, confidence=0.92, traces=traces)


# ---------------------------------------------------------------------------
# format_explanation
# ---------------------------------------------------------------------------


def test_explanation_header_and_decision():
    text = format_explanation(_resolved_result())
    assert "Bubblegum — explain: 'Click Login'" in text
    assert "Decision: PASSED → role=button[name=\"Login\"]" in text
    assert "resolver=accessibility_tree" in text


def test_explanation_reports_tier_stopped_at():
    text = format_explanation(_resolved_result())
    # accessibility_tree is a Tier 1 resolver; tier is looked up from the registry.
    assert "Stopped at: Tier 1 (accessibility_tree)" in text


def test_explanation_lists_ranked_candidates_with_winner_marker():
    text = format_explanation(_resolved_result())
    assert "Ranked candidates (2):" in text
    assert "← winner" in text
    # Winner appears before the runner-up (higher score sorted first).
    assert text.index('role=button[name="Login"]') < text.index('role=link[name="Login"]')


def test_explanation_shows_signal_breakdown_and_weights():
    text = format_explanation(_resolved_result())
    # text_match 0.95 × weight 0.30 = 0.285
    assert "text_match     0.95 ×0.30 = 0.285" in text
    assert "role_match     1.00 ×0.20 = 0.200" in text
    assert "Σ weighted" in text


def test_explanation_why_winner_won_reports_gap():
    text = format_explanation(_resolved_result())
    assert "Why the winner won:" in text
    # winner weighted ≈ 0.825, runner-up ≈ 0.685 → gap ≈ 0.14
    assert "beats runner-up" in text


def test_explanation_resolver_run_log_shows_ran_and_skipped():
    text = format_explanation(_resolved_result())
    assert "✓ accessibility_tree" in text
    assert "· memory_cache" in text
    assert "no cached entry" in text


def test_explanation_handles_unresolved_step():
    result = StepResult(
        status="failed",
        action="Click Ghost",
        confidence=0.0,
        error=ErrorInfo(error_type="ResolutionFailedError", message="no candidates"),
        traces=[ResolverTrace(resolver_name="exact_text", duration_ms=3, candidates=[], can_run=True)],
    )
    text = format_explanation(result)
    assert "UNRESOLVED" in text
    assert "no candidates" in text
    assert "Ranked candidates (0)" in text


def test_explanation_falls_back_without_signals():
    target = ResolvedTarget(ref="css=#x", confidence=0.88, resolver_name="explicit_selector")
    result = StepResult(status="passed", action="Click X", target=target, confidence=0.88,
                        traces=[ResolverTrace(resolver_name="explicit_selector", duration_ms=1, candidates=[target], can_run=True)])
    text = format_explanation(result)
    assert "no signal breakdown" in text


# ---------------------------------------------------------------------------
# session.explain (dry-run convenience)
# ---------------------------------------------------------------------------

_A11Y = "\n".join(["- button \"Login\"", "- textbox \"Username\""])


class _ExplainAdapter:
    async def collect_context(self, _req):
        return UIContext(a11y_snapshot=_A11Y, screen_signature="sig")

    async def execute(self, plan, target):
        return ExecutionResult(success=True, duration_ms=1)

    async def validate(self, _plan):
        return ValidationResult(passed=True)

    async def screenshot(self):
        raise AssertionError("explain() must not execute or screenshot")


@pytest.mark.asyncio
async def test_session_explain_is_dry_run_and_returns_text(monkeypatch, capsys):
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: _ExplainAdapter())
    s = BubblegumSession.web(object())

    text = await s.explain("Click Login")

    assert "Bubblegum — explain: 'Click Login'" in text
    # Dry-run: nothing appended to the session results.
    assert s.results() == []
    # It printed by default.
    assert "explain" in capsys.readouterr().out
