"""
bubblegum/core/grounding/resolvers/vision_model.py
VisionModelResolver stub — Phase 0.

Screenshot to multimodal vision model to bounding-box coords. Requires enable_vision + send_screenshots. Tier 3.

Phase 0: returns [] — no matching logic yet.
"""

from __future__ import annotations

from bubblegum.core.grounding.resolver import Resolver
from bubblegum.core.schemas import ResolvedTarget, StepIntent


class VisionModelResolver(Resolver):

    name       = "vision_model"
    priority   = 70
    channels   = ['web', 'mobile']
    cost_level = "high"
    tier       = 3

    def resolve(self, intent: StepIntent) -> list[ResolvedTarget]:
        """Phase 0 stub — implementation in Phase 6."""
        return []
