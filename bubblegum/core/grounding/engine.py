"""
bubblegum/core/grounding/engine.py
====================================
GroundingEngine — orchestrates tiered resolver execution for a single StepIntent.

Execution model:
  Tier 1 (priority 0–39):  deterministic resolvers — stop only if best confidence ≥ 0.85
  Tier 2 (priority 40–49): fuzzy resolvers        — stop if best confidence ≥ 0.70
  Tier 3 (priority 50+):   AI fallback            — only if Tiers 1+2 failed; blocked on cost=low

Important current semantics:
  - Tier 1 does NOT auto-return candidates in the review band [0.70, 0.85).
    Those candidates are carried forward while lower tiers are still attempted.
  - review_threshold is a return gate for Tier 2/3, not Tier 1.
  - reject_threshold is stored/configurable but not used as a direct return gate
    in this control flow; final LowConfidenceError is raised whenever candidates
    exist but no tier-specific return condition was met.

Ambiguity check:
  If the top 2 candidates are within 0.05 confidence → raise AmbiguousTargetError.
  Never auto-execute when ambiguous.

Final outcome:
  Candidate found but low confidence → LowConfidenceError
  No candidate found at all          → ResolutionFailedError

Phase 0 — skeleton with full logic wiring. Resolvers return [] until Phase 1+ implementation.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from bubblegum.core.grounding.errors import (
    AICostPolicyBlockedError,
    AmbiguousTargetError,
    LowConfidenceError,
    ResolutionFailedError,
)
from bubblegum.core import cost
from bubblegum.core.grounding.ranker import CandidateRanker
from bubblegum.core.grounding.registry import ResolverRegistry
from bubblegum.core.schemas import ResolvedTarget, ResolverTrace, StepIntent

if TYPE_CHECKING:
    from bubblegum.core.grounding.resolver import Resolver

logger = logging.getLogger(__name__)

# Tier boundaries (inclusive priority ranges)
_TIER_RANGES: dict[int, tuple[int, int]] = {
    1: (0,  39),
    2: (40, 49),
    3: (50, 999),
}

# Default thresholds — overridden by BubblegumConfig at runtime
_ACCEPT_THRESHOLD:  float = 0.85
_REVIEW_THRESHOLD:  float = 0.70
_AMBIGUOUS_GAP:     float = 0.05
_REJECT_THRESHOLD:  float = 0.50

_DROPDOWN_KEYWORDS = ("dropdown", "combobox", "combo box", "listbox", "picker", "selector")


def _is_dropdown_select_intent(intent: StepIntent) -> bool:
    """True when the step clearly targets a dropdown / select control.

    Used to relax the final confidence gate for nameless custom comboboxes,
    whose best honest score is role-fit (~0.57) rather than a name match.
    """
    if getattr(intent, "action_type", None) == "select":
        return True
    ri = intent.context.get("relational_intent")
    if isinstance(ri, dict) and str(ri.get("control_kind_hint", "")).lower() in (
        "combobox", "select", "dropdown"
    ):
        return True
    text = (intent.instruction or "").lower()
    return any(k in text for k in _DROPDOWN_KEYWORDS)


class GroundingEngine:
    """
    Orchestrates tiered resolver execution for a single StepIntent.

    Usage:
        engine = GroundingEngine(registry=registry, config=config)
        target, traces = await engine.ground(intent)
    """

    def __init__(
        self,
        registry:         ResolverRegistry | None = None,
        accept_threshold: float = _ACCEPT_THRESHOLD,
        review_threshold: float = _REVIEW_THRESHOLD,
        ambiguous_gap:    float = _AMBIGUOUS_GAP,
        reject_threshold: float = _REJECT_THRESHOLD,
        ai_first:         bool  = False,
    ) -> None:
        self.registry         = registry or ResolverRegistry()
        self.ranker           = CandidateRanker()
        self.accept_threshold = accept_threshold
        self.review_threshold = review_threshold
        self.ambiguous_gap    = ambiguous_gap
        self.reject_threshold = reject_threshold
        # When True, the AI tier (vision/LLM) is attempted before the
        # deterministic tiers — "use AI as the first approach to find the
        # element". Only reorders when the AI tier can actually run (cost
        # policy permits and an eligible Tier 3 resolver exists), so it never
        # blocks deterministic resolution when AI is unavailable.
        self.ai_first         = ai_first

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def ground(
        self, intent: StepIntent
    ) -> tuple[ResolvedTarget, list[ResolverTrace]]:
        """
        Run resolvers in tier order and return the best ResolvedTarget.

        Returns:
            (best_target, traces)  where traces contains one entry per resolver that ran.

        Raises:
            AmbiguousTargetError     — top 2 candidates within ambiguous_gap
            LowConfidenceError       — best candidate found but below reject_threshold
            ResolutionFailedError    — no candidate found across all tiers
            AICostPolicyBlockedError — Tier 3 would run but max_cost_level=low
        """
        all_candidates: list[ResolvedTarget] = []
        all_traces:     list[ResolverTrace]  = []

        # AI-first: attempt the AI tier before the deterministic tiers when the
        # caller opted in AND the AI tier can actually run. Otherwise fall back
        # to the standard deterministic-first order so AI-first never blocks or
        # changes behaviour when AI is unavailable / cost-blocked.
        tier_order: tuple[int, ...] = (1, 2, 3)
        if self.ai_first and self._ai_tier_runnable(intent):
            tier_order = (3, 1, 2)

        for tier_num in tier_order:
            # Before running Tier 3: check if it is blocked by cost policy.
            # We check this even before _run_tier because can_run() will filter
            # all Tier 3 resolvers out when max_cost_level=low, so tier_candidates
            # would be empty — we need to surface the real reason instead.
            if tier_num == 3 and intent.options.max_cost_level == "low":
                # Confirm there actually ARE Tier 3 resolvers that would otherwise run
                lo, hi = _TIER_RANGES[3]
                all_tier3 = [r for r in self.registry.all() if lo <= r.priority <= hi and intent.channel in r.channels]
                if all_tier3:
                    raise AICostPolicyBlockedError(
                        step=intent.instruction,
                        message="Tier 3 AI resolvers exist but are blocked because max_cost_level=low.",
                    )

            # X2: per-run cost budget hard-stop — once the run's estimated LLM
            # spend has reached the budget, block further Tier 3 AI calls.
            if tier_num == 3 and cost.budget_exceeded():
                lo, hi = _TIER_RANGES[3]
                all_tier3 = [r for r in self.registry.all() if lo <= r.priority <= hi and intent.channel in r.channels]
                if all_tier3:
                    tracker = cost.get_tracker()
                    raise AICostPolicyBlockedError(
                        step=intent.instruction,
                        message=(
                            f"Tier 3 AI resolvers are blocked: per-run cost budget exceeded "
                            f"(spent ${tracker.spent:.4f} ≥ budget ${tracker.budget:.4f})."
                        ),
                    )

            tier_candidates, tier_traces = self._run_tier(intent, tier_num)
            all_candidates.extend(tier_candidates)
            all_traces.extend(tier_traces)

            if not tier_candidates:
                continue

            best = self.ranker.best(tier_candidates)

            # Tier 1: stop on accept_threshold only.
            # NOTE: review-range scores in Tier 1 intentionally do not return;
            # they fall through so lower tiers can attempt resolution.
            if tier_num == 1 and best.confidence >= self.accept_threshold:
                logger.debug("Tier 1 resolved '%s' — confidence %.2f", intent.instruction, best.confidence)
                self._check_ambiguity(tier_candidates, intent)
                return best, all_traces

            # Tier 2: stop on review_threshold
            if tier_num == 2 and best.confidence >= self.review_threshold:
                logger.debug("Tier 2 resolved '%s' — confidence %.2f", intent.instruction, best.confidence)
                self._check_ambiguity(tier_candidates, intent)
                return best, all_traces

            # Tier 3: stop on review_threshold
            if tier_num == 3 and best.confidence >= self.review_threshold:
                logger.debug("Tier 3 resolved '%s' — confidence %.2f", intent.instruction, best.confidence)
                self._check_ambiguity(tier_candidates, intent)
                return best, all_traces

        # All tiers exhausted.
        # A perfect deterministic match (exact role + name + uniqueness) tops out
        # in the review band [review_threshold, accept_threshold) because
        # visibility/proximity/memory signals are legitimately unknown on a first
        # run. Per the documented semantics (review_threshold = "proceed with
        # warning"), return the best review-band candidate instead of failing —
        # this is what lets plain-English steps resolve without a manual selector.
        if all_candidates:
            # Deduplicate by ref — keep highest-confidence entry per ref so that
            # the same element found by multiple resolvers is not treated as
            # two distinct ambiguous candidates.
            deduped: dict[str, ResolvedTarget] = {}
            for c in all_candidates:
                if c.ref not in deduped or c.confidence > deduped[c.ref].confidence:
                    deduped[c.ref] = c
            unique_candidates = list(deduped.values())

            best = self.ranker.best(unique_candidates)
            if best.confidence >= self.review_threshold:
                logger.debug(
                    "Resolved '%s' from review-band fallback — confidence %.2f",
                    intent.instruction, best.confidence,
                )
                self._check_ambiguity(unique_candidates, intent)
                return best, all_traces

            # Dropdown/select relax: a custom combobox (Ant Design / MUI / CDK)
            # has no useful accessible name — its value often becomes its name —
            # so "select X from the Y dropdown" tops out at role-fit confidence
            # (~0.57) and would be rejected at the review bar even though the
            # combobox is the correct target. When the step clearly means a
            # dropdown, accept the best combobox/listbox candidate above the
            # reject threshold instead of failing. Ambiguity is still checked
            # among the comboboxes, so two equally-likely selects raise the usual
            # AmbiguousTargetError rather than silently picking one.
            if _is_dropdown_select_intent(intent):
                combos = [
                    c for c in unique_candidates
                    if str(c.metadata.get("role", "")).lower() in ("combobox", "listbox")
                ]
                if len(combos) == 1:
                    best_combo = combos[0]
                    # A named combobox (its value often becomes its accessible
                    # name) is uniquely identifiable; accept it. A nameless one is
                    # only safe when it is genuinely the single combobox on the
                    # page — multiple nameless comboboxes collapse to the same
                    # "role=combobox" ref and must stay ambiguous.
                    has_name = bool(str(best_combo.metadata.get("name", "")).strip())
                    raw_same_ref = sum(1 for c in all_candidates if c.ref == best_combo.ref)
                    if best_combo.confidence >= self.reject_threshold and (has_name or raw_same_ref == 1):
                        logger.debug(
                            "Resolved dropdown '%s' via combobox relax — confidence %.2f",
                            intent.instruction, best_combo.confidence,
                        )
                        return best_combo, all_traces

            raise LowConfidenceError(
                step=intent.instruction,
                candidates=all_candidates,
                best_confidence=best.confidence,
            )

        raise ResolutionFailedError(
            step=intent.instruction,
            message="No resolver found a candidate for this step.",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ai_tier_runnable(self, intent: StepIntent) -> bool:
        """
        True only when the AI tier (Tier 3) can actually run for this intent:
        the cost policy permits AI and at least one eligible Tier 3 resolver
        exists for the channel. Used to gate AI-first reordering so it never
        blocks deterministic resolution when AI is unavailable or cost-blocked.
        """
        if intent.options.max_cost_level == "low":
            return False
        lo, hi = _TIER_RANGES[3]
        return any(
            lo <= r.priority <= hi and intent.channel in r.channels
            for r in self.registry.all()
        )

    def _run_tier(
        self, intent: StepIntent, tier_num: int
    ) -> tuple[list[ResolvedTarget], list[ResolverTrace]]:
        """
        Run eligible resolvers in a tier in priority order.

        Early-exit within the tier: if any resolver returns a candidate whose
        best confidence meets accept_threshold (Tier 1) or review_threshold
        (Tiers 2/3), stop immediately — do not run lower-priority resolvers.
        This prevents multiple resolvers returning equally-confident candidates
        for the same element, which would trigger AmbiguousTargetError
        incorrectly (the candidates are the same element, not genuinely
        different targets).

        Resolvers are sorted by priority ascending so higher-priority (lower
        number) resolvers get the first opportunity to short-circuit the tier.
        """
        lo, hi = _TIER_RANGES[tier_num]
        tier_resolvers = sorted(
            [r for r in self.registry.eligible_for(intent) if lo <= r.priority <= hi],
            key=lambda r: r.priority,
        )

        stop_threshold = (
            self.accept_threshold if tier_num == 1 else self.review_threshold
        )

        candidates: list[ResolvedTarget] = []
        traces:     list[ResolverTrace]  = []

        for resolver in tier_resolvers:
            t0 = time.monotonic()
            try:
                found = resolver.resolve(intent)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Resolver %s raised an exception: %s", resolver.name, exc)
                found = []

            duration_ms = int((time.monotonic() - t0) * 1000)
            candidates.extend(found)
            traces.append(
                ResolverTrace(
                    resolver_name=resolver.name,
                    duration_ms=duration_ms,
                    candidates=found,
                    can_run=True,
                )
            )
            logger.debug(
                "Tier %s / %s → %d candidates (%.0f ms)",
                tier_num, resolver.name, len(found), duration_ms,
            )

            # Early-exit: a high-confidence match stops the tier so that
            # lower-priority resolvers do not add competing candidates for
            # the same element, which would trigger AmbiguousTargetError.
            if found and self.ranker.best(found).confidence >= stop_threshold:
                logger.debug(
                    "Tier %s early-exit after %s (confidence %.2f >= %.2f)",
                    tier_num, resolver.name,
                    self.ranker.best(found).confidence, stop_threshold,
                )
                break

        return candidates, traces

    def _check_ambiguity(
        self, candidates: list[ResolvedTarget], intent: StepIntent
    ) -> None:
        """
        Raise AmbiguousTargetError if the top 2 candidates are within ambiguous_gap.
        Called only when we're about to return a result — safety gate before execution.

        Skipped for verify/extract: any matching element is acceptable for reading
        actions, so ambiguity between equally-confident candidates is harmless.
        """
        if intent.action_type in ("verify", "extract"):
            return
        ranked = self.ranker.rank(candidates)
        if len(ranked) >= 2:
            gap = ranked[0].confidence - ranked[1].confidence
            if gap < self.ambiguous_gap:
                raise AmbiguousTargetError(
                    step=intent.instruction,
                    candidates=ranked[:2],
                    gap=gap,
                )
