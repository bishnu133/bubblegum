"""
bubblegum/core/grounding/resolver.py
=====================================
Resolver abstract base class.

Every built-in and community resolver must subclass Resolver and implement resolve().
No other core code changes when a new resolver is added — only a new subclass file.

Phase 0 — contract only. No resolver logic lives here.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from bubblegum.core.schemas import ExecutionOptions, ResolvedTarget, StepIntent

# Cost-level ordering — used by _within_cost_policy()
_COST_ORDER: dict[str, int] = {"low": 0, "medium": 1, "high": 2}


class Resolver(ABC):
    """
    Abstract base for all Bubblegum resolvers.

    Subclasses declare their metadata as class attributes and implement resolve().
    The GroundingEngine uses can_run() to decide whether to invoke a resolver.

    Tier definitions:
      Tier 1  priority 0–39   deterministic  (ExplicitSelector, MemoryCache, A11yTree, ...)
      Tier 2  priority 40–49  fuzzy/semantic  (FuzzyText)
      Tier 3  priority 50+    AI fallback     (LLMGrounding, OCR, VisionModel)
    """

    # --- class-level metadata (override in every subclass) ---
    name:       str       = "base_resolver"
    priority:   int       = 99
    channels:   list[str] = ["web", "mobile"]
    cost_level: str       = "low"    # "low" | "medium" | "high"
    tier:       int       = 1

    # ------------------------------------------------------------------
    # Filtering hooks — override to restrict by action_type or other flags
    # ------------------------------------------------------------------

    def supports(self, intent: StepIntent) -> bool:
        """
        Return False to skip this resolver for unsupported action_types.
        Default: supports all action types.
        Override in subclasses that only handle specific actions (e.g. click, type).
        """
        return True

    def required_context(self) -> list[str]:
        """
        Return the list of UIContext keys this resolver needs in intent.context.
        If any key is missing, can_run() returns False and the resolver is skipped.
        Example: ["a11y_snapshot"] | ["screenshot"] | []
        """
        return []

    def can_run(self, intent: StepIntent) -> bool:
        """
        Gate check called by the GroundingEngine before invoking resolve().

        A resolver is eligible when ALL of:
          1. intent.channel is in self.channels
          2. self.supports(intent) returns True
          3. All required_context() keys exist in intent.context
          4. self.cost_level does not exceed intent.options.max_cost_level
        """
        if intent.channel not in self.channels:
            return False
        if not self.supports(intent):
            return False
        if not all(k in intent.context for k in self.required_context()):
            return False
        if not self._within_cost_policy(intent.options):
            return False
        return True

    def _within_cost_policy(self, options: ExecutionOptions) -> bool:
        """Return True if this resolver's cost_level is within the configured max."""
        resolver_cost = _COST_ORDER.get(self.cost_level, 0)
        policy_max    = _COST_ORDER.get(options.max_cost_level, 1)
        return resolver_cost <= policy_max

    # ------------------------------------------------------------------
    # Core contract — must be implemented by every resolver
    # ------------------------------------------------------------------

    @abstractmethod
    def resolve(self, intent: StepIntent) -> list[ResolvedTarget]:
        """
        Attempt to ground the step intent and return a list of candidate elements.

        Rules:
          - Always return a list — multiple candidates are allowed and expected.
          - Return [] (empty list) if no candidates are found; do NOT raise an error here.
          - Set confidence on each ResolvedTarget to reflect match quality (0.0 – 1.0).
          - The GroundingEngine + CandidateRanker will pick the best across all resolvers.

        Phase 1+: actual matching logic is implemented in each resolver subclass.
        Phase 0: subclasses return [] as a stub.
        """
        ...
