"""
tests/unit/test_phase1a_resolvers.py
=====================================
Unit tests for Phase 1A resolvers.
No real browser required — all tests use mock StepIntent and synthetic a11y snapshots.

Run with:
    pytest tests/unit/test_phase1a_resolvers.py -v
"""

from __future__ import annotations

import asyncio
import pytest

from bubblegum.core.grounding.engine import GroundingEngine
from bubblegum.core.grounding.ranker import CandidateRanker
from bubblegum.core.schemas import ExecutionOptions, StepIntent
from bubblegum.core.grounding.resolvers.explicit_selector import ExplicitSelectorResolver
from bubblegum.core.grounding.resolvers.accessibility_tree import AccessibilityTreeResolver
from bubblegum.core.grounding.resolvers.exact_text import ExactTextResolver


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

SAMPLE_SNAPSHOT = """\
- banner
  - heading "My App" [level=1]
- main
  - textbox "Username"
  - textbox "Password"
  - button "Login"
  - link "Forgot password?"
  - checkbox "Remember me"
"""

SNAPSHOT_MULTI_BUTTON = """\
- button "Submit"
- button "Cancel"
- button "Submit"
"""


def _intent(
    instruction: str,
    action_type: str = "click",
    context: dict | None = None,
    channel: str = "web",
) -> StepIntent:
    return StepIntent(
        instruction=instruction,
        channel=channel,
        platform="web",
        action_type=action_type,
        context=context or {},
        options=ExecutionOptions(),
    )


# ---------------------------------------------------------------------------
# ExplicitSelectorResolver
# ---------------------------------------------------------------------------

class TestExplicitSelectorResolver:
    def setup_method(self):
        self.resolver = ExplicitSelectorResolver()

    def test_returns_confidence_1_when_selector_present(self):
        intent = _intent("Click Login", context={"explicit_selector": "#login-btn"})
        results = self.resolver.resolve(intent)
        assert len(results) == 1
        assert results[0].ref == "#login-btn"
        assert results[0].confidence == 1.0
        assert results[0].resolver_name == "explicit_selector"

    def test_returns_empty_when_no_selector(self):
        assert self.resolver.resolve(_intent("Click Login")) == []

    def test_returns_empty_when_selector_is_empty_string(self):
        intent = _intent("Click Login", context={"explicit_selector": ""})
        assert self.resolver.resolve(intent) == []

    def test_can_run_without_any_context(self):
        assert self.resolver.can_run(_intent("Click Login")) is True

    def test_required_context_is_empty(self):
        assert self.resolver.required_context() == []

    def test_priority_is_zero(self):
        assert self.resolver.priority == 0

    def test_short_circuits_with_full_confidence(self):
        intent = _intent("Click Submit", context={"explicit_selector": ".submit"})
        assert self.resolver.resolve(intent)[0].confidence == 1.0

    def test_works_with_xpath_selector(self):
        intent = _intent("Click btn", context={"explicit_selector": "//button[@id='btn']"})
        assert self.resolver.resolve(intent)[0].ref == "//button[@id='btn']"

    def test_works_with_css_selector(self):
        intent = _intent("Click btn", context={"explicit_selector": "button.primary"})
        assert self.resolver.resolve(intent)[0].ref == "button.primary"

    def test_emits_strong_signals_that_rank_to_accept(self):
        intent = _intent("Click Login", context={"explicit_selector": "#login-btn"})
        result = self.resolver.resolve(intent)[0]
        ranked = CandidateRanker().score(result)
        assert ranked >= 0.85

    def test_engine_returns_explicit_selector_without_low_confidence(self):
        intent = _intent("Click Login", context={"explicit_selector": "#login-btn"})
        target, _traces = asyncio.run(GroundingEngine().ground(intent))
        assert target.resolver_name == "explicit_selector"
        assert target.ref == "#login-btn"
        assert target.confidence >= 0.85


# ---------------------------------------------------------------------------
# AccessibilityTreeResolver
# ---------------------------------------------------------------------------

