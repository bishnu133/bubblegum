"""Mobile label→input + clickable-ancestor grounding (real-app bug fixes).

Reproduces the Healthy 365 (React Native) login screen from the bug report:
a field's visible label is a separate TextView next to the EditText, and a
tappable "link" is a non-clickable TextView inside a clickable View. These are
universal across native / RN / Compose / Flutter forms, so the fixes are generic.
"""

from __future__ import annotations

import json

from bubblegum.core import sdk
from bubblegum.core.mobile.field_association import resolve_field_ref
from bubblegum.core.schemas import ExecutionOptions, StepIntent


# Two labelled inputs, each label a sibling of its EditText inside its own
# container — verbatim shape from the H365 page source in the bug report.
_LOGIN_XML = """<hierarchy>
  <android.view.ViewGroup resource-id="inputContainer" bounds="[63,689][1017,869]">
    <android.widget.TextView text="NRIC or FIN" resource-id="nricInput-Label" bounds="[63,689][1017,773]"/>
    <android.widget.EditText content-desc="nricInput" resource-id="nricInput" clickable="true" bounds="[63,773][1017,867]"/>
  </android.view.ViewGroup>
  <android.view.ViewGroup resource-id="inputContainer" bounds="[63,948][1017,1129]">
    <android.widget.TextView text="Mobile number" resource-id="mobileNumberInput-Label" bounds="[63,948][1017,1032]"/>
    <android.widget.EditText content-desc="mobileNumberInput" resource-id="mobileNumberInput" clickable="true" bounds="[63,1032][1017,1126]"/>
  </android.view.ViewGroup>
</hierarchy>"""

# A tappable "link": the text node is not clickable; its ancestor View is.
_LINK_XML = """<hierarchy>
  <android.view.View resource-id="login-with-otp-link" clickable="true" bounds="[0,0][500,100]">
    <android.widget.TextView text="Log in with OTP " clickable="false" bounds="[10,10][490,90]"/>
  </android.view.View>
</hierarchy>"""


def _xpath(result) -> str:
    return json.loads(result["ref"])["value"]


# ----------------------------------------------------------------------
# label → input (type)
# ----------------------------------------------------------------------

def test_label_to_input_targets_correct_editable():
    r = resolve_field_ref(hierarchy_xml=_LOGIN_XML, target_phrase='"NRIC or FIN" input field', action_type="type")
    assert r["strategy"] == "label_to_input"
    assert "nricInput" in _xpath(r)
    assert "resource-id" in _xpath(r)


def test_label_to_input_disambiguates_by_container():
    # "Mobile number" must resolve to the mobile input, not the first field.
    r = resolve_field_ref(hierarchy_xml=_LOGIN_XML, target_phrase='"Mobile number" input field', action_type="type")
    assert "mobileNumberInput" in _xpath(r)
    assert "nricInput" not in _xpath(r)


def test_self_labelled_editable_matches_by_content_desc():
    xml = '<hierarchy><android.widget.EditText content-desc="Search" resource-id="search" clickable="true" bounds="[0,0][100,50]"/></hierarchy>'
    r = resolve_field_ref(hierarchy_xml=xml, target_phrase="Search", action_type="type")
    assert r is not None
    assert "search" in _xpath(r)


def test_type_with_no_editable_returns_none():
    xml = '<hierarchy><android.widget.TextView text="Just a label"/></hierarchy>'
    assert resolve_field_ref(hierarchy_xml=xml, target_phrase="Just a label", action_type="type") is None


def test_type_with_unknown_label_returns_none():
    assert resolve_field_ref(hierarchy_xml=_LOGIN_XML, target_phrase="Passport number", action_type="type") is None


# ----------------------------------------------------------------------
# clickable ancestor (tap)
# ----------------------------------------------------------------------

def test_tap_redirects_to_clickable_ancestor():
    r = resolve_field_ref(hierarchy_xml=_LINK_XML, target_phrase='"Log in with OTP"', action_type="tap")
    assert r["strategy"] == "clickable_ancestor"
    assert "login-with-otp-link" in _xpath(r)


def test_tap_on_already_clickable_node_returns_none():
    # Grounding already handles a directly-clickable match; no redirect needed.
    xml = '<hierarchy><android.widget.Button text="Submit" clickable="true" bounds="[0,0][100,50]"/></hierarchy>'
    assert resolve_field_ref(hierarchy_xml=xml, target_phrase="Submit", action_type="tap") is None


# ----------------------------------------------------------------------
# guards
# ----------------------------------------------------------------------

def test_empty_or_bad_inputs_are_safe():
    assert resolve_field_ref(hierarchy_xml="", target_phrase="x", action_type="type") is None
    assert resolve_field_ref(hierarchy_xml=_LOGIN_XML, target_phrase="", action_type="type") is None
    assert resolve_field_ref(hierarchy_xml="<broken", target_phrase="x", action_type="type") is None


def test_non_type_non_tap_action_returns_none():
    assert resolve_field_ref(hierarchy_xml=_LOGIN_XML, target_phrase="NRIC or FIN", action_type="scroll") is None


# ----------------------------------------------------------------------
# SDK fallback wrapper
# ----------------------------------------------------------------------

def _intent(phrase: str, action: str, xml: str) -> StepIntent:
    return StepIntent(
        instruction=f"{action} {phrase}",
        channel="mobile",
        platform="android",
        action_type=action,
        target_phrase=phrase,
        context={"hierarchy_xml": xml},
        options=ExecutionOptions(),
    )


def test_sdk_wrapper_resolves_labelled_input():
    intent = _intent("NRIC or FIN input field", "type", _LOGIN_XML)
    target = sdk._maybe_resolve_mobile_field("mobile", intent)
    assert target is not None
    assert target.resolver_name == "mobile_field_association"
    assert "nricInput" in target.ref
    assert target.metadata["strategy"] == "label_to_input"


def test_sdk_wrapper_noop_on_web():
    intent = _intent("NRIC or FIN", "type", _LOGIN_XML)
    assert sdk._maybe_resolve_mobile_field("web", intent) is None
