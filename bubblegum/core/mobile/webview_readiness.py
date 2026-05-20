from __future__ import annotations


_ALLOWED_OPERATION_TYPES = {"validate", "extract", "execute", "unknown"}
_SAFE_STATUS = {
    "not_checked",
    "waiting_for_webview_context",
    "context_available",
    "waiting_for_target",
    "failed_closed",
}


def _safe_int(value: int | None, *, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _clamp(value: int, *, low: int, high: int) -> int:
    return max(low, min(high, value))


def _safe_operation_type(operation_type: str | None) -> str:
    value = str(operation_type or "").strip().lower()
    return value if value in _ALLOWED_OPERATION_TYPES else "unknown"


def build_webview_readiness_plan(
    *,
    enabled: bool = False,
    context_inventory: dict | None = None,
    webview_context_selection: dict | None = None,
    webview_switch_wiring_plan: dict | None = None,
    operation_type: str | None = None,
    timeout_ms: int | None = None,
    poll_interval_ms: int | None = None,
    max_context_refresh_attempts: int | None = None,
) -> dict:
    warnings: list[str] = []
    evidence: list[str] = []

    safe_timeout_ms = _safe_int(timeout_ms, default=3000)
    if safe_timeout_ms <= 0:
        safe_timeout_ms = 3000
        warnings.append("timeout_ms_invalid_defaulted")

    safe_poll_ms = _safe_int(poll_interval_ms, default=250)
    if safe_poll_ms < 100:
        safe_poll_ms = 100
        warnings.append("poll_interval_ms_clamped_min")

    safe_refresh_attempts = _clamp(_safe_int(max_context_refresh_attempts, default=1), low=0, high=3)
    if max_context_refresh_attempts is not None and safe_refresh_attempts != _safe_int(max_context_refresh_attempts, default=1):
        warnings.append("max_context_refresh_attempts_clamped")

    safe_operation = _safe_operation_type(operation_type)
    selection = webview_context_selection if isinstance(webview_context_selection, dict) else {}
    wiring = webview_switch_wiring_plan if isinstance(webview_switch_wiring_plan, dict) else {}

    if not enabled:
        return {
            "enabled": False,
            "status": "not_checked",
            "reason": "disabled",
            "operation_type": safe_operation,
            "context_refresh_attempts": 0,
            "target_wait_attempted": False,
            "timeout_ms": safe_timeout_ms,
            "poll_interval_ms": safe_poll_ms,
            "max_context_refresh_attempts": safe_refresh_attempts,
            "evidence": ["readiness:disabled"],
            "warnings": warnings,
            "safe_metadata_only": True,
        }

    if timeout_ms is not None and _safe_int(timeout_ms, default=0) <= 0:
        return {
            "enabled": True,
            "status": "failed_closed",
            "reason": "invalid_timeout",
            "operation_type": safe_operation,
            "context_refresh_attempts": 0,
            "target_wait_attempted": False,
            "timeout_ms": safe_timeout_ms,
            "poll_interval_ms": safe_poll_ms,
            "max_context_refresh_attempts": safe_refresh_attempts,
            "evidence": ["readiness:invalid_timeout"],
            "warnings": sorted(set(warnings + ["safe_failed_closed"])),
            "safe_metadata_only": True,
        }

    if not isinstance(context_inventory, dict):
        status = "waiting_for_webview_context"
        reason = "missing_context_inventory"
        evidence.append("ctx:inventory_missing")
    else:
        webview_count = _clamp(_safe_int(context_inventory.get("webview_context_count"), default=0), low=0, high=999)
        evidence.append(f"ctx:webview_count:{webview_count}")
        if webview_count <= 0:
            status = "waiting_for_webview_context"
            reason = "no_webview_context"
        else:
            selected = str(selection.get("decision") or "").strip().lower() == "selected"
            index = _safe_int(selection.get("selected_context_index"), default=-1)
            if selected and 0 <= index < webview_count:
                status = "context_available"
                reason = "selected_context_available"
                evidence.append("selection:selected")
            else:
                status = "waiting_for_webview_context"
                reason = "selection_unavailable"

    if status == "context_available" and bool(wiring.get("switch_ready")):
        status = "waiting_for_target"
        reason = "switch_ready_target_pending"
        evidence.append("wiring:switch_ready")

    if status not in _SAFE_STATUS:
        status = "failed_closed"
        reason = "status_safety_fallback"
        warnings.append("status_fallback")

    return {
        "enabled": True,
        "status": status,
        "reason": reason,
        "operation_type": safe_operation,
        "context_refresh_attempts": 0,
        "target_wait_attempted": False,
        "timeout_ms": safe_timeout_ms,
        "poll_interval_ms": safe_poll_ms,
        "max_context_refresh_attempts": safe_refresh_attempts,
        "evidence": sorted(set(evidence)),
        "warnings": sorted(set(warnings)),
        "safe_metadata_only": True,
    }