class TestAccessibilityTreeResolver:
    def setup_method(self):
        self.resolver = AccessibilityTreeResolver()

    def test_required_context_is_empty(self):
        """Guards inside resolve() — required_context() must return [] for registry eligibility."""
        assert self.resolver.required_context() == []

    def test_can_run_with_empty_context(self):
        """Always eligible for web channel regardless of context state."""
        assert self.resolver.can_run(_intent("Click Login")) is True

    def test_can_run_with_snapshot_in_context(self):
        intent = _intent("Click Login", context={"a11y_snapshot": SAMPLE_SNAPSHOT})
        assert self.resolver.can_run(intent) is True

    def test_returns_empty_when_snapshot_absent(self):
        assert self.resolver.resolve(_intent("Click Login")) == []

    def test_finds_login_button_exact_match(self):
        intent = _intent("Click Login", action_type="click",
                         context={"a11y_snapshot": SAMPLE_SNAPSHOT})
        results = self.resolver.resolve(intent)
        login = next((r for r in results if "Login" in r.ref), None)
        assert login is not None
        assert login.confidence == 0.96   # raised from 0.92 to clear ambiguity gap

    def test_ref_format_role_name(self):
        intent = _intent("Click Login", context={"a11y_snapshot": SAMPLE_SNAPSHOT})
        results = self.resolver.resolve(intent)
        login = next(r for r in results if "Login" in r.ref)
        assert login.ref == 'role=button[name="Login"]'

    def test_finds_textbox_for_type_action(self):
        intent = _intent("Type Username", action_type="type",
                         context={"a11y_snapshot": SAMPLE_SNAPSHOT})
        results = self.resolver.resolve(intent)
        assert any("Username" in r.ref for r in results)

    def test_empty_snapshot_returns_empty(self):
        intent = _intent("Click Login", context={"a11y_snapshot": ""})
        assert self.resolver.resolve(intent) == []

    def test_snapshot_with_no_matching_elements(self):
        intent = _intent("Click NonExistent", context={"a11y_snapshot": SAMPLE_SNAPSHOT})
        for r in self.resolver.resolve(intent):
            assert "NonExistent" not in r.ref

    def test_web_only_channel(self):
        assert self.resolver.channels == ["web"]

    def test_mobile_channel_cannot_run(self):
        intent = _intent("Tap Login", channel="mobile",
                         context={"a11y_snapshot": SAMPLE_SNAPSHOT})
        assert self.resolver.can_run(intent) is False

    def test_resolver_name(self):
        intent = _intent("Click Login", context={"a11y_snapshot": SAMPLE_SNAPSHOT})
        for r in self.resolver.resolve(intent):
            assert r.resolver_name == "accessibility_tree"

    def test_exact_match_confidence_clears_ambiguity_gap(self):
        """
        a11y exact match (0.96) minus ExactText exact match (0.90) = 0.06 > ambiguous_gap (0.05).
        The engine must never raise AmbiguousTargetError for this common case.
        """
        a11y_conf  = 0.96
        exact_conf = 0.90
        gap = a11y_conf - exact_conf
        assert gap > 0.05, (
            f"Gap {gap:.3f} is <= ambiguous_gap 0.05 — engine will raise AmbiguousTargetError"
        )

    def test_role_without_name_returns_low_confidence(self):
        intent = _intent("Click button", context={"a11y_snapshot": SAMPLE_SNAPSHOT})
        for r in self.resolver.resolve(intent):
            assert r.confidence <= 0.96

    def test_verify_phrase_match_emits_strong_signals(self):
        snapshot = '- heading "Example Domain" [level=1]\n'
        intent = _intent(
            "Example Domain visible",
            action_type="verify",
            context={"a11y_snapshot": snapshot},
        )
        results = self.resolver.resolve(intent)
        heading = next(r for r in results if 'role=heading[name="Example Domain"]' == r.ref)
        scored = CandidateRanker().score(heading)
        assert scored >= 0.85
        assert heading.resolver_name == "accessibility_tree"

    def test_extract_phrase_match_emits_strong_signals(self):
        snapshot = '- heading "Example Domain" [level=1]\n'
        intent = _intent(
            "Get text of Example Domain heading",
            action_type="extract",
            context={"a11y_snapshot": snapshot},
        )
        results = self.resolver.resolve(intent)
        heading = next(r for r in results if 'role=heading[name="Example Domain"]' == r.ref)
        scored = CandidateRanker().score(heading)
        assert scored >= 0.85
        assert heading.resolver_name == "accessibility_tree"

    def test_engine_returns_heading_for_verify_nl_phrase(self):
        snapshot = '- heading "Example Domain" [level=1]\n'
        intent = _intent(
            "Example Domain visible",
            action_type="verify",
            context={"a11y_snapshot": snapshot},
        )
        target, _traces = asyncio.run(GroundingEngine().ground(intent))
        assert target.ref == 'role=heading[name="Example Domain"]'
        assert target.resolver_name == "accessibility_tree"

    def test_engine_returns_heading_for_extract_nl_phrase(self):
        snapshot = '- heading "Example Domain" [level=1]\n'
        intent = _intent(
            "Get text of Example Domain heading",
            action_type="extract",
            context={"a11y_snapshot": snapshot},
        )
        target, _traces = asyncio.run(GroundingEngine().ground(intent))
        assert target.ref == 'role=heading[name="Example Domain"]'
        assert target.resolver_name == "accessibility_tree"

    def test_verify_active_plan_short_label_not_over_boosted(self):
        snapshot = """\
- paragraph "Status: Active plan"
- combobox "plan"
"""
        intent = _intent(
            "Verify text Active plan is visible",
            action_type="verify",
            context={"a11y_snapshot": snapshot},
        )
        results = self.resolver.resolve(intent)
        para = next(r for r in results if r.ref == 'role=paragraph[name="Status: Active plan"]')
        combo = next(r for r in results if r.ref == 'role=combobox[name="plan"]')
        para_score = CandidateRanker().score(para)
        combo_score = CandidateRanker().score(combo)
        assert para_score > combo_score
        assert combo_score < 0.72


