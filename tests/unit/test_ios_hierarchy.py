"""
tests/unit/test_ios_hierarchy.py
================================
a56 — iOS (XCUITest) grounding in AppiumHierarchyResolver.

The resolver historically read only Android UiAutomator2 attributes
(``text``/``content-desc``/``resource-id``/``bounds``/``visible-to-user``). iOS
hierarchies expose the same concepts under different names
(``label``/``name``/``value``/``type``/``visible`` and x/y/width/height), so
grounding by human text returned no candidate on iOS. These tests exercise the
cross-platform attribute mapping so a label like "View Summary" resolves on iOS
the same way it does on Android.

All app names / labels below are generic placeholders.
"""

from __future__ import annotations

import json

from bubblegum.core.grounding.resolvers.appium_hierarchy import (
    AppiumHierarchyResolver,
    _ios_bounds,
    _match_quality,
    _unified_attrs,
)
from bubblegum.core.schemas import ExecutionOptions, StepIntent


# An iOS system permission alert (springboard). Both "Allow" and "Don't Allow"
# contain the substring "allow", so a naive text match is ambiguous — the exact
# label must win.
_PERMISSION_ALERT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<AppiumAUT>
  <XCUIElementTypeApplication type="XCUIElementTypeApplication" name="SpringBoard">
    <XCUIElementTypeAlert type="XCUIElementTypeAlert" name="Example App" label="Example App Would Like to Send You Notifications" enabled="true" visible="true" x="40" y="300" width="270" height="180">
      <XCUIElementTypeButton type="XCUIElementTypeButton" name="Don't Allow" label="Don't Allow" enabled="true" visible="true" x="45" y="440" width="130" height="40"/>
      <XCUIElementTypeButton type="XCUIElementTypeButton" name="Allow" label="Allow" enabled="true" visible="true" x="180" y="440" width="130" height="40"/>
    </XCUIElementTypeAlert>
  </XCUIElementTypeApplication>
</AppiumAUT>"""


# A representative React-Native-on-iOS XCUITest hierarchy. The button carries a
# testID ("view-summary-button") but, because it also has a visible label,
# XCUITest surfaces the human label as `name` — exactly the case that breaks a
# testID/predicate-string locator while a text match still works.
_IOS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<AppiumAUT>
  <XCUIElementTypeApplication type="XCUIElementTypeApplication" name="DemoApp">
    <XCUIElementTypeWindow type="XCUIElementTypeWindow" enabled="true" visible="true" x="0" y="0" width="390" height="844">
      <XCUIElementTypeButton type="XCUIElementTypeButton" name="View Summary" label="View Summary" value="" enabled="true" visible="true" x="20" y="600" width="350" height="44"/>
      <XCUIElementTypeStaticText type="XCUIElementTypeStaticText" name="Total Items" label="Total Items" value="42" enabled="true" visible="true" x="20" y="100" width="220" height="20"/>
      <XCUIElementTypeTextField type="XCUIElementTypeTextField" name="search-field" label="" value="Search items" enabled="true" visible="true" x="20" y="50" width="350" height="40"/>
      <XCUIElementTypeButton type="XCUIElementTypeButton" name="hidden-btn" label="Hidden action" value="" enabled="false" visible="false" x="0" y="0" width="0" height="0"/>
    </XCUIElementTypeWindow>
  </XCUIElementTypeApplication>
</AppiumAUT>"""


def _resolve(instruction, *, xml=_IOS_XML, action_type="tap", platform="ios"):
    r = AppiumHierarchyResolver()
    intent = StepIntent(
        instruction=instruction,
        channel="mobile",
        platform=platform,
        action_type=action_type,
        context={"hierarchy_xml": xml},
        options=ExecutionOptions(),
    )
    return r.resolve(intent)


# ---------------------------------------------------------------------------
# label (visible text) matching — the iOS click that a testID locator misses
# ---------------------------------------------------------------------------

def test_label_match_resolves_button():
    candidates = _resolve("View Summary")
    labels = [c for c in candidates if c.metadata.get("matched_attr") == "label"]
    assert labels, "expected a label match for the iOS button"
    assert labels[0].confidence == 0.92


def test_label_match_builds_ios_xpath():
    candidates = _resolve("View Summary")
    labels = [c for c in candidates if c.metadata.get("matched_attr") == "label"]
    ref = json.loads(labels[0].ref)
    assert ref["by"] == "xpath"
    # iOS xpath uses the element type and the @label attribute.
    assert ref["value"] == "//XCUIElementTypeButton[@label='View Summary']"


def test_label_match_case_insensitive():
    assert _resolve("view summary"), "case-insensitive label match expected"


def test_tap_button_role_scores_full():
    candidates = _resolve("View Summary")
    labels = [c for c in candidates if c.metadata.get("matched_attr") == "label"]
    role = labels[0].metadata["signals"]["role_match"]
    assert role == 1.0  # XCUIElementTypeButton -> "button" keyword


# ---------------------------------------------------------------------------
# value matching (text fields) and verify on static text
# ---------------------------------------------------------------------------

