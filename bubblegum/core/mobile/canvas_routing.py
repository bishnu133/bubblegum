"""Flutter / canvas auto-routing (M-C).

Some apps draw their own UI and expose (almost) nothing to the accessibility
hierarchy: Flutter (without semantics), games and engines (Unity, Cocos, SDL,
raw GL/Surface views), and other custom-drawn surfaces. On those screens the
Appium hierarchy has no grounding-usable text, so text-based resolution finds
nothing — the *only* reliable signal about what's on screen is the pixels.

This module decides, from the hierarchy alone, whether the current screen is such
an opaque/canvas surface and should therefore be grounded by vision/OCR + a tap
coordinate rather than by the hierarchy. The decision is used two ways in the
SDK: to auto-enable the coordinate-tap fallback for that screen, and to drive an
explicit "tap the best on-screen OCR match" resolver when hierarchy grounding
comes back empty.

Pure and side-effect free — no Appium, no device — so every rule here is
unit-testable. The tester never configures any of this: a plain-English step on a
Flutter screen routes to vision automatically.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

# Class/tag tokens that mark a self-drawn surface (substring match, lowercased).
_CANVAS_TOKENS: tuple[str, ...] = (
    "flutterview",
    "surfaceview",
    "glsurfaceview",
    "textureview",
    "unityplayer",
    "gvrlayout",
    "cocos2d",
    "sdlsurface",
    "gameview",
)

# Attributes that carry human-readable / grounding-usable text on either platform.
_TEXT_ATTRS: tuple[str, ...] = ("text", "content-desc", "label", "value", "name")


def _text_and_total_node_counts(hierarchy_xml: str) -> tuple[int, int]:
    """Return (text-bearing node count, total node count) for the hierarchy."""
    if not hierarchy_xml:
        return 0, 0
    try:
        root = ET.fromstring(hierarchy_xml)
    except ET.ParseError:
        return 0, 0
    total = 0
    text_nodes = 0
    for node in root.iter():
        total += 1
        for attr in _TEXT_ATTRS:
            if (node.get(attr) or "").strip():
                text_nodes += 1
                break
    return text_nodes, total


def evaluate_canvas_routing(
    *,
    hierarchy_xml: str | None = None,
    ui_framework: dict | None = None,
    vision_available: bool = False,
    platform: str | None = None,
) -> dict[str, Any]:
    """Decide whether the current screen should be grounded by vision/OCR.

    Routes to vision when the screen is a self-drawn surface that the hierarchy
    can't describe:
      - the UI framework is detected as Flutter, or
      - a canvas/engine surface class is present and the hierarchy has ≤1 text
        node, or
      - the hierarchy has nodes but exposes no grounding text at all, or
      - there is no hierarchy to ground from.

    A hierarchy that exposes real text is left on the normal (native) path.
    Returns a safe-metadata decision dict; never raises.
    """
    del platform  # reserved; detection is hierarchy-driven and platform-neutral
    framework = ""
    if isinstance(ui_framework, dict):
        framework = str(ui_framework.get("framework") or "").strip().lower()

    xml = hierarchy_xml or ""
    xml_lower = xml.lower()
    canvas_hits = [t for t in _CANVAS_TOKENS if t in xml_lower]
    text_nodes, total_nodes = _text_and_total_node_counts(xml)

    route = False
    surface_type = "native"
    reason = "native_hierarchy_has_text"
    evidence: list[str] = []

    if framework == "flutter":
        route, surface_type, reason = True, "flutter", "flutter_detected"
        evidence.append("framework:flutter")
    elif canvas_hits and text_nodes <= 1:
        route, surface_type, reason = True, "canvas", "canvas_surface_no_text"
        evidence += [f"class:{t}" for t in canvas_hits]
    elif total_nodes > 0 and text_nodes == 0:
        route, surface_type, reason = True, "opaque", "no_text_in_hierarchy"
        evidence.append(f"nodes:{total_nodes}")
    elif not xml.strip():
        route, surface_type, reason = True, "unknown", "no_hierarchy"
        evidence.append("hierarchy:absent")

    warnings: list[str] = []
    if route and not vision_available:
        # Actionable: routing wants pixels, but no vision backend is configured.
        warnings.append("vision_backend_not_configured")

    return {
        "route_to_vision": route,
        "surface_type": surface_type,
        "reason": reason,
        "vision_available": bool(vision_available),
        "framework": framework or "unknown",
        "text_node_count": text_nodes,
        "total_node_count": total_nodes,
        "canvas_tokens": sorted(set(canvas_hits)),
        "evidence": sorted(set(evidence)),
        "warnings": warnings,
        "safe_metadata_only": True,
    }


# ----------------------------------------------------------------------
# Candidate selection (tap the best on-screen OCR/vision match)
# ----------------------------------------------------------------------

def _norm(value: str | None) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).split())


def _tokens(value: str | None) -> set[str]:
    return {t for t in _norm(value).split() if t}


def _candidate_field(candidate: Any, name: str) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(name)
    return getattr(candidate, name, None)


def select_canvas_vision_candidate(
    *,
    target_phrase: str | None,
    instruction: str | None,
    vision_candidates: Any,
    min_score: float = 0.5,
) -> dict[str, Any] | None:
    """Pick the on-screen vision/OCR candidate best matching the step's target.

    ``vision_candidates`` is a list of ``VisionCandidate`` objects (or dicts)
    each carrying ``text``/``label`` + a ``[x1,y1,x2,y2]`` ``bbox``. Scores text
    similarity to the target phrase (exact → substring → token overlap) and
    returns the best above ``min_score`` as a small dict, or ``None``. Pure and
    engine-free so it is unit-testable.
    """
    query = (target_phrase or "").strip() or (instruction or "").strip()
    if not query or not vision_candidates:
        return None
    q_norm = _norm(query)
    q_tokens = _tokens(query)
    if not q_tokens:
        return None

    best: dict[str, Any] | None = None
    best_effective = 0.0
    for candidate in vision_candidates:
        text = _candidate_field(candidate, "text") or _candidate_field(candidate, "label") or ""
        bbox = _candidate_field(candidate, "bbox")
        if not isinstance(text, str) or not text.strip() or not bbox:
            continue
        t_norm = _norm(text)
        t_tokens = _tokens(text)
        if not t_tokens:
            continue

        if q_norm == t_norm:
            score = 1.0
        elif t_norm in q_norm or q_norm in t_norm:
            score = 0.9
        else:
            overlap = len(q_tokens & t_tokens)
            if overlap == 0:
                continue
            score = 0.6 * (overlap / len(q_tokens)) + 0.4 * (overlap / len(t_tokens))

        if score < min_score:
            continue
        try:
            conf = float(_candidate_field(candidate, "confidence") or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        # Tie-break on OCR confidence without letting it overtake a better text score.
        effective = score + min(max(conf, 0.0), 1.0) * 0.001
        if effective > best_effective:
            best_effective = effective
            best = {
                "text": text.strip(),
                "bbox": [int(v) for v in bbox],
                "confidence": round(conf, 4),
                "score": round(score, 4),
            }
    return best
