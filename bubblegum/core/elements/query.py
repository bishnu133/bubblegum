"""Phase 19G-I: metadata-only graph query diagnostics helper."""

from __future__ import annotations

from typing import Any

from .graph import ElementGraph
from .normalized import NormalizedElement

_SUPPORTED_RELATIONS = {
    "none",
    "label_for",
    "same_row_as_text",
    "within_card",
    "within_modal",
    "within_region",
    "mobile_attr_hint",
}


class ControlKind:
    """Phase 22D-1: closed vocabulary of `control_kind_hint` values.

    String-valued so existing dict-based payloads continue to work without
    migration. `SELECT` is an alias of `DROPDOWN` accepted on input; matchers
    normalize it to `DROPDOWN`. `COMBOBOX` is intentionally narrower than
    `DROPDOWN` — it matches only `role=combobox`, while `DROPDOWN` also
    matches native `<select>` and widget-type spinners.
    """

    NONE = "none"
    BUTTON = "button"
    INPUT = "input"
    DROPDOWN = "dropdown"
    SELECT = "select"
    COMBOBOX = "combobox"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    LINK = "link"
    DIALOG = "dialog"
    TAB = "tab"
    SWITCH = "switch"


KNOWN_CONTROL_KINDS = frozenset({
    ControlKind.NONE,
    ControlKind.BUTTON,
    ControlKind.INPUT,
    ControlKind.DROPDOWN,
    ControlKind.SELECT,
    ControlKind.COMBOBOX,
    ControlKind.CHECKBOX,
    ControlKind.RADIO,
    ControlKind.LINK,
    ControlKind.DIALOG,
    ControlKind.TAB,
    ControlKind.SWITCH,
})


def _empty_payload(*, status: str = "no_relation", relation_type: str = "none", reasons: list[str] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "relation_type": relation_type,
        "anchor_resolution": {"status": "not_required", "anchor_text": None, "anchor_ids": [], "reason": "not_required"},
        "scope_resolution": {
            "status": "not_required",
            "scope_type": "none",
            "scope_label": None,
            "scope_ids": [],
            "reason": "not_required",
        },
        "matched_ids": [],
        "excluded_ids": [],
        "ambiguity": {"is_ambiguous": False, "kind": "none", "candidate_ids": []},
        "reasons": sorted(set(reasons or [])),
    }


def _norm(value: Any) -> str:
    return (value or "").strip().casefold()


def _best_text(e: NormalizedElement) -> str:
    return e.label or e.text or e.accessibility_name or e.content_desc or ""


def _iter_descendants(graph: ElementGraph, root_id: str) -> list[str]:
    out: set[str] = set()
    stack = list(graph.parent_to_children.get(root_id, []))
    while stack:
        current = stack.pop()
        if current in out:
            continue
        out.add(current)
        stack.extend(graph.parent_to_children.get(current, []))
    return sorted(out)


def _match_control_kind(elements: list[NormalizedElement], hint: str, action_type: str | None) -> tuple[list[str], list[str]]:
    kind = _norm(hint)
    if kind == ControlKind.SELECT:
        kind = ControlKind.DROPDOWN
    action = _norm(action_type)
    if kind == "none" and action in {"type", "select", "check"}:
        kind = {"type": "input", "select": "dropdown", "check": "checkbox"}.get(action, "none")

    def ok(e: NormalizedElement) -> bool:
        role = _norm(e.role)
        tag = _norm(e.tag)
        widget = _norm(e.widget_type)
        attr_type = _norm(e.attributes.get("type"))
        attr_role = _norm(e.attributes.get("role"))
        if kind == "none":
            return True
        if kind == "button":
            return role in {"button", "link"} or tag == "button" or "button" in widget
        if kind == "input":
            return role in {"textbox", "input", "searchbox", "textarea", "combobox", "spinbutton"} or tag in {"input", "textarea"} or "edittext" in widget
        if kind == "dropdown":
            return role in {"combobox"} or tag == "select" or any(t in widget for t in {"spinner", "dropdown", "select"})
        if kind == "combobox":
            return role == "combobox" or attr_role == "combobox"
        if kind == "checkbox":
            return role == "checkbox" or (tag == "input" and attr_type == "checkbox") or "checkbox" in widget
        if kind == "radio":
            return role == "radio" or attr_role == "radio" or (tag == "input" and attr_type == "radio") or "radio" in widget
        if kind == "link":
            return role == "link" or tag == "a" or attr_role == "link"
        if kind == "dialog":
            return role in {"dialog", "alertdialog"} or attr_role in {"dialog", "alertdialog"} or any(t in widget for t in {"dialog", "modal"})
        if kind == "tab":
            return role == "tab" or attr_role == "tab"
        if kind == "switch":
            return role == "switch" or attr_role == "switch" or "switch" in widget
        return True

    matched = sorted({e.id for e in elements if ok(e)})
    excluded = sorted({e.id for e in elements if not ok(e)})
    return matched, excluded