def test_value_match_on_textfield():
    candidates = _resolve("Search items", action_type="type")
    values = [c for c in candidates if c.metadata.get("matched_attr") == "value"]
    assert values, "expected a value match on the iOS text field"
    ref = json.loads(values[0].ref)
    assert ref["value"] == "//XCUIElementTypeTextField[@value='Search items']"


def test_verify_static_text_by_label():
    candidates = _resolve("Total Items", action_type="verify")
    labels = [c for c in candidates if c.metadata.get("matched_attr") == "label"]
    assert labels, "expected the static text to match by label"


# ---------------------------------------------------------------------------
# geometry / visibility
# ---------------------------------------------------------------------------

def test_ios_bounds_synthesised_from_xywh():
    candidates = _resolve("View Summary")
    labels = [c for c in candidates if c.metadata.get("matched_attr") == "label"]
    # x=20 y=600 w=350 h=44 -> [20,600][370,644]
    assert labels[0].metadata["bounds"] == "[20,600][370,644]"


def test_ios_bounds_helper_zero_size_is_empty():
    import xml.etree.ElementTree as ET

    el = ET.fromstring('<XCUIElementTypeButton x="0" y="0" width="0" height="0"/>')
    assert _ios_bounds(el) == ""


def test_hidden_element_downranked_visibility():
    candidates = _resolve("Hidden action")
    hidden = [c for c in candidates if c.metadata.get("matched_value") == "Hidden action"]
    assert hidden, "hidden element should still be a candidate"
    assert hidden[0].metadata["signals"]["visibility"] == 0.2


# ---------------------------------------------------------------------------
# platform auto-detection (no explicit intent.platform)
# ---------------------------------------------------------------------------

def test_ios_detected_from_xcui_tag_without_platform():
    # platform defaults to "web"; the XCUIElementType tag alone must route iOS.
    candidates = _resolve("View Summary", platform="web")
    labels = [c for c in candidates if c.metadata.get("matched_attr") == "label"]
    assert labels, "iOS attributes must be read even when platform is unset"


def test_unified_attrs_maps_ios_fields():
    import xml.etree.ElementTree as ET

    el = ET.fromstring(
        '<XCUIElementTypeButton type="XCUIElementTypeButton" name="acc-id" '
        'label="Save" value="v" enabled="true" visible="true" '
        'x="1" y="2" width="3" height="4"/>'
    )
    attrs = _unified_attrs(el, "ios")
    assert attrs["ios"] is True
    assert attrs["widget_type"] == "XCUIElementTypeButton"
    assert attrs["text"] == "Save"          # label -> text
    assert attrs["content_desc"] == "acc-id"  # name -> content_desc
    assert attrs["value"] == "v"
    assert attrs["bounds"] == "[1,2][4,6]"


# ---------------------------------------------------------------------------
# exact-match disambiguation — the "Allow" vs "Don't Allow" permission alert
# ---------------------------------------------------------------------------

def _top_candidate(candidates):
    return max(candidates, key=lambda c: c.confidence) if candidates else None


def test_allow_beats_dont_allow_on_permission_alert():
    candidates = _resolve("Allow", xml=_PERMISSION_ALERT_XML)
    # Both buttons match the substring, but the exact "Allow" must rank highest.
    assert len(candidates) >= 2
    top = _top_candidate(candidates)
    assert top.metadata["matched_value"] == "Allow"
    assert top.confidence == 0.92          # exact match keeps full confidence


def test_dont_allow_is_downranked_not_dropped():
    candidates = _resolve("Allow", xml=_PERMISSION_ALERT_XML)
    dont = [c for c in candidates if c.metadata["matched_value"] == "Don't Allow"]
    allow = [c for c in candidates if c.metadata["matched_value"] == "Allow"]
    assert dont and allow
    # Present as a candidate, but strictly below the exact match.
    assert dont[0].confidence < allow[0].confidence


def test_tap_dont_allow_still_selectable_exactly():
    # Asking for the deny button by its exact label must pick it, not "Allow".
    candidates = _resolve("Don't Allow", xml=_PERMISSION_ALERT_XML)
    top = _top_candidate(candidates)
    assert top.metadata["matched_value"] == "Don't Allow"
    assert top.confidence == 0.92


def test_match_quality_exact_vs_partial():
    assert _match_quality("allow", "Allow") == 1.0
    assert _match_quality("allow", "Don't Allow") < 1.0
    assert _match_quality("allow", "Allow") > _match_quality("allow", "Don't Allow")


def test_unified_attrs_android_unchanged():
    import xml.etree.ElementTree as ET

    el = ET.fromstring(
        '<android.widget.Button class="android.widget.Button" text="Login" '
        'content-desc="login" resource-id="com.x:id/login" '
        'bounds="[0,0][100,50]" clickable="true"/>'
    )
    attrs = _unified_attrs(el, "android")
    assert attrs["ios"] is False
    assert attrs["text"] == "Login"
    assert attrs["content_desc"] == "login"
    assert attrs["resource_id"] == "com.x:id/login"
    assert attrs["clickable"] is True
