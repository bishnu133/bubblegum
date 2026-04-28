"""
bubblegum/core/grounding/resolvers/ocr.py
OCRResolver stub — Phase 0.

Tesseract/cloud OCR on screenshot. Requires enable_ocr=true. Tier 3 AI fallback.

Phase 0: returns [] — no matching logic yet.
"""

from __future__ import annotations

from bubblegum.core.grounding.resolver import Resolver
from bubblegum.core.schemas import ResolvedTarget, StepIntent


class OCRResolver(Resolver):

    name       = "ocr"
    priority   = 60
    channels   = ['web', 'mobile']
    cost_level = "medium"
    tier       = 3

    def resolve(self, intent: StepIntent) -> list[ResolvedTarget]:
        """Phase 0 stub — implementation in Phase 6."""
        return []
