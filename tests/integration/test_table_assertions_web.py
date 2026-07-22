"""Table assertions — live integration against the ant_table widget page.

Gated by ``--playwright``. Proves the public ``verify`` table path on a real
Ant Design-style table (header/body split across two <table>s + a measure row):

  - columns present, via natural language and structured kwargs
  - a value under a column for a row matched by another column (DB-style key)
  - contained-text match (status cell renders "✓ Active")
  - a clear failure when the value is wrong
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.bubblegum, pytest.mark.asyncio]


async def test_columns_present_natural_language(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/ant_table.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    res = await bubblegum_web.verify(
        "the table has columns RecordID, Account Status and Profile Status"
    )
    assert res.status in ("passed", "recovered"), res.error
    bubblegum_web.assert_all_passed()


async def test_columns_present_structured(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/ant_table.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    res = await bubblegum_web.verify(
        "participant table columns",
        assertion_type="table",
        columns=["RecordID", "AltID", "Name", "Account Status", "Profile Status"],
    )
    assert res.status in ("passed", "recovered"), res.error


async def test_value_under_column_for_matched_row(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/ant_table.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    # DB-style: the key (Name / RecordID) and expected value are parameters.
    res = await bubblegum_web.verify(
        "participant status",
        assertion_type="table",
        row_match={"Name": "Test Account"},
        cell={"Account Status": "Active", "Profile Status": "Verified"},
    )
    assert res.status in ("passed", "recovered"), res.error


async def test_value_under_column_natural_language(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/ant_table.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    res = await bubblegum_web.verify(
        'in the row where Name is "Test Account", Account Status is "Active"'
    )
    assert res.status in ("passed", "recovered"), res.error


async def test_wrong_value_fails_clearly(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/ant_table.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    res = await bubblegum_web.verify(
        "participant status",
        assertion_type="table",
        row_match={"Name": "Test Account"},
        cell={"Account Status": "Withdrawn"},
        timeout_ms=1000,
    )
    assert res.status == "failed"
    assert "did not match" in (res.error.message or "")
