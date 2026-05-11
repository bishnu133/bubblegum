"""Internal normalized cross-platform element models (Phase 19C MVP)."""

from .normalized import (
    NormalizedBounds,
    NormalizedElement,
    normalize_mobile_hierarchy_node,
    normalize_web_entry,
)

__all__ = [
    "NormalizedBounds",
    "NormalizedElement",
    "normalize_web_entry",
    "normalize_mobile_hierarchy_node",
]
