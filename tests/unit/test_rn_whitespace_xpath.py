"""Bug 3/4 fix: generated xpath tolerates React-Native trailing whitespace.

RN (and other toolkits) emit text nodes like ``"Log in with OTP "`` with trailing
whitespace. An exact ``@text='Log in with OTP'`` match then finds nothing. The
resolver now emits ``normalize-space(@text)='…'`` for text-like attributes, which
matches regardless of surrounding/collapsible whitespace, on both UiAutomator2
and XCUITest. Id-like attributes keep an exact match.
"""

from __future__ import annotations

import json

from bubblegum.core.grounding.resolvers.appium_hierarchy import AppiumHierarchyResolver, _build_xpath
from bubblegum.core.schemas import ExecutionOptions, StepIntent


def test_text_attr_uses_normalize_space():
    assert _build_xpath("android.widget.TextView", "text", "Log in with OTP") == \
        "//android.widget.TextView[normalize-space(@text)='Log in with OTP']"


def test_content_desc_and_label_and_value_use_normalize_space():
    assert "normalize-space(@content-desc)" in _build_xpath("X", "content-desc", "Save")
    assert "normalize-space(@label)" in _build_xpath("X", "label", "Save")
    assert "normalize-space(@value)" in _build_xpath("X", "value", "Search items")


def test_resource_id_stays_exact():
    assert _build_xpath("android.widget.EditText", "resource-id", "nricInput") == \
        "//android.widget.EditText[@resource-id='nricInput']"


def test_internal_whitespace_is_collapsed_in_comparison():
    # A double-spaced value normalizes to single spaces on the RHS too.
    assert _build_xpath("X", "text", "Log  in") == "//X[normalize-space(@text)='Log in']"


def test_embedded_single_quote_still_quoted():
    xp = _build_xpath("X", "text", "Can't")
    assert "normalize-space(@text)" in xp and "Can't" in xp  # wrapped in double quotes


def test_resolver_emits_normalize_space_for_trailing_space_text():
    xml = '<hierarchy><android.widget.TextView text="Log in with OTP " clickable="true"/></hierarchy>'
    intent = StepIntent(
        instruction="Tap Log in with OTP",
        channel="mobile",
        platform="android",
        action_type="tap",
        target_phrase="Log in with OTP",
        context={"hierarchy_xml": xml},
        options=ExecutionOptions(),
    )
    cands = AppiumHierarchyResolver().resolve(intent)
    assert cands, "resolver should match the trailing-space text node"
    ref = json.loads(max(cands, key=lambda c: c.confidence).ref)["value"]
    assert ref == "//android.widget.TextView[normalize-space(@text)='Log in with OTP']"
