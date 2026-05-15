from __future__ import annotations


def _surface_type(framework_detection: dict | None) -> str:
    if not isinstance(framework_detection, dict):
        return "unknown"
    value = str(framework_detection.get("surface_type") or "").strip().lower()
    allowed = {"android_native", "ios_native", "webview", "hybrid", "system_dialog", "unknown"}
    return value if value in allowed else "unknown"


def _safe_action(action_type: str | None) -> str | None:
    value = str(action_type or "").strip().lower()
    if value in {"tap", "click", "type", "scroll", "swipe"}:
        return value
    return None


def _safe_target_hint(target_hint: str | None) -> str | None:
    value = str(target_hint or "").strip().lower()
    if not value:
        return None
    web_tokens = ("web", "browser", "url", "link", "html", "dom")
    native_tokens = ("native", "dialog", "permission", "system", "alert")
    if any(tok in value for tok in web_tokens):
        return "web_hint"
    if any(tok in value for tok in native_tokens):
        return "native_hint"
    return None


def build_webview_switch_diagnostics(
    *,
    context_inventory: dict | None = None,
    framework_detection: dict | None = None,
    action_type: str | None = None,
    target_hint: str | None = None,
) -> dict:
    inv = context_inventory if isinstance(context_inventory, dict) else {}
    surface = _surface_type(framework_detection)

    has_webview = bool(inv.get("has_webview_context"))
    has_native = bool(inv.get("has_native_context"))
    current = str(inv.get("current_context_type") or "").strip().lower()

    evidence: list[str] = [f"surface:{surface}"]
    if has_webview:
        evidence.append("ctx:webview_present")
    if has_native:
        evidence.append("ctx:native_present")
    if current in {"native", "webview", "webview/chromium"}:
        evidence.append("current:webview" if current.startswith("webview") else "current:native")

    safe_action = _safe_action(action_type)
    if safe_action:
        evidence.append(f"action:{safe_action}")
    safe_target = _safe_target_hint(target_hint)
    if safe_target:
        evidence.append(f"target:{safe_target}")

    status = "unknown"
    recommended_context = "unknown"
    reason = "unknown_surface"
    switch_required_future = False

    if surface in {"android_native", "ios_native"}:
        status = "native_only"
        recommended_context = "native"
        reason = "native_surface"
    elif surface == "webview":
        status = "webview_candidate"
        recommended_context = "webview"
        reason = "webview_surface"
        switch_required_future = True
    elif surface == "hybrid":
        status = "hybrid_candidate"
        reason = "hybrid_surface"
        if safe_target == "native_hint":
            recommended_context = "native"
        else:
            recommended_context = "webview" if has_webview else "native"
        switch_required_future = bool(has_webview)
        if not has_webview:
            reason = "no_webview_context"
    elif surface == "system_dialog":
        status = "not_applicable"
        recommended_context = "native"
        reason = "system_dialog_surface"

    return {
        "status": status,
        "recommended_context": recommended_context,
        "switch_required_future": switch_required_future,
        "switch_attempted": False,
        "reason": reason,
        "evidence": sorted(set(evidence)),
        "warnings": [],
        "safe_metadata_only": True,
    }
