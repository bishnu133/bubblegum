from __future__ import annotations


def _safe_surface(framework_detection: dict | None) -> str:
    if not isinstance(framework_detection, dict):
        return "unknown"
    value = str(framework_detection.get("surface_type") or "").strip().lower()
    allowed = {"android_native", "ios_native", "webview", "hybrid", "system_dialog", "unknown"}
    return value if value in allowed else "unknown"


def _safe_dryrun_status(webview_switch_diagnostics: dict | None) -> str:
    if not isinstance(webview_switch_diagnostics, dict):
        return "unknown"
    value = str(webview_switch_diagnostics.get("status") or "").strip().lower()
    allowed = {"webview_candidate", "hybrid_candidate", "native_only", "not_applicable", "unsupported", "unknown"}
    return value if value in allowed else "unknown"


def _web_like_hint(action_type: str | None, target_hint: str | None) -> str:
    action = str(action_type or "").strip().lower()
    target = str(target_hint or "").strip().lower()
    blob = f"{action} {target}".strip()
    if not blob:
        return "none"
    strong_web = ("web", "url", "link", "browser", "html", "dom", "http", "https")
    strong_native = ("native", "system dialog", "permission", "alert", "popup")
    if any(tok in blob for tok in strong_web):
        return "web"
    if any(tok in blob for tok in strong_native):
        return "native"
    return "weak"


def evaluate_webview_switch_guardrails(
    *,
    context_inventory: dict | None = None,
    framework_detection: dict | None = None,
    webview_switch_diagnostics: dict | None = None,
    action_type: str | None = None,
    target_hint: str | None = None,
    explicit_opt_in: bool = False,
) -> dict:
    inv = context_inventory if isinstance(context_inventory, dict) else {}
    surface = _safe_surface(framework_detection)
    dryrun_status = _safe_dryrun_status(webview_switch_diagnostics)
    has_webview = bool(inv.get("has_webview_context"))
    webview_count = int(inv.get("webview_context_count") or 0)
    hint_class = _web_like_hint(action_type, target_hint)

    evidence: list[str] = [f"surface:{surface}", f"dryrun:{dryrun_status}"]
    evidence.append("ctx:webview_present" if has_webview else "ctx:webview_missing")
    evidence.append("hint:web" if hint_class == "web" else f"hint:{hint_class}")
    if webview_count > 1:
        evidence.append("ctx:webview_multiple")

    result = {
        "decision": "blocked",
        "reason": "opt_in_missing",
        "eligible_surface": surface in {"webview", "hybrid"},
        "requires_opt_in": True,
        "opt_in_present": bool(explicit_opt_in),
        "switch_attempted": False,
        "recommended_context": "native",
        "evidence": sorted(set(evidence)),
        "warnings": [],
        "safe_metadata_only": True,
    }

    if not context_inventory and not framework_detection and not webview_switch_diagnostics:
        result["decision"] = "unknown"
        result["reason"] = "insufficient_metadata"
        result["recommended_context"] = "unknown"
        return result

    if surface == "system_dialog":
        result["decision"] = "unsupported"
        result["reason"] = "system_dialog_surface"
        return result

    if surface == "unknown":
        if has_webview:
            result["decision"] = "blocked"
            result["reason"] = "unknown_surface"
        else:
            result["decision"] = "unsupported"
            result["reason"] = "unknown_surface"
        result["recommended_context"] = "unknown"
        return result

    if surface in {"android_native", "ios_native"}:
        result["decision"] = "blocked"
        result["reason"] = "surface_not_eligible"
        return result

    if not explicit_opt_in:
        return result

    if dryrun_status in {"native_only", "not_applicable", "unsupported", "unknown"}:
        result["decision"] = "blocked"
        result["reason"] = "dry_run_not_candidate"
        return result

    if not has_webview:
        result["decision"] = "unsupported"
        result["reason"] = "webview_context_missing"
        return result

    if webview_count > 1:
        result["decision"] = "deferred"
        result["reason"] = "insufficient_metadata"
        result["recommended_context"] = "webview"
        result["warnings"] = ["multiple_webview_contexts_no_selection_policy"]
        return result

    if hint_class in {"weak", "none"} and (action_type or target_hint):
        result["decision"] = "deferred"
        result["reason"] = "web_like_hint_missing"
        result["recommended_context"] = "webview"
        return result

    if hint_class == "native":
        result["decision"] = "blocked"
        result["reason"] = "surface_not_eligible"
        return result

    result["decision"] = "allowed"
    result["reason"] = "eligible_hybrid" if surface == "hybrid" else "eligible_webview"
    result["recommended_context"] = "webview"
    return result
