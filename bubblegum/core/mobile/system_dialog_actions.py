from __future__ import annotations

from typing import Any
from xml.etree import ElementTree as ET

_ALLOWED_ACTIONS = {"allow", "deny", "ok", "cancel", "dismiss"}
_UNSAFE_ACTIONS = {"deny", "cancel"}
_SYSTEM_PACKAGE_HINTS = (
    "com.android.permissioncontroller",
    "com.google.android.permissioncontroller",
    "com.android.systemui",
)


def _base_result(requested_action: str) -> dict[str, Any]:
    return {
        "action_requested": requested_action,
        "candidate_found": False,
        "action": requested_action,
        "selector": None,
        "strategy": "unknown",
        "confidence": 0.0,
        "reason": "manual_review_required",
        "evidence": [],
        "warnings": [],
        "safe_metadata_only": True,
    }


def _norm_action(value: str | None) -> str:
    action = str(value or "").strip().lower()
    return action if action in _ALLOWED_ACTIONS else "unknown"


def _parse_bounds(raw: str | None) -> tuple[int, int, int, int] | None:
    text = str(raw or "")
    if "[" not in text or "]" not in text:
        return None
    try:
        left_top, right_bot = text.split("][")
        x1, y1 = left_top.replace("[", "").split(",")
        x2, y2 = right_bot.replace("]", "").split(",")
        return (int(x1), int(y1), int(x2), int(y2))
    except Exception:
        return None


def _inside(inner, outer) -> bool:
    if not inner or not outer:
        return False
    return inner[0] >= outer[0] and inner[1] >= outer[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def _extract_candidates(xml: str, requested_action: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    root = ET.fromstring(xml)
    active_containers: list[dict[str, Any]] = []
    all_buttons: list[dict[str, Any]] = []

    for idx, node in enumerate(root.iter()):
        attrs = node.attrib
        text = str(attrs.get("text") or attrs.get("content-desc") or "").strip().lower()
        rid = str(attrs.get("resource-id") or "").strip().lower()
        cls = str(attrs.get("class") or node.tag or "").strip().lower()
        pkg = str(attrs.get("package") or "").strip().lower()
        bounds = _parse_bounds(attrs.get("bounds"))
        click = str(attrs.get("clickable") or "").lower() == "true"
        enabled = str(attrs.get("enabled") or "").lower() != "false"
        visible = str(attrs.get("displayed") or "true").lower() != "false"

        owner = "system" if any(h in f"{pkg} {rid}" for h in _SYSTEM_PACKAGE_HINTS) else "app"

        if owner == "system" and bounds and any(k in cls for k in ("framelayout", "linearlayout", "dialog", "window")):
            active_containers.append({"bounds": bounds, "idx": idx, "owner": owner, "rid": rid, "class": cls})

        if requested_action in text or requested_action in rid:
            all_buttons.append(
                {
                    "text": text,
                    "rid": rid,
                    "class": cls,
                    "pkg": pkg,
                    "bounds": bounds,
                    "clickable": click,
                    "enabled": enabled,
                    "visible": visible,
                    "owner": owner,
                    "idx": idx,
                }
            )

    # pick topmost system container (highest idx)
    system_containers = [c for c in active_containers if c["owner"] == "system"]
    top_container = max(system_containers, key=lambda x: x["idx"]) if system_containers else None
    safe = []
    rejected = []
    for cand in all_buttons:
        if not (cand["clickable"] and cand["enabled"] and cand["visible"]):
            rejected.append(cand)
            continue
        if cand["owner"] != "system":
            rejected.append(cand)
            continue
        if top_container and not _inside(cand["bounds"], top_container["bounds"]):
            rejected.append(cand)
            continue
        safe.append(cand)
    return safe, rejected


def resolve_system_dialog_action_candidate(*, hierarchy_xml: str | None, system_dialog_detection: dict | None, system_dialog_guardrails: dict | None, requested_action: str, explicit_opt_in: bool = False) -> dict:
    action = _norm_action(requested_action)
    out = _base_result(action)

    det = system_dialog_detection if isinstance(system_dialog_detection, dict) else {}
    guard = system_dialog_guardrails if isinstance(system_dialog_guardrails, dict) else {}

    if action == "unknown":
        out["reason"] = "action_not_requested"
        return out
    if not explicit_opt_in:
        out["reason"] = "opt_in_missing"
        return out
    if guard.get("decision") != "allowed":
        out["reason"] = "guardrails_blocked"
        return out
    if action in _UNSAFE_ACTIONS and guard.get("reason") != "policy_allows":
        out["reason"] = "unsafe_action"
        return out
    if not det.get("dialog_detected"):
        out["reason"] = "no_dialog"
        return out
    if not hierarchy_xml:
        out["reason"] = "insufficient_metadata"
        return out

    try:
        safe, rejected = _extract_candidates(hierarchy_xml, action)
    except Exception:
        out["reason"] = "insufficient_metadata"
        return out

    out["warnings"] = ["background_candidates_rejected"] if rejected else []
    if len(safe) == 1:
        c = safe[0]
        out.update(
            {
                "candidate_found": True,
                "selector": {"by": "xpath", "value": f"//*[@bounds='{c['bounds']}' and (@text or @content-desc)]"},
                "strategy": "resource_id" if c["rid"] else "class_text",
                "confidence": 0.9 if c["rid"] else 0.8,
                "reason": "single_safe_system_dialog_candidate",
                "evidence": [f"dialog:{det.get('dialog_type', 'unknown')}", f"candidate:{action}", "owner:system"],
            }
        )
        return out
    if len(safe) > 1:
        out["reason"] = "manual_review_required"
        out["warnings"] = sorted(set(out["warnings"] + ["multiple_candidates"]))
        return out

    out["reason"] = "manual_review_required"
    out["warnings"] = sorted(set(out["warnings"] + ["no_safe_candidate"]))
    return out


def execute_system_dialog_action(*, driver, candidate: dict, explicit_opt_in: bool = False) -> dict:
    action = _norm_action(candidate.get("action_requested") if isinstance(candidate, dict) else None)
    out = {
        "action_requested": action,
        "candidate_found": bool(candidate.get("candidate_found") if isinstance(candidate, dict) else False),
        "action_attempted": False,
        "action_status": "not_attempted",
        "reason": str(candidate.get("reason") or "manual_review_required") if isinstance(candidate, dict) else "insufficient_metadata",
        "evidence": list(candidate.get("evidence") or []) if isinstance(candidate, dict) else [],
        "warnings": list(candidate.get("warnings") or []) if isinstance(candidate, dict) else [],
        "safe_metadata_only": True,
    }
    if not explicit_opt_in:
        out["reason"] = "opt_in_missing"
        return out
    if not out["candidate_found"]:
        return out
    selector = candidate.get("selector") if isinstance(candidate, dict) else None
    if not isinstance(selector, dict):
        out["reason"] = "insufficient_metadata"
        return out
    try:
        out["action_attempted"] = True
        element = driver.find_element(selector.get("by", "xpath"), selector.get("value", ""))
        element.click()
        out["action_status"] = "clicked"
        out["reason"] = "action_executed"
    except Exception:
        out["action_attempted"] = True
        out["action_status"] = "failed"
        out["reason"] = "action_failed"
        out["warnings"] = sorted(set(out["warnings"] + ["click_failed"]))
    return out
