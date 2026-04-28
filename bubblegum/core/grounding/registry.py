"""
bubblegum/core/grounding/registry.py
======================================
ResolverRegistry — maintains the ordered list of resolvers available to the GroundingEngine.

Built-in resolvers are registered at import time via _register_builtins().
Custom resolvers (community packages, project-specific) are registered via register().

Phase 0 — skeleton only. Resolver stubs exist but contain no logic.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bubblegum.core.grounding.resolver import Resolver
from bubblegum.core.schemas import StepIntent

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class ResolverRegistry:
    """
    Maintains an ordered collection of Resolver instances.

    Resolvers are always stored sorted by priority (ascending — lower runs first).
    The GroundingEngine calls eligible_for(intent) to get the filtered, sorted list
    for each step.

    Usage:
        registry = ResolverRegistry()
        registry.register(MaterialUIResolver())   # custom resolver
        resolvers = registry.eligible_for(intent)
    """

    def __init__(self) -> None:
        self._resolvers: list[Resolver] = []
        _register_builtins(self)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, resolver: Resolver) -> None:
        """
        Register a resolver instance.

        Inserts in priority order. If a resolver with the same name is already
        registered, it is replaced (allows override of built-in resolvers).
        """
        # Remove existing resolver with same name (deduplication / override)
        self._resolvers = [r for r in self._resolvers if r.name != resolver.name]
        self._resolvers.append(resolver)
        self._resolvers.sort(key=lambda r: r.priority)
        logger.debug("Registered resolver: %s (priority=%s, tier=%s)", resolver.name, resolver.priority, resolver.tier)

    def unregister(self, name: str) -> None:
        """Remove a resolver by name. No-op if not found."""
        before = len(self._resolvers)
        self._resolvers = [r for r in self._resolvers if r.name != name]
        if len(self._resolvers) < before:
            logger.debug("Unregistered resolver: %s", name)

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def eligible_for(self, intent: StepIntent) -> list[Resolver]:
        """
        Return all resolvers that can_run() for the given intent, sorted by priority.
        The GroundingEngine iterates this list in order, tier by tier.
        """
        eligible = [r for r in self._resolvers if r.can_run(intent)]
        logger.debug(
            "Eligible resolvers for '%s' (channel=%s): %s",
            intent.instruction,
            intent.channel,
            [r.name for r in eligible],
        )
        return eligible

    def get_by_tier(self, intent: StepIntent, tier: int) -> list[Resolver]:
        """Return eligible resolvers filtered to a specific tier."""
        return [r for r in self.eligible_for(intent) if r.tier == tier]

    def get(self, name: str) -> Resolver | None:
        """Return a registered resolver by name, or None."""
        return next((r for r in self._resolvers if r.name == name), None)

    def all(self) -> list[Resolver]:
        """Return all registered resolvers in priority order (for inspection/debugging)."""
        return list(self._resolvers)

    def __repr__(self) -> str:
        names = [f"{r.name}(p={r.priority},t={r.tier})" for r in self._resolvers]
        return f"ResolverRegistry([{', '.join(names)}])"


# ---------------------------------------------------------------------------
# Built-in resolver registration
# ---------------------------------------------------------------------------

def _register_builtins(registry: ResolverRegistry) -> None:
    """
    Import and register all 9 built-in resolver stubs.
    Imported lazily here to avoid circular imports at module load time.

    Phase 0: each resolver stub returns [] from resolve(). Logic added in Phase 1/2/3.
    """
    from bubblegum.core.grounding.resolvers.explicit_selector  import ExplicitSelectorResolver
    from bubblegum.core.grounding.resolvers.memory_cache        import MemoryCacheResolver
    from bubblegum.core.grounding.resolvers.accessibility_tree  import AccessibilityTreeResolver
    from bubblegum.core.grounding.resolvers.appium_hierarchy    import AppiumHierarchyResolver
    from bubblegum.core.grounding.resolvers.exact_text          import ExactTextResolver
    from bubblegum.core.grounding.resolvers.fuzzy_text          import FuzzyTextResolver
    from bubblegum.core.grounding.resolvers.llm_grounding       import LLMGroundingResolver
    from bubblegum.core.grounding.resolvers.ocr                 import OCRResolver
    from bubblegum.core.grounding.resolvers.vision_model        import VisionModelResolver

    for resolver_cls in [
        ExplicitSelectorResolver,
        MemoryCacheResolver,
        AccessibilityTreeResolver,
        AppiumHierarchyResolver,
        ExactTextResolver,
        FuzzyTextResolver,
        LLMGroundingResolver,
        OCRResolver,
        VisionModelResolver,
    ]:
        registry.register(resolver_cls())
