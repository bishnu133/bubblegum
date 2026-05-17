from __future__ import annotations

import re
from typing import Any

_ICON_SYNONYMS: dict[str, tuple[str, ...]] = {
    "search": ("search", "find", "magnify", "magnifier"),
    "profile": ("profile", "account", "user", "avatar", "person"),
    "cart": ("cart", "bag", "basket"),
    "back": ("back", "arrow_back", "navigate_up", "up"),
    "close": ("close", "dismiss", "cancel", "x"),
    "more": ("more", "menu", "overflow", "kebab", "three", "dots", "three-dot", "three_dots"),
    "settings": ("settings", "setting", "gear", "cog"),
    "delete": ("delete", "trash", "remove", "bin"),
    "edit": ("edit", "pencil", "rename"),
    "add": ("add", "plus", "create", "new"),
    "calendar": ("calendar", "date"),
    "filter": ("filter", "funnel", "sort"),
    "favorite": ("favorite", "favourite", "heart", "star", "bookmark"),
}

_ICON_WIDGET_HINTS = ("imagebutton", "imageview", "icon", "floatingactionbutton")


def _tokenize(value: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", value.lower()) if t}


def _instruction_icon(instruction: str) -> str:
    tokens = _tokenize(instruction)
    for icon, synonyms in _ICON_SYNONYMS.items():
        if any(s in tokens for s in synonyms):
            return icon
    return "unknown"


def _extract_icon_for_element(el: Any) -> tuple[str, str]:
    content_desc = str(getattr(el, "content_desc", "") or "")
    resource_id = str(getattr(el, "resource_id", "") or "")
    widget_type = str(getattr(el, "widget_type", "") or "")
    text = str(getattr(el, "text", "") or "")
    for icon, synonyms in _ICON_SYNONYMS.items():
        if any(s in _tokenize(content_desc) for s in synonyms):
            return icon, "content_desc"
    suffix = resource_id.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    suffix_tokens = _tokenize(suffix)
    for icon, synonyms in _ICON_SYNONYMS.items():
        if any(s in suffix_tokens for s in synonyms):
            return icon, "resource_id"
    if any(h in widget_type.lower() for h in _ICON_WIDGET_HINTS) and not text.strip():
        return "unknown", "class_hint"
    return "unknown", "unknown"


def detect_icon_like_mobile_elements(*, elements: list, platform: str | None = None) -> dict:
    _ = platform
    candidates = []
    for el in elements:
        icon, hint = _extract_icon_for_element(el)
        if hint == "unknown":
            continue
        candidates.append({"ref": getattr(el, "source_ref", None), "target_icon": icon, "icon_hint_type": hint})
    if not candidates:
        return {
            "status": "no_icon_candidate",
            "icon_hint_type": "unknown",
            "target_icon": "unknown",
            "candidate_count": 0,
            "matched_candidate_count": 0,
            "reason": "no_hint_match",
            "evidence": [],
            "warnings": [],
            "safe_metadata_only": True,
            "matched_refs": [],
        }
    return {
        "status": "resolved",
        "icon_hint_type": "unknown",
        "target_icon": "unknown",
        "candidate_count": len(candidates),
        "matched_candidate_count": len(candidates),
        "reason": "icon_candidates_detected",
        "evidence": ["candidate:icon_like"],
        "warnings": [],
        "safe_metadata_only": True,
        "matched_refs": [c["ref"] for c in candidates if c.get("ref")],
        "candidates": candidates,
    }


def resolve_icon_target_hint(*, instruction: str, candidates: list, elements: list, graph=None, repeated_region_diagnostics: dict | None = None) -> dict:
    _ = graph
    target_icon = _instruction_icon(instruction)
    if target_icon == "unknown":
        return {"status": "unsupported", "icon_hint_type": "unknown", "target_icon": "unknown", "candidate_count": len(candidates), "matched_candidate_count": 0, "reason": "no_hint_match", "evidence": [], "warnings": [], "safe_metadata_only": True}

    by_ref = {getattr(el, "source_ref", None): el for el in elements}
    matches: list[tuple[Any, str]] = []
    for cand in candidates:
        ref = getattr(cand, "ref", None)
        el = by_ref.get(ref)
        if el is None:
            continue
        icon, hint = _extract_icon_for_element(el)
        if icon == target_icon:
            matches.append((cand, hint))

    # repeated region tie-break
    if len(matches) > 1 and isinstance(repeated_region_diagnostics, dict) and repeated_region_diagnostics.get("status") == "resolved":
        selected_ref = repeated_region_diagnostics.get("selected_candidate_ref")
        selected = [m for m in matches if getattr(m[0], "ref", None) == selected_ref]
        if len(selected) == 1:
            return {"status": "resolved", "icon_hint_type": "repeated_region", "target_icon": target_icon, "candidate_count": len(candidates), "matched_candidate_count": 1, "reason": "nearby_text_match", "evidence": [f"icon:{target_icon}", "hint:repeated_region", "candidate:single"], "warnings": [], "safe_metadata_only": True, "selected_candidate_ref": selected_ref}

    if len(matches) == 1:
        cand, hint = matches[0]
        return {"status": "resolved", "icon_hint_type": hint, "target_icon": target_icon, "candidate_count": len(candidates), "matched_candidate_count": 1, "reason": f"{hint}_match", "evidence": [f"icon:{target_icon}", f"hint:{hint}", "candidate:single"], "warnings": [], "safe_metadata_only": True, "selected_candidate_ref": getattr(cand, "ref", None)}
    if len(matches) > 1:
        return {"status": "ambiguous", "icon_hint_type": "unknown", "target_icon": target_icon, "candidate_count": len(candidates), "matched_candidate_count": len(matches), "reason": "ambiguous_multiple_icons", "evidence": [f"icon:{target_icon}"], "warnings": [], "safe_metadata_only": True}
    return {"status": "no_icon_candidate", "icon_hint_type": "unknown", "target_icon": target_icon, "candidate_count": len(candidates), "matched_candidate_count": 0, "reason": "no_hint_match", "evidence": [f"icon:{target_icon}"], "warnings": [], "safe_metadata_only": True}
