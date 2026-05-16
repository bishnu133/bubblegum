from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from bubblegum.core.elements.normalized import NormalizedElement

_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}


def _parse_instruction(instruction: str) -> dict[str, Any]:
    s = (instruction or "").strip().lower()
    action = None
    for verb in ("view details", "edit", "delete", "add", "status"):
        if verb in s:
            action = verb
            break

    ordinal = None
    for word, value in _ORDINALS.items():
        if re.search(rf"\b{word}\b", s):
            ordinal = value
            break

    anchor = None
    hint_type = "ordinal" if ordinal is not None else "none"
    if ordinal is None:
        for token in (" same row as ", " for ", " near "):
            if token in s:
                anchor = s.split(token, 1)[1].strip()
                hint_type = "text"
                break

    if anchor:
        anchor = re.sub(r"\b(row|card|item)\b$", "", anchor).strip()

    return {"action": action or "unknown", "anchor": anchor, "anchor_hint_type": hint_type, "ordinal": ordinal}


def detect_repeated_mobile_regions(*, elements: list, platform: str | None = None) -> dict:
    normalized: list[NormalizedElement] = [e for e in elements if isinstance(e, NormalizedElement)]
    by_id = {e.id: e for e in normalized}
    children_by_parent: dict[str, list[NormalizedElement]] = defaultdict(list)
    for el in normalized:
        if el.parent_id:
            children_by_parent[el.parent_id].append(el)

    repeated_parent_ids = [pid for pid, kids in children_by_parent.items() if len(kids) >= 2]
    repeated_parent_set = set(repeated_parent_ids)
    top_level_repeated_parent_ids = [
        pid for pid in repeated_parent_ids
        if not (by_id.get(pid) and by_id[pid].parent_id in repeated_parent_set)
    ]
    if not repeated_parent_ids:
        return {"status": "no_repeated_region", "region_type": "unknown", "matched_region_count": 0, "regions": [], "safe_metadata_only": True}

    regions: list[dict[str, Any]] = []
    for pid in top_level_repeated_parent_ids:
        parent = by_id.get(pid)
        parent_widget = (parent.widget_type or "").lower() if parent else ""
        if "card" in parent_widget:
            region_type = "card"
        elif "recyclerview" in parent_widget or "listview" in parent_widget:
            region_type = "list_item"
        else:
            region_type = "row"

        for child in children_by_parent[pid]:
            refs = []
            if child.source_ref:
                refs.append(child.source_ref)
            stack = [child]
            while stack:
                cur = stack.pop()
                for grand in children_by_parent.get(cur.id, []):
                    if grand.source_ref:
                        refs.append(grand.source_ref)
                    stack.append(grand)
            regions.append({"region_id": child.id, "region_type": region_type, "child_refs": sorted(set(refs))})

    return {
        "status": "resolved" if regions else "no_repeated_region",
        "region_type": regions[0]["region_type"] if regions else "unknown",
        "matched_region_count": len(top_level_repeated_parent_ids),
        "regions": regions,
        "safe_metadata_only": True,
    }


def disambiguate_within_repeated_region(*, instruction: str, target_candidates: list, anchor_candidates: list, elements: list, graph=None) -> dict:
    parsed = _parse_instruction(instruction)
    result = {
        "status": "unknown",
        "region_type": "unknown",
        "matched_region_count": 0,
        "candidate_count": len(target_candidates),
        "anchor_hint_type": parsed["anchor_hint_type"],
        "target_action_hint": parsed["action"],
        "reason": "unsupported",
        "evidence": [],
        "warnings": [],
        "safe_metadata_only": True,
    }

    if len(target_candidates) <= 1:
        result.update({"status": "unsupported", "reason": "single_candidate"})
        return result

    detection = detect_repeated_mobile_regions(elements=elements)
    result["region_type"] = detection.get("region_type", "unknown")
    result["matched_region_count"] = int(detection.get("matched_region_count", 0))
    regions = detection.get("regions", [])
    if not regions:
        result.update({"status": "no_repeated_region", "reason": "no_repeated_region"})
        return result

    if parsed.get("ordinal") is not None:
        idx = parsed["ordinal"] - 1
        if idx < 0 or idx >= len(regions):
            result.update({"status": "ambiguous", "reason": "ambiguous_multiple_regions"})
            return result
        chosen_region = regions[idx]
        result["evidence"].append("anchor:ordinal")
    elif parsed.get("anchor"):
        by_ref = {e.source_ref: e for e in elements if isinstance(e, NormalizedElement) and e.source_ref}
        matched = []
        needle = parsed["anchor"].lower()
        for region in regions:
            text_parts = []
            for ref in region.get("child_refs", []):
                el = by_ref.get(ref)
                if not el:
                    continue
                text_parts.append((el.text or "") + " " + (el.content_desc or ""))
            haystack = " ".join(text_parts).lower()
            if needle and needle in haystack:
                matched.append(region)
        result["evidence"].append("anchor:text")
        if not matched:
            result.update({"status": "no_anchor", "reason": "anchor_not_found"})
            return result
        if len(matched) > 1:
            result.update({"status": "ambiguous", "reason": "ambiguous_multiple_regions"})
            return result
        chosen_region = matched[0]
    else:
        result.update({"status": "no_anchor", "reason": "anchor_not_found"})
        return result

    region_refs = set(chosen_region.get("child_refs", []))
    matches = [candidate for candidate in target_candidates if candidate.ref in region_refs]
    if len(matches) != 1:
        result.update({"status": "ambiguous", "reason": "target_not_in_region"})
        return result

    result.update({
        "status": "resolved",
        "matched_region_count": 1,
        "selected_candidate_ref": matches[0].ref,
        "reason": "same_region_anchor_match",
    })
    result["evidence"].extend([f"region:{chosen_region.get('region_type', 'unknown')}", "relation:same_region"])
    return result
