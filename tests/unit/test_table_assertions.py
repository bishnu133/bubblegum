"""Table assertions: NL parsing, matcher evaluation, and verify() routing.

Covers the new ``assertion_type="table"`` page-scoped verify path and the
natural-language inference, using a fake adapter (no browser).
"""

from __future__ import annotations

import asyncio

import bubblegum.core.sdk as sdk
from bubblegum.core.table import (
    build_table_matcher,
    describe_table_matcher,
    evaluate_table,
    parse_table_spec,
)


# ---------------------------------------------------------------------------
# Natural-language parsing
# ---------------------------------------------------------------------------

def test_parse_columns_present():
    assert parse_table_spec(
        "the search results table shows the columns RecordID, Account Status and Profile Status"
    ) == {"columns": ["RecordID", "Account Status", "Profile Status"]}


def test_parse_row_keyed_cell():
    assert parse_table_spec(
        'in the row where Name is "Test Account", Account Status is "Active"'
    ) == {"row_match": {"Name": "Test Account"}, "cell": {"Account Status": "Active"}}


def test_parse_column_shows_value():
    assert parse_table_spec('the Account Status column shows "Active"') == {
        "cell": {"Account Status": "Active"}
    }


def test_parse_value_under_column():
    assert parse_table_spec('"Active" appears under the Account Status column') == {
        "cell": {"Account Status": "Active"}
    }


def test_parse_returns_none_for_non_table_phrases():
    assert parse_table_spec("Click the Search button") is None
    assert parse_table_spec("the page shows a success message") is None


# ---------------------------------------------------------------------------
# Matcher evaluation
# ---------------------------------------------------------------------------

_TABLES = [
    {
        "headers": ["RecordID", "AltID", "Name", "Account Status", "Profile Status"],
        "rows": [
            {"RecordID": "9ca8", "AltID": "30A", "Name": "Test Account",
             "Account Status": "Active", "Profile Status": "Verified"},
            {"RecordID": "1111", "AltID": "22B", "Name": "Other Person",
             "Account Status": "Withdrawn", "Profile Status": "Unverified"},
        ],
    }
]


def test_eval_columns_present_pass_and_fail():
    ok, _ = evaluate_table({"columns": ["RecordID", "Account Status", "Profile Status"]}, _TABLES)
    assert ok is True
    bad, detail = evaluate_table({"columns": ["RecordID", "Nope"]}, _TABLES)
    assert bad is False and "Nope" in detail


def test_eval_row_keyed_cell():
    ok, _ = evaluate_table(
        {"row_match": {"Name": "Test Account"}, "cell": {"Account Status": "Active"}},
        _TABLES,
    )
    assert ok is True

    bad, detail = evaluate_table(
        {"row_match": {"Name": "Test Account"}, "cell": {"Account Status": "Withdrawn"}},
        _TABLES,
    )
    assert bad is False and "did not match" in detail


def test_eval_row_match_not_found():
    bad, detail = evaluate_table(
        {"row_match": {"Name": "Ghost"}, "cell": {"Account Status": "Active"}}, _TABLES
    )
    assert bad is False and "no row where" in detail


def test_eval_cell_any_row_and_contains_match():
    # Tolerates a badge: expected "Active" is contained in "✓ Active".
    tables = [{"headers": ["Status"], "rows": [{"Status": "✓ Active"}]}]
    ok, _ = evaluate_table({"cell": {"Status": "Active"}}, tables)
    assert ok is True


def test_eval_no_tables():
    bad, detail = evaluate_table({"columns": ["X"]}, [])
    assert bad is False and "no tables" in detail


def test_build_matcher_prefers_kwargs():
    m = build_table_matcher("ignored", {"row_match": {"RecordID": "9ca8"}, "cell": {"Account Status": "Active"}})
    assert m == {"row_match": {"RecordID": "9ca8"}, "cell": {"Account Status": "Active"}}
    assert "Account Status" in describe_table_matcher(m)


# ---------------------------------------------------------------------------
# verify() routing through a fake adapter
# ---------------------------------------------------------------------------

class _FakeAdapter:
    def __init__(self, tables):
        self._tables = tables

    async def collect_context(self, *_a, **_k):  # pragma: no cover - not reached for table path
        raise AssertionError("table verify must not ground an element")

    async def extract_tables(self):
        return self._tables


def _run(coro):
    return asyncio.run(coro)


def _verify(monkeypatch, instruction, tables, **kwargs):
    adapter = _FakeAdapter(tables)
    monkeypatch.setattr(sdk, "_get_adapter", lambda *a, **k: adapter)
    return _run(sdk.verify(instruction, channel="web", page=object(), **kwargs))


def test_verify_structured_table_pass(monkeypatch):
    res = _verify(
        monkeypatch, "participant row", _TABLES,
        assertion_type="table",
        row_match={"Name": "Test Account"}, cell={"Account Status": "Active"},
    )
    assert res.status == "passed"
    assert res.target.resolver_name == "table"


def test_verify_structured_table_fail(monkeypatch):
    res = _verify(
        monkeypatch, "participant row", _TABLES,
        assertion_type="table",
        row_match={"Name": "Test Account"}, cell={"Account Status": "Withdrawn"},
        timeout_ms=0,
    )
    assert res.status == "failed"
    assert "did not match" in (res.error.message or "")


def test_verify_natural_language_columns_routes_to_table(monkeypatch):
    res = _verify(
        monkeypatch,
        "the table has columns RecordID, Account Status and Profile Status",
        _TABLES,
    )
    assert res.status == "passed"
    assert res.target.resolver_name == "table"
