"""Regression tests for verify text extraction and multi-column row assertions."""
from __future__ import annotations

from bubblegum.core.parser.instruction import extract_expected
from bubblegum.core.table import parse_table_spec


# --- "the <X> page appear(s)" reduces to the heading text --------------------


def test_extract_expected_page_appearance():
    assert extract_expected("the Create Badge page appear") == "Create Badge"
    assert extract_expected("Create Badge page appears") == "Create Badge"
    assert extract_expected("the Configure Reward page appear") == "Configure Reward"
    assert extract_expected("the Reward Configuration page loaded") == "Reward Configuration"


def test_extract_expected_keeps_existing_behaviour():
    assert extract_expected("Verify Dashboard is visible") == "Dashboard"
    assert extract_expected("Login button visible") == "Login button"


# --- multi-column row assertions --------------------------------------------


def test_row_multi_column_parse():
    spec = parse_table_spec(
        'in the row where Badge Internal Name is "BadgeInternalName-1", '
        'Status is "Submitted", Badge Type is "Proficiency"'
    )
    assert spec == {
        "row_match": {"Badge Internal Name": "BadgeInternalName-1"},
        "cell": {"Status": "Submitted", "Badge Type": "Proficiency"},
    }


def test_row_single_column_still_works():
    spec = parse_table_spec(
        'in the row where Name is "Bishnu", Account Status is "Active"'
    )
    assert spec == {"row_match": {"Name": "Bishnu"}, "cell": {"Account Status": "Active"}}


def test_row_tolerates_trailing_is_visible():
    spec = parse_table_spec(
        'in the row where Config Reference is "RC-1", Status is "Submitted" is visible'
    )
    assert spec == {"row_match": {"Config Reference": "RC-1"}, "cell": {"Status": "Submitted"}}


def test_row_value_with_comma_is_preserved():
    spec = parse_table_spec(
        'in the row where Name is "Doe, John", Status is "Active"'
    )
    assert spec == {"row_match": {"Name": "Doe, John"}, "cell": {"Status": "Active"}}
