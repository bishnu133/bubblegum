"""Internal normalized cross-platform element models (Phase 19C MVP)."""

from .graph import ElementGraph
from .query import build_graph_query_diagnostics
from .normalized import (
    NormalizedBounds,
    NormalizedElement,
    normalize_mobile_hierarchy_node,
    normalize_web_entry,
)

__all__ = [
    "ElementGraph",
    "build_graph_query_diagnostics",
    "NormalizedBounds",
    "NormalizedElement",
    "normalize_web_entry",
    "normalize_mobile_hierarchy_node",
]
