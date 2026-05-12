from __future__ import annotations

import re
from typing import Any


def infer_action_type(instruction: str, kwargs: dict) -> str:
    """Infer action_type from kwargs or instruction text."""
    if "action_type" in kwargs:
        return kwargs["action_type"]
    lowered = instruction.lower()
    if any(w in lowered for w in ("type", "enter", "fill", "input")):
        return "type"
    if any(w in lowered for w in ("select", "choose", "pick")):
        return "select"
    if any(w in lowered for w in ("scroll",)):
        return "scroll"
    if any(w in lowered for w in ("verify", "check", "assert", "visible", "present")):
        return "verify"
    if any(w in lowered for w in ("extract", "get", "read", "fetch")):
        return "extract"
    return "click"


def extract_expected(instruction: str) -> str:
    """Pull key noun phrase from a verify instruction."""
    return re.sub(
        r"^(verify|check|assert|confirm|ensure|see|that)\s+",
        "",
        instruction,
        flags=re.IGNORECASE,
    ).strip()


def _base_relational_payload() -> dict[str, Any]:
    return {
        "primary_target_text": None,
        "relation_type": "none",
        "anchor_text": None,
        "scope_type": "none",
        "scope_label": None,
        "control_kind_hint": "none",
        "mobile_attr_preference": "none",
        "ambiguity_policy": "fail_on_ambiguous",
    }


def _clean_fragment(value: str | None) -> str | None:
    if value is None:
        return None
    out = value.strip(" .,:;!?\t\n\r\"'")
    out = re.sub(r"\s+", " ", out).strip()
    return out or None


def parse_relational_intent(instruction: str, action_type: str | None = None) -> dict[str, Any] | None:
    """Parse conservative relational metadata hints from instruction text.

    Rule-based only. Returns None if no safe MVP pattern matches.
    """
    text = instruction.strip()
    lowered = text.casefold()

    # Guard: intentionally defer complex nested/multi-anchor relational phrasing.
    if re.search(r"\b(for|from|in)\b.*\b(for|from|in)\b", lowered):
        return None

    # 1) "for <anchor>" => same_row_as_text
    m_for = re.search(r"\bfor\s+(.+?)\s*[\.!?]?\s*$", text, flags=re.IGNORECASE)
    if m_for:
        anchor = _clean_fragment(m_for.group(1))
        if anchor:
            payload = _base_relational_payload()
            payload["relation_type"] = "same_row_as_text"
            payload["anchor_text"] = anchor
            return payload

    # 2) "in the confirmation modal" / "in modal" => within_modal
    m_modal_labeled = re.search(r"\bin\s+(?:the\s+)?(.+?)\s+modal\b", text, flags=re.IGNORECASE)
    if m_modal_labeled:
        label = _clean_fragment(m_modal_labeled.group(1))
        payload = _base_relational_payload()
        payload["relation_type"] = "within_modal"
        payload["scope_type"] = "modal"
        payload["scope_label"] = f"{label} modal" if label else None
        return payload

    if re.search(r"\bin\s+modal\b", lowered):
        payload = _base_relational_payload()
        payload["relation_type"] = "within_modal"
        payload["scope_type"] = "modal"
        return payload

    # 3) "from/in the <label> dropdown" => within_region + dropdown
    m_dropdown = re.search(r"\b(?:from|in)\s+(?:the\s+)?(.+?)\s+dropdown\b", text, flags=re.IGNORECASE)
    if m_dropdown:
        label = _clean_fragment(m_dropdown.group(1))
        if label:
            payload = _base_relational_payload()
            payload["relation_type"] = "within_region"
            payload["scope_type"] = "region"
            payload["scope_label"] = label
            payload["control_kind_hint"] = "dropdown"
            return payload

    # 4) "check <label>" / "checkbox <label>" => label_for + checkbox
    if action_type == "check" or lowered.startswith("check ") or lowered.startswith("checkbox "):
        m_checkbox = re.match(r"^(?:check|checkbox)\s+(.+?)\s*[\.!?]?\s*$", text, flags=re.IGNORECASE)
        if m_checkbox:
            label = _clean_fragment(m_checkbox.group(1))
            if label:
                payload = _base_relational_payload()
                payload["relation_type"] = "label_for"
                payload["control_kind_hint"] = "checkbox"
                payload["primary_target_text"] = label
                payload["scope_type"] = "label"
                return payload

    return None
