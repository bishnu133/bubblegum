"""Internal normalized cross-platform element models (Phase 19C MVP)."""

from .graph import ElementGraph
from .query import ControlKind, KNOWN_CONTROL_KINDS, build_graph_query_diagnostics
from .normalized import (
    NormalizedBounds,
    NormalizedElement,
    normalize_mobile_hierarchy_node,
    normalize_web_entry,
)

__all__ = [
    "ControlKind",
    "ElementGraph",
    "KNOWN_CONTROL_KINDS",
    "build_graph_query_diagnostics",
    "NormalizedBounds",
    "NormalizedElement",
    "normalize_web_entry",
    "normalize_mobile_hierarchy_node",
]