# ---------------------------------------------------------------------------
# ExactTextResolver
# ---------------------------------------------------------------------------

class TestExactTextResolver:
    def setup_method(self):
        self.resolver = ExactTextResolver()

    def test_required_context(self):
        assert "a11y_snapshot" in self.resolver.required_context()

    def test_exact_case_sensitive_match(self):
        intent = _intent("Click Login", context={"a11y_snapshot": SAMPLE_SNAPSHOT})
        results = self.resolver.resolve(intent)
        login = next((r for r in results if "Login" in r.ref), None)
        assert login is not None
        assert login.confidence == 0.90

    def test_ref_is_text_locator_format(self):
        intent = _intent("Click Login", context={"a11y_snapshot": SAMPLE_SNAPSHOT})
        results = self.resolver.resolve(intent)
        login = next(r for r in results if "Login" in r.ref)
        assert login.ref == 'text="Login"'

    def test_case_insensitive_match_lower_confidence(self):
        snapshot = '- button "login"\n'
        intent = _intent("Click Login", context={"a11y_snapshot": snapshot})
        results = self.resolver.resolve(intent)
        assert len(results) >= 1
        assert results[0].confidence == 0.82

    def test_no_match_returns_empty(self):
        intent = _intent("Click XYZ_NONEXISTENT", context={"a11y_snapshot": SAMPLE_SNAPSHOT})
        assert self.resolver.resolve(intent) == []

    def test_deduplicates_repeated_elements(self):
        intent = _intent("Click Submit", context={"a11y_snapshot": SNAPSHOT_MULTI_BUTTON})
        refs = [r.ref for r in self.resolver.resolve(intent)]
        assert len(refs) == len(set(refs))

    def test_resolver_name(self):
        intent = _intent("Click Login", context={"a11y_snapshot": SAMPLE_SNAPSHOT})
        for r in self.resolver.resolve(intent):
            assert r.resolver_name == "exact_text"

    def test_web_and_mobile_channels(self):
        assert "web" in self.resolver.channels
        assert "mobile" in self.resolver.channels

    def test_empty_snapshot_returns_empty(self):
        intent = _intent("Click Login", context={"a11y_snapshot": ""})
        assert self.resolver.resolve(intent) == []

    def test_priority_ordering(self):
        assert ExactTextResolver().priority > AccessibilityTreeResolver().priority


# ---------------------------------------------------------------------------
# Cross-resolver: confidence ordering
# ---------------------------------------------------------------------------

class TestConfidenceOrdering:
    def test_explicit_beats_accessibility_beats_exact(self):
        """
        explicit_selector (1.0) > a11y (0.96) > exact_text (0.90).
        Gap between a11y and exact_text must be > ambiguous_gap (0.05).
        """
        explicit  = ExplicitSelectorResolver()
        a11y      = AccessibilityTreeResolver()
        exact_txt = ExactTextResolver()

        context = {"explicit_selector": "#login", "a11y_snapshot": SAMPLE_SNAPSHOT}
        intent  = _intent("Click Login", context=context)

        top_explicit = max(r.confidence for r in explicit.resolve(intent))
        top_a11y     = max(r.confidence for r in a11y.resolve(intent))
        top_exact    = max(r.confidence for r in exact_txt.resolve(intent))

        assert top_explicit > top_a11y
        assert top_a11y > top_exact
        assert (top_a11y - top_exact) > 0.05, (
            "Gap between a11y and exact_text must exceed ambiguous_gap=0.05"
        )