def _container_type_score(e: NormalizedElement, mode: str) -> int:
    tokens = " ".join([_norm(e.role), _norm(e.tag), _norm(e.widget_type), _norm(e.attributes.get("class")), _norm(e.metadata.get("class"))])
    if mode == "card":
        hints = ["card", "panel", "listitem", "group"]
    elif mode == "modal":
        hints = ["dialog", "modal", "alertdialog", "sheet", "popup"]
    else:
        hints = ["region", "group", "fieldset", "section", "form"]
    return sum(1 for h in hints if h in tokens)


def _resolve_anchor(graph: ElementGraph, text: str | None) -> tuple[str, list[NormalizedElement], str]:
    anchor = (text or "").strip()
    if not anchor:
        return "missing", [], "missing_anchor_text"
    matches = graph.elements_with_text(anchor)
    if not matches:
        return "missing", [], "anchor_not_found"
    return "resolved", matches, "ok"


def build_graph_query_diagnostics(
    graph: ElementGraph | None,
    relational_intent: dict[str, Any] | None,
    *,
    action_type: str | None = None,
) -> dict[str, Any]:
    if graph is None or not relational_intent:
        return _empty_payload(status="no_relation", relation_type="none", reasons=["missing_graph_or_relational_intent"])

    relation_type = _norm(relational_intent.get("relation_type") or "none")
    if relation_type not in _SUPPORTED_RELATIONS:
        return _empty_payload(status="unsupported", relation_type=relation_type or "none", reasons=["unsupported_relation"])
    if relation_type == "none":
        return _empty_payload(status="no_relation", relation_type="none", reasons=["relation_none"])

    payload = _empty_payload(status="no_match", relation_type=relation_type)
    payload["anchor_resolution"] = {"status": "not_required", "anchor_text": None, "anchor_ids": [], "reason": "not_required"}
    payload["scope_resolution"] = {"status": "not_required", "scope_type": _norm(relational_intent.get("scope_type") or "none") or "none", "scope_label": relational_intent.get("scope_label"), "scope_ids": [], "reason": "not_required"}

    if relation_type == "mobile_attr_hint":
        pref = _norm(relational_intent.get("mobile_attr_preference") or "none")
        ids = sorted(graph.elements_by_id.keys())
        payload["status"] = "ok" if ids else "no_match"
        payload["matched_ids"] = ids
        payload["reasons"] = [f"mobile_attr_preference:{pref}"]
        return payload

    if relation_type == "label_for":
        anchor_text = relational_intent.get("primary_target_text") or relational_intent.get("anchor_text")
        status, anchors, reason = _resolve_anchor(graph, anchor_text)
        payload["anchor_resolution"] = {"status": status, "anchor_text": anchor_text, "anchor_ids": sorted([a.id for a in anchors]), "reason": reason}
        if status != "resolved":
            payload["status"] = "no_anchor"
            payload["reasons"] = [reason]
            return payload
        controls = graph.controls_for_label(str(anchor_text))
        if not controls:
            payload["status"] = "no_match"
            payload["reasons"] = ["no_controls_for_label"]
            return payload
        if len(anchors) > 1:
            payload["status"] = "ambiguous"
            payload["ambiguity"] = {"is_ambiguous": True, "kind": "anchor", "candidate_ids": sorted([a.id for a in anchors])}
            payload["reasons"] = ["multiple_label_anchors"]
            return payload
        matched, excluded = _match_control_kind(controls, str(relational_intent.get("control_kind_hint") or "none"), action_type)
        payload["matched_ids"] = matched
        payload["excluded_ids"] = excluded
        payload["status"] = "ok" if matched else "no_match"
        payload["reasons"] = ["ok" if matched else "control_kind_filtered_all"]
        return payload

    if relation_type == "same_row_as_text":
        anchor_text = relational_intent.get("anchor_text")
        status, anchors, reason = _resolve_anchor(graph, anchor_text)
        payload["anchor_resolution"] = {"status": status, "anchor_text": anchor_text, "anchor_ids": sorted([a.id for a in anchors]), "reason": reason}
        if status != "resolved":
            payload["status"] = "no_anchor"
            payload["reasons"] = [reason]
            return payload
        if len(anchors) > 1:
            payload["status"] = "ambiguous"
            payload["ambiguity"] = {"is_ambiguous": True, "kind": "anchor", "candidate_ids": sorted([a.id for a in anchors])}
            payload["reasons"] = ["multiple_anchor_matches"]
            return payload
        peer_ids = sorted(graph.same_row_map.get(anchors[0].id, []))
        peers = [graph.get_element(i) for i in peer_ids if graph.get_element(i)]
        matched, excluded = _match_control_kind(peers, str(relational_intent.get("control_kind_hint") or "none"), action_type)
        payload["matched_ids"] = matched
        payload["excluded_ids"] = excluded
        payload["status"] = "ok" if matched else "no_match"
        payload["reasons"] = ["ok" if matched else "no_same_row_match"]
        return payload

    # scope-based relations
    mode = {"within_card": "card", "within_modal": "modal", "within_region": "region"}[relation_type]
    scope_label = (relational_intent.get("scope_label") or relational_intent.get("anchor_text") or "").strip()
    scope_candidates: list[str] = []
    if scope_label:
        scope_candidates = [e.id for e in graph.elements_with_text(scope_label) if _container_type_score(e, mode) > 0]
    if not scope_candidates and relational_intent.get("anchor_text"):
        _, anchors, _ = _resolve_anchor(graph, relational_intent.get("anchor_text"))
        for anchor in anchors:
            cur = anchor.id
            while cur in graph.child_to_parent:
                parent = graph.child_to_parent[cur]
                pe = graph.get_element(parent)
                if pe and _container_type_score(pe, mode) > 0:
                    scope_candidates.append(parent)
                    break
                cur = parent
    scope_candidates = sorted(set(scope_candidates))
    payload["scope_resolution"] = {
        "status": "resolved" if scope_candidates else "missing",
        "scope_type": mode,
        "scope_label": scope_label or None,
        "scope_ids": scope_candidates,
        "reason": "ok" if scope_candidates else "scope_not_found",
    }
    if not scope_candidates:
        payload["status"] = "no_scope"
        payload["reasons"] = ["scope_not_found"]
        return payload
    if len(scope_candidates) > 1:
        payload["status"] = "ambiguous"
        payload["ambiguity"] = {"is_ambiguous": True, "kind": "scope", "candidate_ids": scope_candidates}
        payload["reasons"] = ["multiple_scope_candidates"]
        return payload

    descendants = _iter_descendants(graph, scope_candidates[0])
    elements = [graph.get_element(i) for i in descendants if graph.get_element(i)]
    matched, excluded = _match_control_kind(elements, str(relational_intent.get("control_kind_hint") or "none"), action_type)
    payload["matched_ids"] = matched
    payload["excluded_ids"] = excluded
    payload["status"] = "ok" if matched else "no_match"
    payload["reasons"] = ["ok" if matched else "scope_has_no_matches"]
    return payload
