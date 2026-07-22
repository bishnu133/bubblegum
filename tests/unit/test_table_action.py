"""Table-cell and link-by-text click actions.

Covers parse_table_action (NL + structured kwargs) and the SDK routing helper
_maybe_resolve_table_or_link, using a fake adapter (no browser).
"""

from __future__ import annotations

import asyncio

import bubblegum.core.sdk as sdk
from bubblegum.core.table import parse_table_action


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def test_parse_cell_under_column_click_row():
    assert parse_table_action("under the RecordID column, click the 1st row value") == {
        "kind": "cell", "column": "RecordID", "row_index": 1}


def test_parse_cell_link_in_first_result_row():
    assert parse_table_action("Click the RecordID link in the first result row") == {
        "kind": "cell", "column": "RecordID", "row_index": 1}


def test_parse_cell_last_row():
    assert parse_table_action("click the last row Name") == {
        "kind": "cell", "column": "Name", "row_index": -1}


def test_parse_cell_row_match():
    assert parse_table_action(
        'in the row where Name is "Test Account", click the RecordID value'
    ) == {"kind": "cell", "column": "RecordID", "row_match": {"Name": "Test Account"}}


def test_parse_link_with_text():
    assert parse_table_action('click the link with text "9ca87fc7-bacc"') == {
        "kind": "link", "text": "9ca87fc7-bacc", "exact": False}


def test_parse_structured_kwargs():
    assert parse_table_action("anything", {"column": "RecordID", "row": "first"}) == {
        "kind": "cell", "column": "RecordID", "row_index": 1}
    assert parse_table_action("anything", {"link_text": "9ca8"}) == {
        "kind": "link", "text": "9ca8", "exact": False}
    assert parse_table_action("x", {"column": "Status", "row_match": {"Name": "A"}}) == {
        "kind": "cell", "column": "Status", "row_match": {"Name": "A"}}


def test_parse_non_table_actions_return_none():
    assert parse_table_action("Click the Search button") is None
    assert parse_table_action("Select Participant from the search type dropdown") is None


# ---------------------------------------------------------------------------
# SDK routing
# ---------------------------------------------------------------------------

class _Adapter:
    def __init__(self):
        self.cell_calls = []
        self.link_calls = []

    async def find_table_cell(self, *, column, row_index=None, row_match=None, prefer_clickable=True):
        self.cell_calls.append((column, row_index, row_match))
        return '[data-bg-cell="1"]'

    async def find_link(self, text, *, exact=False):
        self.link_calls.append((text, exact))
        return '[data-bg-link="1"]'


def _run(coro):
    return asyncio.run(coro)


def test_routing_resolves_cell_click():
    adapter = _Adapter()
    target = _run(sdk._maybe_resolve_table_or_link(
        adapter, "web", "Click the RecordID link in the first result row", {}))
    assert target is not None
    assert target.ref == '[data-bg-cell="1"]'
    assert target.resolver_name == "table_cell_dom"
    assert adapter.cell_calls == [("RecordID", 1, None)]


def test_routing_resolves_link_click():
    adapter = _Adapter()
    target = _run(sdk._maybe_resolve_table_or_link(
        adapter, "web", 'click the link with text "9ca8"', {}))
    assert target.ref == '[data-bg-link="1"]'
    assert target.resolver_name == "link_dom"
    assert adapter.link_calls == [("9ca8", False)]


def test_routing_passes_structured_kwargs():
    adapter = _Adapter()
    _run(sdk._maybe_resolve_table_or_link(
        adapter, "web", "open it", {"column": "RecordID", "row": "first"}))
    assert adapter.cell_calls == [("RecordID", 1, None)]


def test_routing_skips_non_table_steps():
    adapter = _Adapter()
    assert _run(sdk._maybe_resolve_table_or_link(adapter, "web", "Click the Save button", {})) is None
    assert adapter.cell_calls == [] and adapter.link_calls == []


def test_routing_skips_mobile():
    adapter = _Adapter()
    assert _run(sdk._maybe_resolve_table_or_link(
        adapter, "mobile", "Click the RecordID link in the first row", {})) is None
