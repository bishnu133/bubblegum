"""Parsing of column-scoped header-control clicks ("the Search icon of the Title
column") and its gating against ordinary clicks and row/cell actions."""

from __future__ import annotations

import pytest

from bubblegum.core.table import parse_column_header_control, parse_table_action


@pytest.mark.parametrize(
    "phrase,column,control",
    [
        ("Click on the Search icon of Title Column", "Title", "Search icon"),
        ("Click on the Search icon of Updated By Column", "Updated By", "Search icon"),
        ("Click the filter icon in the Status column", "Status", "filter icon"),
        ('Click the search icon in the "Updated By" column header', "Updated By", "search icon"),
        ("Click the Title column search icon", "Title", "search icon"),
        ("Click the Division column's filter", "Division", "filter"),
        ("Click the sort icon of Start column", "Start", "sort icon"),
        ("Tap the menu icon for the Name column", "Name", "menu icon"),
    ],
)
def test_parses_column_scoped_header_control(phrase, column, control):
    assert parse_column_header_control(phrase) == {"column": column, "control": control}


@pytest.mark.parametrize(
    "phrase",
    [
        "Click on the Search icon",                      # unscoped — unchanged behaviour
        "Click the Search button",
        "Click the Edit button in the Actions column",   # a row/cell control, not a header one
        "Click the Status column header",                # no header control named
        "Click the RecordID value in the 1st row",       # existing table-cell action
        "Click Save",
    ],
)
def test_does_not_claim_other_clicks(phrase):
    assert parse_column_header_control(phrase) is None


def test_existing_table_cell_action_unaffected():
    spec = parse_table_action("Click the RecordID value in the 1st row", {})
    assert spec == {"kind": "cell", "column": "RecordID", "row_index": 1}
