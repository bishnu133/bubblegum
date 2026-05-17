from __future__ import annotations


def _safe_policy(selection_policy: str | None) -> str:
    value = str(selection_policy or "").strip().lower()
    allowed = {"single_webview_only", "first_available", "hint_match"}
    return value if value in allowed else "unknown"


def _safe_eligibility_decision(webview_switch_eligibility: dict | None) -> str:
    if not isinstance(webview_switch_eligibility, dict):
        return "unknown"
    value = str(webview_switch_eligibility.get("decision") or "").strip().lower()
    allowed = {"allowed", "blocked", "deferred", "unknown"}
    return value if value in allowed else "unknown"


def _safe_webview_count(context_inventory: dict | None) -> int | None:
    if not isinstance(context_inventory, dict):
        return None

    if isinstance(context_inventory.get("webview_count"), int):
        return max(0, int(context_inventory["webview_count"]))
    if isinstance(context_inventory.get("webview_context_count"), int):
        return max(0, int(context_inventory["webview_context_count"]))

    context_types = context_inventory.get("context_types")
    if isinstance(context_types, list):
        return sum(1 for v in context_types if str(v).strip().lower() in {"webview", "webview/chromium"})

    has_webview = context_inventory.get("has_webview")
    if has_webview is None:
        has_webview = context_inventory.get("has_webview_context")
    if isinstance(has_webview, bool):
        return 1 if has_webview else 0

    return None


def select_webview_context(
    *,
    context_inventory: dict | None = None,
    webview_switch_eligibility: dict | None = None,
    selection_policy: str = "single_webview_only",
    preferred_context_hint: str | None = None,
) -> dict:
    policy = _safe_policy(selection_policy)
    eligibility_decision = _safe_eligibility_decision(webview_switch_eligibility)
    webview_count = _safe_webview_count(context_inventory)
    safe_hint = str(preferred_context_hint or "").strip().lower()

    out = {
        "decision": "unknown",
        "reason": "insufficient_metadata",
        "selection_policy": policy,
        "selected_context_type": "unknown",
        "selected_context_index": -1,
        "candidate_context_count": 0,
        "eligibility_decision": eligibility_decision,
        "switch_attempted": False,
        "evidence": [],
        "warnings": [],
        "safe_metadata_only": True,
    }

    if policy == "unknown":
        out["decision"] = "blocked"
        out["reason"] = "unsupported_selection_policy"
        out["warnings"] = ["unsupported_selection_policy"]
        return out

    if eligibility_decision != "allowed":
        out["decision"] = "blocked" if eligibility_decision in {"blocked", "unknown"} else "deferred"
        out["reason"] = "eligibility_not_allowed"
        out["warnings"] = ["eligibility_not_allowed"]
        return out

    if webview_count is None:
        out["reason"] = "context_inventory_missing"
        return out

    out["candidate_context_count"] = webview_count

    if webview_count <= 0:
        out["decision"] = "unknown"
        out["reason"] = "webview_context_missing"
        return out

    if policy == "single_webview_only":
        if webview_count == 1:
            out["decision"] = "selected"
            out["reason"] = "single_webview_available"
            out["selected_context_type"] = "webview"
            out["selected_context_index"] = 0
            return out
        out["decision"] = "deferred"
        out["reason"] = "multiple_webviews_single_policy"
        return out

    if policy == "first_available":
        out["decision"] = "selected"
        out["reason"] = "first_webview_selected"
        out["selected_context_type"] = "webview"
        out["selected_context_index"] = 0
        return out

    if policy == "hint_match":
        if safe_hint in {"webview", "webview/chromium", "index:0", "0", "first"}:
            out["decision"] = "selected"
            out["reason"] = "deterministic_hint_match"
            out["selected_context_type"] = "webview"
            out["selected_context_index"] = 0
            return out
        out["decision"] = "deferred"
        out["reason"] = "hint_match_not_deterministic"
        out["warnings"] = ["hint_match_unresolved"]
        return out

    out["decision"] = "deferred"
    out["reason"] = "selection_policy_not_applied"
    return out
