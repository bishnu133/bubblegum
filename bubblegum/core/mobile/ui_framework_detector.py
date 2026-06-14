"""
bubblegum/core/mobile/ui_framework_detector.py
==============================================
Detect the app's UI toolkit (M4): Jetpack Compose / Flutter / React Native /
SwiftUI vs. classic native.

This complements ``framework_detector.detect_mobile_surface`` (which classifies
the *Appium automation surface* — native/webview/hybrid and the driver). Here we
classify the *UI framework* the app is built with, because Compose, Flutter and
RN expose their element trees very differently from classic native views, and
the hierarchy resolver can tune its matching once it knows which one it is.

Detection is heuristic and signature-based — class/package tokens in the
hierarchy XML plus a platform fallback. No Flutter driver / accessibility
toggling is attempted; Flutter's limits are reported honestly in ``limits`` /
``warnings`` rather than solved here.
"""

from __future__ import annotations

from typing import Any

# Frameworks this detector can report.
JETPACK_COMPOSE = "jetpack_compose"
FLUTTER = "flutter"
REACT_NATIVE = "react_native"
SWIFTUI = "swiftui"
NATIVE_ANDROID = "native_android"
NATIVE_IOS = "native_ios"
UNKNOWN = "unknown"

# Strong class/package signatures (substring match on lowercased hierarchy XML).
_COMPOSE_TOKENS = ("androidx.compose",)  # AndroidComposeView / ComposeView
_FLUTTER_TOKENS = ("io.flutter", "flutterview")
_RN_ANDROID_TOKENS = ("com.facebook.react", "reactrootview", "reactviewgroup")
_RN_IOS_TOKENS = ("rctview", "rctrootview", "rctscrollview", "rctsafeareaview")
_SWIFTUI_TOKENS = ("swiftui", "uihostingview", "hostingcontroller", "_ttgc7swiftui")


def _norm_platform(platform: str | None, capabilities: dict[str, Any] | None) -> str:
    value = (platform or "").strip().lower()
    if not value and capabilities:
        value = str(capabilities.get("platformName") or capabilities.get("platform") or "").strip().lower()
    if value == "android":
        return "android"
    if value in {"ios", "iphone", "ipad"}:
        return "ios"
    return "unknown"


def _found(xml: str, tokens: tuple[str, ...]) -> list[str]:
    return [t for t in tokens if t in xml]


def detect_ui_framework(
    *,
    platform: str | None = None,
    capabilities: dict | None = None,
    hierarchy_xml: str | None = None,
) -> dict[str, Any]:
    """Classify the app's UI framework from hierarchy signatures + platform.

    Returns a safe-metadata dict:
        framework   one of the constants above
        confidence  0.0–1.0 (strong class signature ≈ 0.9, platform fallback 0.6)
        evidence    matched signal tokens
        warnings    e.g. resolution caveats
        limits      framework limitations callers/readers should know
    """
    detected_platform = _norm_platform(platform, capabilities)
    xml = (hierarchy_xml or "").lower()
    evidence: list[str] = []
    warnings: list[str] = []
    limits: list[str] = []

    framework = UNKNOWN
    confidence = 0.0

    # Cross-platform toolkits first (most specific), then platform-native.
    flutter_hits = _found(xml, _FLUTTER_TOKENS)
    rn_hits = _found(xml, _RN_ANDROID_TOKENS) + (_found(xml, _RN_IOS_TOKENS) if detected_platform == "ios" else [])
    compose_hits = _found(xml, _COMPOSE_TOKENS) if detected_platform != "ios" else []
    swiftui_hits = _found(xml, _SWIFTUI_TOKENS) if detected_platform == "ios" else []

    if flutter_hits:
        framework, confidence = FLUTTER, 0.9
        evidence += [f"class:{t}" for t in flutter_hits]
        limits.append("flutter_semantics_required")
        warnings.append("flutter_resolution_limited_without_accessibility")
    elif rn_hits:
        framework, confidence = REACT_NATIVE, 0.9
        evidence += [f"class:{t}" for t in rn_hits]
        limits.append("react_native_generic_view_nodes")
    elif compose_hits:
        framework, confidence = JETPACK_COMPOSE, 0.9
        evidence += [f"class:{t}" for t in compose_hits]
        limits.append("compose_generic_view_nodes")
    elif swiftui_hits:
        framework, confidence = SWIFTUI, 0.8
        evidence += [f"class:{t}" for t in swiftui_hits]
        limits.append("swiftui_type_info_limited")
    elif detected_platform == "android":
        framework, confidence = NATIVE_ANDROID, 0.6 if xml else 0.4
        evidence.append("platform:android")
    elif detected_platform == "ios":
        framework, confidence = NATIVE_IOS, 0.6 if xml else 0.4
        evidence.append("platform:ios")
        # Without a strong SwiftUI signature, UIKit and SwiftUI look alike to
        # XCUITest — say so rather than guessing.
        warnings.append("ios_native_toolkit_ambiguous")

    if not xml:
        warnings.append("no_hierarchy_signals")

    return {
        "framework": framework,
        "confidence": round(confidence, 2),
        "platform": detected_platform,
        "evidence": sorted(set(evidence)),
        "warnings": sorted(set(warnings)),
        "limits": sorted(set(limits)),
        "safe_metadata_only": True,
    }
