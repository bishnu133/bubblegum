"""Coordinate-based clicking primitives (X3).

When a vision- or OCR-resolved target cannot be mapped to a real DOM/hierarchy
element — canvas-rendered UIs, image maps, custom-drawn widgets — the only
actionable thing the model gives us is a bounding box. This module turns that
box into a click point and encodes it as an executable ``point://x,y`` ref that
the web/mobile adapters click at directly (mouse click / coordinate tap).

Pure data, no browser/Appium: every function here is unit-testable without a
device. Bounding boxes follow the project convention ``[x1, y1, x2, y2]`` (top-
left / bottom-right, image pixels), matching ``core/vision`` candidates.
"""

from __future__ import annotations

from typing import Any

#: Action types eligible for a blind coordinate click. Typing/selecting need a
#: real element (focus, value), so coordinate fallback is click/tap only.
COORDINATE_CLICK_ACTIONS: frozenset[str] = frozenset({"click", "tap"})

_COORDINATE_SCHEME = "point://"


def is_coordinate_ref(ref: Any) -> bool:
    """Return True when ``ref`` is a ``point://x,y`` coordinate ref."""
    return isinstance(ref, str) and ref.startswith(_COORDINATE_SCHEME)


def coordinate_ref(x: int, y: int) -> str:
    """Encode an ``(x, y)`` click point as a ``point://x,y`` ref."""
    return f"{_COORDINATE_SCHEME}{int(x)},{int(y)}"


def parse_coordinate_ref(ref: Any) -> tuple[int, int] | None:
    """Parse a ``point://x,y`` ref into ``(x, y)``.

    Returns ``None`` for anything that is not a well-formed, non-negative
    coordinate ref (so callers can fail closed rather than click at (0, 0)).
    """
    if not is_coordinate_ref(ref):
        return None
    body = ref[len(_COORDINATE_SCHEME):]
    parts = body.split(",")
    if len(parts) != 2:
        return None
    try:
        x = int(parts[0].strip())
        y = int(parts[1].strip())
    except ValueError:
        return None
    if x < 0 or y < 0:
        return None
    return x, y


def bbox_center(bbox: Any) -> tuple[int, int] | None:
    """Return the integer center ``(x, y)`` of a ``[x1, y1, x2, y2]`` box.

    Returns ``None`` for a malformed box (not 4 numbers), a box with any
    negative coordinate, or a degenerate zero-area box — none of which yield a
    point worth clicking.
    """
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    vals: list[float] = []
    for v in bbox:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return None
        vals.append(float(v))
    x1, y1, x2, y2 = vals
    if min(vals) < 0:
        return None
    lo_x, hi_x = sorted((x1, x2))
    lo_y, hi_y = sorted((y1, y2))
    if hi_x == lo_x or hi_y == lo_y:
        return None
    return int((lo_x + hi_x) / 2), int((lo_y + hi_y) / 2)


def coordinate_ref_from_bbox(bbox: Any) -> str | None:
    """Convenience: bbox → ``point://x,y`` ref (or ``None`` if uncomputable)."""
    center = bbox_center(bbox)
    if center is None:
        return None
    return coordinate_ref(*center)
