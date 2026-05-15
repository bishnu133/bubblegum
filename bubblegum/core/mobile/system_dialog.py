from __future__ import annotations

from typing import Any


_PERMISSION_TOKENS = (
    ("while using", "token:while_using"),
    ("only this time", "token:only_this_time"),
    ("don't allow", "token:dont_allow"),
    ("dont allow", "token:dont_allow"),
    ("allow", "token:allow"),
    ("deny", "token:deny"),
)

_CONFIRM_CANCEL_TOKENS = (
    ("ok", "token:ok"),
    ("cancel", "token:cancel"),
    ("confirm", "token:confirm"),
    ("dismiss", "token:dismiss"),
)


def _norm_platform(platform: str | None, capabilities: dict[str, Any] | None) -> str:
    value = (platform or "").strip().lower()
    if not value and capabilities:
        value = str(capabilities.get("platformName") or capabilities.get("platform") or "").strip().lower()
    if value == "android":
        return "android"
    if value in {"ios", "iphone", "ipad"}:
        return "ios"
    return "unknown"


def _collect_tokens(xml: str | None) -> set[str]:
    text = (xml or "").lower()
    tokens: set[str] = set()

    for needle, token in _PERMISSION_TOKENS:
        if needle in text:
            tokens.add(token)

    for needle, token in _CONFIRM_CANCEL_TOKENS:
        if needle in text:
            tokens.add(token)

    if "xcuielementtypealert" in text or " alert" in text or "alert" in text:
        tokens.add("hint:alert")
    if "com.android.permissioncontroller" in text or "com.google.android.permissioncontroller" in text:
        tokens.add("hint:android_system_ui")
    if "android.widget" in text:
        tokens.add("hint:android_widget")
    if "xcuielementtype" in text:
        tokens.add("hint:ios_xcui")
    return tokens


def detect_system_dialog(
    *,
    platform: str | None = None,
    capabilities: dict | None = None,
    app_state: dict | None = None,
    hierarchy_xml: str | None = None,
) -> dict:
    caps = capabilities or {}
    state = app_state or {}
    framework = state.get("framework_detection") if isinstance(state.get("framework_detection"), dict) else {}

    detected_platform = _norm_platform(platform, caps)
    evidence: set[str] = set()
    warnings: list[str] = []
    tokens = _collect_tokens(hierarchy_xml)

    if detected_platform != "unknown":
        evidence.add(f"platform:{detected_platform}")

    if str(framework.get("surface_type") or "").strip().lower() == "system_dialog":
        evidence.add("surface:system_dialog")

    evidence.update(tokens)

    permission_hits = {t for t in tokens if t.startswith("token:") and t in {"token:allow", "token:deny", "token:while_using", "token:only_this_time", "token:dont_allow"}}
    confirm_hits = {t for t in tokens if t in {"token:ok", "token:cancel", "token:confirm", "token:dismiss"}}

    dialog_type = "unknown"
    if permission_hits:
        dialog_type = "permission"
    elif len(confirm_hits) >= 2 and ("token:ok" in confirm_hits or "token:confirm" in confirm_hits) and ("token:cancel" in confirm_hits or "token:dismiss" in confirm_hits):
        dialog_type = "confirm_cancel"
    elif "hint:alert" in tokens or "surface:system_dialog" in evidence:
        dialog_type = "alert"

    owner = "unknown"
    if any(t in tokens for t in {"hint:android_system_ui", "hint:ios_xcui"}) or "surface:system_dialog" in evidence:
        owner = "system"
    elif "dialog" in (hierarchy_xml or "").lower() or confirm_hits:
        owner = "app"

    dialog_detected = dialog_type != "unknown" or "surface:system_dialog" in evidence

    recommended_action = "manual_review"
    if not dialog_detected:
        recommended_action = "defer"
    elif dialog_type == "permission":
        if any(t in permission_hits for t in {"token:deny", "token:dont_allow"}):
            recommended_action = "deny"
        elif any(t in permission_hits for t in {"token:while_using", "token:only_this_time", "token:allow"}):
            recommended_action = "allow"
    elif dialog_type == "unknown":
        recommended_action = "unknown"

    if not evidence:
        warnings.append("sparse_signals")

    confidence = 0.0
    if dialog_detected:
        confidence = 0.55
        if dialog_type == "permission" and len(permission_hits) >= 2:
            confidence = 0.9
        elif dialog_type == "confirm_cancel":
            confidence = 0.75
        elif dialog_type == "alert":
            confidence = 0.65

    return {
        "dialog_detected": bool(dialog_detected),
        "dialog_type": dialog_type,
        "platform": detected_platform,
        "owner": owner,
        "recommended_action": recommended_action,
        "confidence": confidence,
        "evidence": sorted(evidence),
        "warnings": sorted(set(warnings)),
        "safe_metadata_only": True,
    }
