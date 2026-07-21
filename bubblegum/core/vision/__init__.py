"""Vision abstraction primitives (Phase 11B/11F)."""

from .backends import (
    AnthropicVisionProvider,
    CallableVisionProvider,
    HTTPGroundingProvider,
    OpenAIVisionProvider,
)
from .engine import (
    FakeVisionProvider,
    VisionCandidate,
    VisionProvider,
    build_vision_candidates_from_screenshot,
    normalize_vision_candidates,
)
from .factory import get_vision_provider

__all__ = [
    "AnthropicVisionProvider",
    "CallableVisionProvider",
    "HTTPGroundingProvider",
    "OpenAIVisionProvider",
    "VisionCandidate",
    "VisionProvider",
    "FakeVisionProvider",
    "normalize_vision_candidates",
    "build_vision_candidates_from_screenshot",
    "get_vision_provider",
]
