"""Vision abstraction primitives (Phase 11B/11F)."""

from .backends import AnthropicVisionProvider, CallableVisionProvider, OpenAIVisionProvider
from .engine import (
    FakeVisionProvider,
    VisionCandidate,
    VisionProvider,
    build_vision_candidates_from_screenshot,
    normalize_vision_candidates,
)

__all__ = [
    "AnthropicVisionProvider",
    "CallableVisionProvider",
    "OpenAIVisionProvider",
    "VisionCandidate",
    "VisionProvider",
    "FakeVisionProvider",
    "normalize_vision_candidates",
    "build_vision_candidates_from_screenshot",
]
