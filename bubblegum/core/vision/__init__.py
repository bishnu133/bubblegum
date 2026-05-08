"""Vision abstraction primitives (Phase 11B)."""

from .engine import (
    FakeVisionProvider,
    VisionCandidate,
    VisionProvider,
    build_vision_candidates_from_screenshot,
    normalize_vision_candidates,
)

__all__ = [
    "VisionCandidate",
    "VisionProvider",
    "FakeVisionProvider",
    "normalize_vision_candidates",
    "build_vision_candidates_from_screenshot",
]
