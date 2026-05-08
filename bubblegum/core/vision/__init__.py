"""Vision abstraction primitives (Phase 11B/11F)."""

from .backends import CallableVisionProvider
from .engine import (
    FakeVisionProvider,
    VisionCandidate,
    VisionProvider,
    build_vision_candidates_from_screenshot,
    normalize_vision_candidates,
)

__all__ = [
    "CallableVisionProvider",
    "VisionCandidate",
    "VisionProvider",
    "FakeVisionProvider",
    "normalize_vision_candidates",
    "build_vision_candidates_from_screenshot",
]
