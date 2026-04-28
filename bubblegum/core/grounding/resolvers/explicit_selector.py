"""
bubblegum/core/grounding/resolvers/explicit_selector.py
========================================================
ExplicitSelectorResolver — Tier 1, priority 0.

If the caller passes an explicit CSS/XPath/aria selector via
intent.context["explicit_selector"], return it at confidence=1.0 and stop.

This is the highest-priority resolver because an explicit selector is always
the most reliable signal — the test author knows exactly what they want.

Phase 1A — fully implemented.
"""

from __future__ import annotations

from bubblegum.core.grounding.resolver import Resolver
from bubblegum.core.schemas import ResolvedTarget, StepIntent


class ExplicitSelectorResolver(Resolver):
    """
    Returns a pre-supplied selector at confidence 1.0.

    Does NOT override required_context() — it checks intent.context itself
    inside resolve() so that can_run() always returns True and the resolver
    is always eligible. This allows recover() to inject a selector at call
    time rather than requiring it to be present in UIContext upfront.
    """

    name:       str       = "explicit_selector"
    priority:   int       = 0
    channels:   list[str] = ["web", "mobile"]
    cost_level: str       = "low"
    tier:       int       = 1

    # NOTE: required_context() is intentionally NOT overridden.
    # The check is performed inside resolve() instead.

    def resolve(self, intent: StepIntent) -> list[ResolvedTarget]:
        """
        Return the explicit selector at full confidence, or [] if none was supplied.
        """
        selector: str | None = intent.context.get("explicit_selector")
        if not selector:
            return []

        return [
            ResolvedTarget(
                ref=selector,
                confidence=1.0,
                resolver_name=self.name,
                metadata={"source": "explicit_selector"},
            )
        ]
