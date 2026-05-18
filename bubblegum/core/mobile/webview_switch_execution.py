from __future__ import annotations

from collections.abc import Callable


def _safe_decision(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    allowed = {"allowed", "blocked", "deferred", "unknown"}
    return normalized if normalized in allowed else "unknown"


def _safe_selection_decision(webview_context_selection: dict | None) -> str:
    if not isinstance(webview_context_selection, dict):
        return "unknown"
    normalized = str(webview_context_selection.get("decision") or "").strip().lower()
    allowed = {"selected", "blocked", "deferred", "unknown"}
    return normalized if normalized in allowed else "unknown"


def _safe_context_type(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"native", "nativ", "native_app"}:
        return "native"
    if normalized.startswith("webview"):
        return "webview"
    return "unknown"


def _safe_reason(payload: dict | None) -> str:
    if not isinstance(payload, dict):
        return "unknown"
    reason = str(payload.get("reason") or "").strip().lower()
    return reason or "unknown"


def _sanitize_exception(exc: Exception) -> str:
    message = str(exc).strip().lower()
    if not message:
        return "execution_error"
    return "execution_error"


def build_webview_switch_execution_plan(
    *,
    webview_switch_eligibility: dict | None = None,
    webview_context_selection: dict | None = None,
    explicit_opt_in: bool = False,
) -> dict:
    eligibility_decision = _safe_decision((webview_switch_eligibility or {}).get("decision") if isinstance(webview_switch_eligibility, dict) else None)
    selection_decision = _safe_selection_decision(webview_context_selection)
    selected_context_type = _safe_context_type((webview_context_selection or {}).get("selected_context_type") if isinstance(webview_context_selection, dict) else None)

    out = {
        "switch_enabled": bool(explicit_opt_in),
        "switch_attempted": False,
        "switch_status": "not_attempted",
        "restore_attempted": False,
        "restore_status": "not_needed",
        "original_context_type": "unknown",
        "selected_context_type": selected_context_type if selected_context_type == "webview" else "unknown",
        "context_selection_reason": _safe_reason(webview_context_selection),
        "reason": "not_attempted",
        "evidence": [],
        "warnings": [],
        "safe_metadata_only": True,
    }

    if not explicit_opt_in:
        out["switch_status"] = "blocked"
        out["reason"] = "opt_in_required"
        out["warnings"] = ["opt_in_required"]
        return out

    if eligibility_decision != "allowed":
        out["switch_status"] = "blocked" if eligibility_decision in {"blocked", "unknown"} else "deferred"
        out["reason"] = "eligibility_not_allowed"
        out["warnings"] = ["eligibility_not_allowed"]
        return out

    if selection_decision != "selected":
        out["switch_status"] = "blocked" if selection_decision in {"blocked", "unknown"} else "deferred"
        out["reason"] = "context_not_selected"
        out["warnings"] = ["context_not_selected"]
        return out

    if selected_context_type != "webview":
        out["switch_status"] = "blocked"
        out["reason"] = "selected_context_metadata_insufficient"
        out["warnings"] = ["selected_context_metadata_insufficient"]
        return out

    out["reason"] = "switch_ready"
    return out


def execute_webview_switch_guarded(
    *,
    webview_switch_eligibility: dict | None = None,
    webview_context_selection: dict | None = None,
    explicit_opt_in: bool = False,
    get_current_context: Callable[[], str | None] | None = None,
    switch_context: Callable[[dict], None] | None = None,
    restore_context: Callable[[str | None], None] | None = None,
    operation_callable: Callable[[], object] | None = None,
) -> dict:
    plan = build_webview_switch_execution_plan(
        webview_switch_eligibility=webview_switch_eligibility,
        webview_context_selection=webview_context_selection,
        explicit_opt_in=explicit_opt_in,
    )

    if plan["reason"] != "switch_ready":
        return plan

    original_context_value = None
    switched = False

    try:
        if callable(get_current_context):
            original_context_value = get_current_context()
            plan["original_context_type"] = _safe_context_type(original_context_value)

        if not callable(switch_context):
            plan["switch_status"] = "blocked"
            plan["reason"] = "switch_callable_missing"
            plan["warnings"] = ["switch_callable_missing"]
            return plan

        plan["switch_attempted"] = True
        switch_context(webview_context_selection or {})
        switched = True
        plan["switch_status"] = "switched"
        plan["reason"] = "switch_succeeded"
        if callable(operation_callable):
            operation_callable()
    except Exception as exc:
        plan["switch_status"] = "failed"
        plan["reason"] = _sanitize_exception(exc)
        plan["warnings"] = ["switch_failed"]
    finally:
        if switched:
            if callable(restore_context):
                plan["restore_attempted"] = True
                try:
                    restore_context(original_context_value)
                    plan["restore_status"] = "restored"
                except Exception:
                    plan["restore_status"] = "failed"
                    plan["warnings"] = [*plan.get("warnings", []), "restore_failed"]
            else:
                plan["restore_status"] = "unknown"

    return plan
