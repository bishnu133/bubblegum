from __future__ import annotations


def _safe_surface(framework_detection: dict | None) -> str:
    if not isinstance(framework_detection, dict):
        return "unknown"
    value = str(framework_detection.get("surface_type") or "").strip().lower()
    allowed = {"android_native", "ios_native", "webview", "hybrid", "system_dialog", "unknown"}
    return value if value in allowed else "unknown"


def _instruction_hint_type(instruction: str | None) -> str:
    text = str(instruction or "").strip().lower()
    if not text:
        return "unknown"

    web_like = ("link", "href", "css", "input", "textbox", "webview", "html", "field", "button inside webview")
    native_like = ("permission", "allow", "deny", "system dialog", "native back")
    weak = ("tap continue", "click ok", "select item")

    if any(token in text for token in native_like):
        return "native_like"
    if any(token in text for token in web_like):
        return "web_like"
    if any(token in text for token in weak):
        return "weak"
    return "unknown"


def _diagnostics_candidate(diagnostics: dict | None) -> bool:
    if not isinstance(diagnostics, dict):
        return False
    return str(diagnostics.get("status") or "").strip().lower() in {"webview_candidate", "hybrid_candidate"}


def evaluate_webview_switch_eligibility(
    *,
    instruction: str | None = None,
    context_inventory: dict | None = None,
    framework_detection: dict | None = None,
    webview_switch_diagnostics: dict | None = None,
    webview_switch_guardrails: dict | None = None,
    system_dialog_detection: dict | None = None,
    explicit_opt_in: bool = False,
    mode: str = "dry_run",
) -> dict:
    inv = context_inventory if isinstance(context_inventory, dict) else {}
    surface = _safe_surface(framework_detection)
    hint_type = _instruction_hint_type(instruction)
    guardrails_decision = str((webview_switch_guardrails or {}).get("decision") or "").strip().lower() if isinstance(webview_switch_guardrails, dict) else "unknown"
    guardrails_allowed = guardrails_decision == "allowed"
    diagnostics_candidate = _diagnostics_candidate(webview_switch_diagnostics)
    webview_context_available = bool(inv.get("has_webview_context"))
    multi_webview = int(inv.get("webview_context_count") or 0) > 1

    dialog_detected = bool((system_dialog_detection or {}).get("dialog_detected")) if isinstance(system_dialog_detection, dict) else False
    dialog_owner = str((system_dialog_detection or {}).get("owner") or "").strip().lower() if isinstance(system_dialog_detection, dict) else ""
    system_dialog_blocking = dialog_detected and dialog_owner == "system"

    eligible_surface = surface in {"webview", "hybrid"}

    evidence = [
        f"surface:{surface}",
        f"mode:{'dry_run' if mode != 'live' else 'live'}",
        "opt_in:present" if explicit_opt_in else "opt_in:missing",
        "diag:candidate" if diagnostics_candidate else "diag:not_candidate",
        "guardrails:allowed" if guardrails_allowed else f"guardrails:{guardrails_decision or 'unknown'}",
        "ctx:webview_present" if webview_context_available else "ctx:webview_missing",
        "ctx:webview_multiple" if multi_webview else "ctx:webview_single_or_none",
        f"hint:{hint_type}",
    ]
    if system_dialog_blocking:
        evidence.append("dialog:system_blocking")

    result = {
        "decision": "blocked",
        "reason": "opt_in_missing",
        "eligible_surface": eligible_surface,
        "opt_in_present": bool(explicit_opt_in),
        "diagnostics_candidate": diagnostics_candidate,
        "guardrails_allowed": guardrails_allowed,
        "webview_context_available": webview_context_available,
        "multi_webview": multi_webview,
        "system_dialog_blocking": system_dialog_blocking,
        "instruction_hint_type": hint_type,
        "switch_attempted": False,
        "evidence": sorted(set(evidence)),
        "warnings": [],
        "safe_metadata_only": True,
    }

    if not any(isinstance(x, dict) for x in (context_inventory, framework_detection, webview_switch_diagnostics, webview_switch_guardrails, system_dialog_detection)):
        result["decision"] = "unknown"
        result["reason"] = "insufficient_metadata"
        return result

    if not explicit_opt_in:
        return result

    if not eligible_surface:
        result["reason"] = "surface_not_eligible"
        return result

    if system_dialog_blocking:
        result["reason"] = "system_dialog_blocking"
        return result

    if not diagnostics_candidate:
        result["reason"] = "diagnostics_not_candidate"
        return result

    if not guardrails_allowed:
        result["decision"] = "deferred" if guardrails_decision in {"deferred", "unknown"} else "blocked"
        result["reason"] = "guardrails_not_allowed"
        return result

    if not webview_context_available:
        result["reason"] = "webview_context_missing"
        return result

    if multi_webview:
        result["decision"] = "deferred"
        result["reason"] = "multiple_webviews_no_selection_policy"
        result["warnings"] = ["selection_policy_missing"]
        return result

    if hint_type in {"weak", "unknown"}:
        result["decision"] = "deferred"
        result["reason"] = "instruction_hint_weak"
        return result

    if hint_type == "native_like":
        result["reason"] = "instruction_native_like"
        return result

    result["decision"] = "allowed"
    result["reason"] = "eligibility_criteria_satisfied"
    return result
