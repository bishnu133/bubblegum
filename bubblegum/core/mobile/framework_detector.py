from __future__ import annotations

from typing import Any


def _norm_platform(platform: str | None, capabilities: dict[str, Any] | None) -> str:
    value = (platform or "").strip().lower()
    if not value and capabilities:
        value = str(capabilities.get("platformName") or capabilities.get("platform") or "").strip().lower()
    if value in {"android"}:
        return "android"
    if value in {"ios", "iphone", "ipad"}:
        return "ios"
    return "unknown"


def _framework_from_caps(caps: dict[str, Any] | None, platform: str, has_webview: bool, has_native: bool) -> str:
    caps = caps or {}
    automation = str(caps.get("automationName") or "").strip().lower()
    if has_webview and has_native:
        return "mixed"
    if has_webview:
        return "chromedriver_webview"
    if "uiautomator" in automation or platform == "android":
        return "uiautomator2"
    if "xcui" in automation or platform == "ios":
        return "xcuitest"
    return "unknown"


def _xml_tokens(hierarchy_xml: str | None) -> set[str]:
    xml = (hierarchy_xml or "").lower()
    tokens: set[str] = set()
    if not xml:
        return tokens

    if "android.widget." in xml or "resource-id=" in xml or "content-desc=" in xml or "bounds=" in xml:
        tokens.add("xml:android_widget")
    if "xcuielementtype" in xml or "label=" in xml or "name=" in xml or "value=" in xml:
        tokens.add("xml:ios_xcui")
    if "webview" in xml or "chromium" in xml:
        tokens.add("xml:webview_hint")

    dialog_markers = ("allow", "deny", "while using", "don't allow", "dont allow", "ok", "cancel")
    if any(marker in xml for marker in dialog_markers):
        tokens.add("xml:permission_tokens")
    if "com.android.permissioncontroller" in xml or "com.google.android.permissioncontroller" in xml:
        tokens.add("xml:system_pkg_hint")
    return tokens


def detect_mobile_surface(*, platform: str | None = None, capabilities: dict | None = None, app_state: dict | None = None, hierarchy_xml: str | None = None) -> dict[str, Any]:
    caps: dict[str, Any] = capabilities or {}
    state: dict[str, Any] = app_state or {}
    inv = state.get("context_inventory") if isinstance(state.get("context_inventory"), dict) else {}

    detected_platform = _norm_platform(platform, caps)
    evidence: list[str] = []
    warnings: list[str] = []

    if detected_platform != "unknown":
        evidence.append(f"platform:{detected_platform}")

    inferred_mode = str(inv.get("inferred_context_mode") or "").strip().lower()
    if inferred_mode in {"native_only", "webview_only", "hybrid"}:
        evidence.append(f"ctx:{inferred_mode}")

    current_context_type = str(inv.get("current_context_type") or "").strip().lower()
    if current_context_type in {"native", "webview", "webview/chromium", "other", "unknown"}:
        evidence.append(f"ctx_current:{current_context_type}")

    xml_tokens = _xml_tokens(hierarchy_xml)
    evidence.extend(sorted(xml_tokens))

    has_native = bool(inv.get("has_native_context")) or inferred_mode in {"native_only", "hybrid"} or current_context_type == "native"
    has_webview = bool(inv.get("has_webview_context")) or inferred_mode in {"webview_only", "hybrid"} or current_context_type.startswith("webview")

    android_score = 0
    ios_score = 0
    webview_score = 0
    hybrid_score = 0
    system_score = 0

    if detected_platform == "android":
        android_score += 2
    if detected_platform == "ios":
        ios_score += 2

    if inferred_mode == "native_only":
        android_score += 1 if detected_platform == "android" else 0
        ios_score += 1 if detected_platform == "ios" else 0
    if inferred_mode == "webview_only":
        webview_score += 3
    if inferred_mode == "hybrid":
        hybrid_score += 4

    if has_native and has_webview:
        hybrid_score += 3
    if current_context_type in {"webview", "webview/chromium"}:
        webview_score += 2

    if "xml:android_widget" in xml_tokens:
        android_score += 2
    if "xml:ios_xcui" in xml_tokens:
        ios_score += 2

    if "xml:android_widget" in xml_tokens and "xml:ios_xcui" in xml_tokens:
        warnings.append("conflicting_surface_signals")
    if "xml:webview_hint" in xml_tokens:
        webview_score += 1
    if "xml:permission_tokens" in xml_tokens:
        system_score += 2
    if "xml:system_pkg_hint" in xml_tokens:
        system_score += 2

    scores = {
        "android_native": android_score,
        "ios_native": ios_score,
        "webview": webview_score,
        "hybrid": hybrid_score,
        "system_dialog": system_score,
    }

    best_type = "unknown"
    best_score = 0
    if any(scores.values()):
        best_type, best_score = max(scores.items(), key=lambda item: item[1])
        sorted_scores = sorted(scores.values(), reverse=True)
        if len(sorted_scores) >= 2 and sorted_scores[0] == sorted_scores[1] and sorted_scores[0] > 0:
            best_type = "unknown"
            warnings.append("conflicting_surface_signals")

    if "conflicting_surface_signals" in warnings and android_score > 0 and ios_score > 0:
        best_type = "unknown"

    if best_score == 0:
        warnings.append("sparse_surface_signals")

    confidence = round(min(1.0, best_score / 6.0), 2) if best_type != "unknown" else 0.0
    framework = _framework_from_caps(caps, detected_platform, has_webview, has_native)

    return {
        "surface_type": best_type,
        "platform": detected_platform,
        "framework": framework,
        "confidence": confidence,
        "evidence": sorted(set(evidence)),
        "warnings": sorted(set(warnings)),
        "safe_metadata_only": True,
    }
