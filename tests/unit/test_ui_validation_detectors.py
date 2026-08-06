"""Browser-free unit tests for the new UI-validation detectors and the
row-scoped table-action parser (V1-V6).

The end-to-end behaviour is covered by tests/integration/test_ui_validations_web.py
against a real browser; these guard the pure NL-parsing/routing decisions so a
regression is caught fast in the unit suite.
"""
from __future__ import annotations

import bubblegum.core.sdk as sdk
from bubblegum.core.table import parse_table_action


# --- V1: element-present detection + kind mapping ----------------------------

def test_present_detection_and_kind():
    f = sdk._looks_like_present_assertion
    assert f('the "Save" button is present', {})
    assert f("a table is present on the page", {})
    assert f("the Username textbox is visible", {})
    assert f("a listbox is displayed", {})
    # not a presence phrase
    assert not f('Select "France" from Country', {})
    # explicit other type opts out; explicit present opts in
    assert not f("the button is present", {"assertion_type": "text_visible"})
    assert f("anything", {"assertion_type": "present"})
    assert sdk._element_kind('the "Save" button is present') == "button"
    assert sdk._element_kind("a data grid is shown") == "grid"
    assert sdk._element_kind("the drop-down is present") == "dropdown"
    assert sdk._element_kind("the heading is present") == "heading"
    assert sdk._element_kind("nothing element-like here") is None


# --- V2: active/highlighted detection ----------------------------------------

def test_active_detection():
    f = sdk._looks_like_active_assertion
    assert f('the "Activities" menu is highlighted', {})
    assert f('the "Date and Time" step is active', {})
    assert f('the "Reports" tab is selected', {})
    assert f("the sidebar item is in bold", {})
    # bare "active" without a nav noun / quote must NOT trigger (e.g. GAQ text)
    assert not f("Get Active Questionnaire requirement is Required", {})
    assert f("anything", {"assertion_type": "highlighted"})


# --- V3: dropdown-options detection + list split -----------------------------

def test_dropdown_detection_and_split():
    f = sdk._looks_like_dropdown_assertion
    assert f('the "Programme" dropdown contains "A", "B"', {})
    assert f('the "Category" listbox has options "X", "Y"', {})
    # needs a listing cue AND expected values
    assert not f('the "Programme" dropdown is present', {})
    assert f('"Programme" dropdown', {"options": ["A", "B"]})
    assert sdk._split_option_list("the dropdown contains Alpha, Beta and Gamma") == ["Alpha", "Beta", "Gamma"]


# --- V4: alert detection -----------------------------------------------------

def test_alert_detection():
    f = sdk._looks_like_alert_assertion
    assert f('the alert says "Saved"', {})
    assert f('the alert description contains "cardio"', {})
    assert f('the notification shows "Done"', {})
    assert not f('the "Save" button is present', {})


# --- V5: page-header detection (single-quote guard) --------------------------

def test_header_detection():
    f = sdk._looks_like_header_assertion
    assert f('the page header is "General Information"', {})
    assert f('the page title is "Date and Time"', {})
    assert f('the header is "Overview"', {})
    # two quoted segments -> that's the multi-"all visible" text check, not header
    assert not f('the header shows "Active" and "Verified"', {})
    # a table column header must not be mistaken for the page header
    assert not f('the "Status" column header is "Active"', {})


# --- V6: row-scoped checkbox/link parsing ------------------------------------

def test_row_checkbox_parsing():
    assert parse_table_action('In the row where Date is "10/08/2026", select the checkbox') == {
        "kind": "cell", "control": "checkbox", "row_match": {"Date": "10/08/2026"}}
    assert parse_table_action('Select the checkbox in the row where Date is "10/08/2026"') == {
        "kind": "cell", "control": "checkbox", "row_match": {"Date": "10/08/2026"}}
    assert parse_table_action("tick the checkbox in the first row") == {
        "kind": "cell", "control": "checkbox", "row_index": 1}


def test_row_link_parsing():
    assert parse_table_action('In the row where Date is "10/08/2026", click the "Add Assessment" link') == {
        "kind": "cell", "control_text": "Add Assessment", "row_match": {"Date": "10/08/2026"}}
    assert parse_table_action('Click the "Add Assessment" link in the row where Day is Monday') == {
        "kind": "cell", "control_text": "Add Assessment", "row_match": {"Day": "Monday"}}


def test_row_link_by_index_stays_column_cell():
    # "click the COL link in the Nth row" keeps its existing column-cell meaning.
    assert parse_table_action("Click the RecordID link in the first result row") == {
        "kind": "cell", "column": "RecordID", "row_index": 1}
