"""Last-resort fallback selector: a deterministic safety net used only after
every natural + AI approach fails to identify the element.

Covers the pure units (no browser):
  * ``_fallback_selector_target`` builds a flagged target from the option, and
    returns None when unset;
  * the option is plumbed through ``build_options`` / ``make_intent``;
  * the reporters count/flag a fallback-resolved step *apart* from self-heals.
"""

from __future__ import annotations

from bubblegum.core.planner.intent import build_options, make_intent
from bubblegum.core.schemas import ExecutionOptions, ResolvedTarget, StepResult
from bubblegum.core.sdk import FALLBACK_SELECTOR_RESOLVER, _fallback_selector_target
from bubblegum.reporting.html_report import write_html_report
from bubblegum.reporting.summary_report import _count_fallbacks, compute_run_summary


def _intent(fallback: str | None):
    return make_intent(
        instruction="Click Save",
        channel="web",
        platform="web",
        action_type="click",
        options=ExecutionOptions(fallback_selector=fallback),
    )


def test_option_is_plumbed_through_build_options():
    opts = build_options(
        {"fallback_selector": '[data-testid="save"]'},
        ai_enabled=True, max_cost_level="medium", memory_ttl_days=7, memory_max_failures=3,
    )
    assert opts.fallback_selector == '[data-testid="save"]'


def test_fallback_target_built_when_option_set():
    target = _fallback_selector_target(_intent("#save"))
    assert target is not None
    assert target.ref == "#save"
    assert target.resolver_name == FALLBACK_SELECTOR_RESOLVER
    assert target.metadata.get("fallback_selector_used") is True
    assert 0.0 < target.confidence < 0.85  # deliberately not a confident match


def test_no_fallback_target_without_option():
    assert _fallback_selector_target(_intent(None)) is None


def _step(resolver: str, meta: dict | None = None) -> StepResult:
    return StepResult(
        status="passed", action="Click Save",
        target=ResolvedTarget(ref="#x", confidence=0.5, resolver_name=resolver, metadata=meta or {}),
        confidence=0.5, duration_ms=1,
    )


def test_summary_counts_fallback_apart_from_recovered():
    results = [
        _step("accessibility_tree"),
        _step(FALLBACK_SELECTOR_RESOLVER, {"fallback_selector_used": True}),
        _step("fuzzy_text"),
    ]
    assert _count_fallbacks(results) == 1
    rec = compute_run_summary(results, "badge-creation")
    assert rec["fallback"] == 1
    assert rec["recovered"] == 0  # a fallback is NOT a self-heal


def test_html_report_flags_fallback_step(tmp_path):
    out = write_html_report(
        [_step(FALLBACK_SELECTOR_RESOLVER, {"fallback_selector_used": True, "fallback_selector": "#save"})],
        tmp_path / "r.html",
    )
    text = out.read_text(encoding="utf-8")
    assert "Fallback selector used" in text
    assert "#save" in text
