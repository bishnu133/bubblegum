"""Phase 19E-B: compact graph-signal metadata helpers (diagnostics only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .graph import ElementGraph
from .normalized import NormalizedElement


_SAFE_EMPTY: dict[str, Any] = {
    "label_for_match": False,
    "same_row_match": False,
    "same_container_match": False,
    "nearby_label_match": False,
    "role_match_with_graph_context": False,
    "unique_in_scope": False,
    "visible_enabled_match": False,
    "score_hint": 0.0,
    "reason": "no_graph_context",
}


@dataclass(frozen=True)
class GraphSignalInput:
    candidate_ref: str
    candidate_text: str = ""
    candidate_role: str = ""
    instruction: str = ""


def _norm(value: str | None) -> str:
    return (value or "").strip().casefold()


def _best_text(element: NormalizedElement) -> str:
    return element.label or element.text or element.accessibility_name or element.content_desc or ""


def _is_labelish(element: NormalizedElement) -> bool:
    role = _norm(element.role)
    tag = _norm(element.tag)
    widget = _norm(element.widget_type)
    return role in {"label", "text", "statictext"} or tag == "label" or widget.endswith("textview")


def _to_bool(value: bool) -> bool:
    return bool(value)


def compute_graph_signals(
    signal_input: GraphSignalInput,
    *,
    graph: ElementGraph | None,
    elements_by_ref: dict[str, NormalizedElement] | None,
) -> dict[str, Any]:
    """Compute compact graph diagnostics only.

    Returns deterministic JSON-safe booleans/small scalars only.
    Never raises; falls back to a safe neutral payload.
    """
    if graph is None or not elements_by_ref:
        return dict(_SAFE_EMPTY)

    element = elements_by_ref.get(signal_input.candidate_ref)
    if element is None:
        payload = dict(_SAFE_EMPTY)
        payload["reason"] = "candidate_not_mapped"
        return payload

    instruction = _norm(signal_input.instruction)
    ctext = _norm(signal_input.candidate_text) or _norm(_best_text(element))
    crole = _norm(signal_input.candidate_role) or _norm(element.role)

    labels = graph.labels_for(element.id)
    label_for_match = any(_norm(_best_text(label)) in instruction and _norm(_best_text(label)) for label in labels)

    same_row = graph.same_row_map.get(element.id, [])
    same_row_match = len(same_row) > 0

    same_container = graph.same_container_map.get(element.id, [])
    same_container_match = len(same_container) > 0

    nearby = graph.nearby(element.id)
    nearby_label_match = any(_is_labelish(n) and _norm(_best_text(n)) in instruction and _norm(_best_text(n)) for n in nearby)

    role_match_with_graph_context = bool(crole) and (
        (crole in {"textbox", "input", "searchbox", "combobox", "spinbutton", "textarea"} and (label_for_match or nearby_label_match))
        or (crole in {"button", "link"} and bool(ctext) and ctext in instruction)
    )

    in_scope = [
        e for e in graph.elements_by_id.values()
        if _norm(_best_text(e)) == ctext and ctext
    ]
    unique_in_scope = len(in_scope) == 1

    visible_enabled_match = _to_bool(element.visible and element.enabled)

    flags = [
        label_for_match,
        same_row_match,
        same_container_match,
        nearby_label_match,
        role_match_with_graph_context,
        unique_in_scope,
        visible_enabled_match,
    ]
    score_hint = round(sum(1.0 for f in flags if f) / len(flags), 3)

    return {
        "label_for_match": bool(label_for_match),
        "same_row_match": bool(same_row_match),
        "same_container_match": bool(same_container_match),
        "nearby_label_match": bool(nearby_label_match),
        "role_match_with_graph_context": bool(role_match_with_graph_context),
        "unique_in_scope": bool(unique_in_scope),
        "visible_enabled_match": bool(visible_enabled_match),
        "score_hint": score_hint,
        "reason": "ok",
    }
