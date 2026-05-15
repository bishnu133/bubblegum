from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

_SAFE_FIELDS = {
    "scroll_needed",
    "status",
    "reason",
    "platform",
    "target_hint_type",
    "scroll_direction",
    "max_scrolls",
    "candidate_container_count",
    "evidence",
    "warnings",
    "safe_metadata_only",
}

_ANDROID_SCROLL_HINTS = ("RecyclerView", "ScrollView", "ListView", "NestedScrollView")
_IOS_SCROLL_HINTS = ("XCUIElementTypeTable", "XCUIElementTypeCollectionView", "XCUIElementTypeScrollView")


def _clamp_max_scrolls(value: int | None) -> int:
    if value is None:
        return 3
    return max(1, min(int(value), 10))


def _infer_target_hint_type(target_hint: str | None, instruction: str | None) -> str:
    hint = (target_hint or "").strip()
    source = hint or (instruction or "").strip()
    lower = source.lower()
    if not source:
        return "unknown"
    if any(tok in lower for tok in ("content-desc", "accessibility", "accessibility id", "a11y")):
        return "content_desc"
    if "resource-id" in lower or re.search(r"\b\w[\w.]*:id/", source):
        return "resource_id"
    if hint and (" " in hint or re.search(r"[A-Za-z]", hint)):
        return "text"
    return "unknown"


def _target_present(hierarchy_xml: str, target_hint: str | None) -> bool:
    if not hierarchy_xml or not target_hint:
        return False
    return target_hint.strip().lower() in hierarchy_xml.lower()


def build_mobile_scroll_discovery_plan(*, instruction: str | None = None, target_hint: str | None = None, hierarchy_xml: str | None = None, platform: str | None = None, app_state: dict | None = None, max_scrolls: int = 3,) -> dict[str, Any]:
    del app_state
    normalized_platform = (platform or "unknown").strip().lower()
    if normalized_platform not in {"android", "ios"}:
        normalized_platform = "unknown"

    plan: dict[str, Any] = {
        "scroll_needed": False,
        "status": "unknown",
        "reason": "insufficient_metadata",
        "platform": normalized_platform,
        "target_hint_type": _infer_target_hint_type(target_hint, instruction),
        "scroll_direction": "unknown",
        "max_scrolls": _clamp_max_scrolls(max_scrolls),
        "candidate_container_count": 0,
        "evidence": [],
        "warnings": [],
        "safe_metadata_only": True,
    }

    if not hierarchy_xml:
        return plan

    try:
        root = ET.fromstring(hierarchy_xml)
    except ET.ParseError:
        plan["warnings"] = ["hierarchy_parse_failed"]
        return plan

    if normalized_platform == "unknown":
        root_tag = (root.tag or "").lower()
        normalized_platform = "ios" if "xcui" in root_tag else "android"
        plan["platform"] = normalized_platform

    hints = _ANDROID_SCROLL_HINTS if normalized_platform == "android" else _IOS_SCROLL_HINTS
    count = 0
    for node in root.iter():
        klass = (node.get("class") or node.tag or "").strip()
        if (node.get("scrollable") or "").lower() == "true" or any(h in klass for h in hints):
            count += 1
    plan["candidate_container_count"] = count

    visible = _target_present(hierarchy_xml, target_hint)
    if visible:
        plan.update({"status": "not_needed", "reason": "target_already_visible", "scroll_needed": False})
        plan["evidence"] = ["target:visible"]
        return {k: v for k, v in plan.items() if k in _SAFE_FIELDS}

    if count <= 0:
        plan.update({"status": "unsupported", "reason": "no_scrollable_container", "scroll_needed": False})
        plan["evidence"] = ["container:none"]
        return {k: v for k, v in plan.items() if k in _SAFE_FIELDS}

    plan.update({"status": "candidate", "reason": "target_not_visible", "scroll_needed": True, "scroll_direction": "down"})
    plan["evidence"] = ["target:not_visible", "container:scrollable", "direction:down"]
    return {k: v for k, v in plan.items() if k in _SAFE_FIELDS}


def execute_bounded_mobile_scroll_search(*, driver, target_hint: str, plan: dict, explicit_opt_in: bool = False) -> dict[str, Any]:
    result = {
        "action_attempted": False,
        "scroll_attempts": 0,
        "target_found": False,
        "status": "blocked" if not explicit_opt_in else "unknown",
        "reason": "opt_in_required" if not explicit_opt_in else "insufficient_metadata",
        "warnings": [],
        "safe_metadata_only": True,
    }
    if not explicit_opt_in:
        return result
    max_scrolls = _clamp_max_scrolls(int(plan.get("max_scrolls", 3))) if isinstance(plan, dict) else 3
    result["action_attempted"] = True
    for idx in range(max_scrolls + 1):
        page_source = ""
        try:
            page_source = getattr(driver, "page_source", "") or ""
        except Exception:
            result["warnings"].append("page_source_unavailable")
        if target_hint and target_hint.lower() in page_source.lower():
            result.update({"target_found": True, "status": "found", "reason": "target_visible", "scroll_attempts": idx})
            return result
        if idx >= max_scrolls:
            break
        try:
            driver.swipe(500, 1500, 500, 700, 300)
        except Exception:
            result["warnings"].append("scroll_action_failed")
            break
    result.update({"status": "not_found", "reason": "max_scrolls_reached", "scroll_attempts": max_scrolls})
    return result
