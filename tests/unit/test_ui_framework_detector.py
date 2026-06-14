"""Unit tests for the UI framework detector + resolver gating (M4).

Browser/device-free: signature-based detection across Compose / Flutter / RN /
SwiftUI / native hierarchies, and the conservative, additive resolver tweak
(clickable generic View nodes scored as real controls for Compose/RN).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from bubblegum.core.grounding.resolvers.appium_hierarchy import (
    AppiumHierarchyResolver,
    _role_match_for_action,
)
from bubblegum.core.mobile.ui_framework_detector import detect_ui_framework
from bubblegum.core.schemas import StepIntent


# ---------------------------------------------------------------------------
# detect_ui_framework
# ---------------------------------------------------------------------------


def test_detect_jetpack_compose():
    xml = '<hierarchy><androidx.compose.ui.platform.AndroidComposeView clickable="true" content-desc="Login"/></hierarchy>'
    out = detect_ui_framework(platform="Android", hierarchy_xml=xml)
    assert out["framework"] == "jetpack_compose"
    assert out["confidence"] == 0.9
    assert "compose_generic_view_nodes" in out["limits"]


def test_detect_flutter_reports_limits():
    xml = '<hierarchy><io.flutter.embedding.android.FlutterView/></hierarchy>'
    out = detect_ui_framework(platform="Android", hierarchy_xml=xml)
    assert out["framework"] == "flutter"
    assert "flutter_semantics_required" in out["limits"]
    assert "flutter_resolution_limited_without_accessibility" in out["warnings"]


def test_detect_react_native_android():
    xml = '<hierarchy><com.facebook.react.ReactRootView><com.facebook.react.views.view.ReactViewGroup/></com.facebook.react.ReactRootView></hierarchy>'
    out = detect_ui_framework(platform="Android", hierarchy_xml=xml)
    assert out["framework"] == "react_native"


def test_detect_react_native_ios():
    xml = '<AppiumAUT><XCUIElementTypeOther name="RCTView"/></AppiumAUT>'
    out = detect_ui_framework(platform="iOS", hierarchy_xml=xml)
    assert out["framework"] == "react_native"


def test_detect_swiftui():
    xml = '<AppiumAUT><XCUIElementTypeOther name="_UIHostingView"/></AppiumAUT>'
    out = detect_ui_framework(platform="iOS", hierarchy_xml=xml)
    assert out["framework"] == "swiftui"
    assert "swiftui_type_info_limited" in out["limits"]


def test_detect_native_android_and_ios_fallback():
    a = detect_ui_framework(platform="Android", hierarchy_xml="<hierarchy><android.widget.Button/></hierarchy>")
    assert a["framework"] == "native_android"
    i = detect_ui_framework(platform="iOS", hierarchy_xml="<AppiumAUT><XCUIElementTypeButton/></AppiumAUT>")
    assert i["framework"] == "native_ios"
    assert "ios_native_toolkit_ambiguous" in i["warnings"]


def test_detect_unknown_without_signals():
    out = detect_ui_framework(platform=None, hierarchy_xml=None)
    assert out["framework"] == "unknown"
    assert "no_hierarchy_signals" in out["warnings"]


def test_compose_not_misdetected_on_ios():
    # androidx.compose can't apply to iOS; an iOS tree falls back to native_ios.
    out = detect_ui_framework(platform="iOS", hierarchy_xml="<AppiumAUT><XCUIElementTypeStaticText/></AppiumAUT>")
    assert out["framework"] == "native_ios"


# ---------------------------------------------------------------------------
# _role_match_for_action gating
# ---------------------------------------------------------------------------


def test_role_match_native_unchanged():
    # No ui_framework → generic View stays down-ranked (back-compat).
    assert _role_match_for_action("android.view.View", "tap") == 0.4
    assert _role_match_for_action("android.widget.Button", "tap") == 1.0


def test_role_match_boosts_clickable_generic_view_for_compose_and_rn():
    for fw in ("jetpack_compose", "react_native"):
        assert _role_match_for_action("android.view.View", "tap", ui_framework=fw, clickable=True) == 0.9
        # Non-clickable generic node is NOT boosted.
        assert _role_match_for_action("android.view.View", "tap", ui_framework=fw, clickable=False) == 0.4


def test_role_match_no_boost_for_flutter_or_native():
    assert _role_match_for_action("android.view.View", "tap", ui_framework="flutter", clickable=True) == 0.4
    assert _role_match_for_action("android.view.View", "tap", ui_framework="native_android", clickable=True) == 0.4


# ---------------------------------------------------------------------------
# Resolver end-to-end with framework gating
# ---------------------------------------------------------------------------


_COMPOSE_HIERARCHY = (
    '<hierarchy>'
    '<android.view.View class="android.view.View" content-desc="Login" clickable="true" bounds="[0,0][100,50]"/>'
    '</hierarchy>'
)


def _intent(instruction, app_state):
    return StepIntent(
        instruction=instruction,
        channel="mobile",
        platform="android",
        action_type="tap",
        target_phrase=instruction.split(" ", 1)[-1],
        context={"hierarchy_xml": _COMPOSE_HIERARCHY, "app_state": app_state},
    )


def test_resolver_boosts_compose_clickable_view_role():
    resolver = AppiumHierarchyResolver()
    app_state = {"ui_framework": {"framework": "jetpack_compose", "confidence": 0.9, "limits": ["compose_generic_view_nodes"]}}
    targets = resolver.resolve(_intent("Tap Login", app_state))
    assert targets, "expected the content-desc match"
    role = targets[0].metadata["signals"]["role_match"]
    assert role == 0.9  # boosted from the native 0.4
    # Framework info is stamped onto the candidate for explain/reports.
    assert targets[0].metadata["ui_framework"]["framework"] == "jetpack_compose"


def test_resolver_native_generic_view_not_boosted():
    resolver = AppiumHierarchyResolver()
    app_state = {"ui_framework": {"framework": "native_android", "confidence": 0.6, "limits": []}}
    targets = resolver.resolve(_intent("Tap Login", app_state))
    assert targets
    assert targets[0].metadata["signals"]["role_match"] == 0.4
