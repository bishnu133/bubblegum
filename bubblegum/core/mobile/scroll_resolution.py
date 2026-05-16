from __future__ import annotations

from typing import Any, Callable

_SAFE_FIELDS = {
    "enabled",
    "attempted",
    "attempt_count",
    "max_scrolls",
    "found_after_scroll",
    "final_status",
    "reason",
    "evidence",
    "warnings",
    "safe_metadata_only",
}

_SAFE_CAP = 10


def _base(*, enabled: bool, attempted: bool, max_scrolls: int) -> dict[str, Any]:
    return {
        "enabled": enabled,
        "attempted": attempted,
        "attempt_count": 0,
        "max_scrolls": max_scrolls,
        "found_after_scroll": False,
        "final_status": "blocked",
        "reason": "insufficient_metadata",
        "evidence": [],
        "warnings": [],
        "safe_metadata_only": True,
    }


def _safe(result: dict[str, Any]) -> dict[str, Any]:
    return {k: result[k] for k in _SAFE_FIELDS if k in result}


def resolve_with_bounded_scroll(
    *,
    driver,
    instruction: str,
    target_hint: str | None,
    resolve_once: Callable[[], dict[str, Any]],
    collect_context: Callable[[], dict[str, Any]],
    scroll_plan: dict | None = None,
    explicit_opt_in: bool = False,
    max_scrolls: int = 3,
) -> dict[str, Any]:
    del instruction
    result = _base(enabled=bool(explicit_opt_in), attempted=False, max_scrolls=max_scrolls)

    if not explicit_opt_in:
        result["reason"] = "opt_in_missing"
        return _safe(result)

    if not isinstance(max_scrolls, int) or max_scrolls < 1 or max_scrolls > _SAFE_CAP:
        result["final_status"] = "unsupported"
        result["reason"] = "max_scrolls_reached"
        result["warnings"] = ["invalid_max_scrolls"]
        result["max_scrolls"] = min(max(max_scrolls if isinstance(max_scrolls, int) else 1, 1), _SAFE_CAP)
        return _safe(result)

    result["attempted"] = True
    result["max_scrolls"] = max_scrolls

    if not isinstance(target_hint, str) or not target_hint.strip():
        result["final_status"] = "blocked"
        result["reason"] = "insufficient_metadata"
        return _safe(result)

    plan = scroll_plan if isinstance(scroll_plan, dict) else {}
    if str(plan.get("status", "")).lower() != "candidate":
        result["final_status"] = "unsupported"
        result["reason"] = "insufficient_metadata"
        return _safe(result)
    if plan.get("scroll_needed") is not True:
        result["final_status"] = "unsupported"
        result["reason"] = "insufficient_metadata"
        return _safe(result)
    if int(plan.get("candidate_container_count", 0)) <= 0:
        result["final_status"] = "unsupported"
        result["reason"] = "no_scrollable_container"
        return _safe(result)

    app_state = collect_context() or {}
    if isinstance(app_state, dict):
        channel = str(app_state.get("channel", "mobile")).lower()
        if channel != "mobile":
            result["final_status"] = "unsupported"
            result["reason"] = "insufficient_metadata"
            return _safe(result)
        detection = app_state.get("system_dialog_detection")
        if isinstance(detection, dict) and detection.get("dialog_detected") is True:
            result["final_status"] = "blocked"
            result["reason"] = "blocked_by_system_dialog"
            return _safe(result)
        webview = app_state.get("webview_switch_guardrails")
        if isinstance(webview, dict) and webview.get("requires_switch") is True:
            result["final_status"] = "blocked"
            result["reason"] = "insufficient_metadata"
            return _safe(result)

    for idx in range(1, max_scrolls + 1):
        result["evidence"].append(f"attempt:{idx}")
        try:
            driver.swipe(500, 1500, 500, 700, 300)
            result["evidence"].append("scroll:down")
        except Exception:
            result["final_status"] = "error"
            result["reason"] = "exhausted"
            result["warnings"].append("scroll_action_failed")
            result["attempt_count"] = idx
            return _safe(result)

        app_state = collect_context() or {}
        result["evidence"].append("resolver:rerun")
        resolved = resolve_once() or {}
        result["attempt_count"] = idx
        if bool(resolved.get("found")):
            result["found_after_scroll"] = True
            result["final_status"] = "found"
            result["reason"] = "found_after_scroll"
            return _safe(result)

    result["final_status"] = "not_found"
    result["reason"] = "max_scrolls_reached"
    return _safe(result)
