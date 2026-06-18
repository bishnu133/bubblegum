"""Table-cell and link-by-text click actions — live integration.

Gated by ``--playwright``. Drives the ant_table widget page (PPHID cells contain
links whose text is a dynamic id, not the column name):

  - click a cell's element by column + row ("the PPHID link in the first row")
  - click a cell by a row matched on another column's value
  - click a link by its (dynamic) text
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.bubblegum, pytest.mark.asyncio]

FIRST = "9ca87fc7-bacc-4458-b8ce-3ee228534382"
SECOND = "1111aaaa-bbbb-cccc-dddd-222233334444"


async def test_click_cell_link_by_column_and_row(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/ant_table.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    res = await bubblegum_web.act("Click the PPHID link in the first result row")
    assert res.status in ("passed", "recovered"), res.error
    assert await bubblegum_web.is_visible(f"Opened: {FIRST}")


async def test_click_cell_under_column_natural_phrasing(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/ant_table.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    res = await bubblegum_web.act("under the PPHID column, click the last row value")
    assert res.status in ("passed", "recovered"), res.error
    assert await bubblegum_web.is_visible(f"Opened: {SECOND}")


async def test_click_cell_by_row_match(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/ant_table.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    res = await bubblegum_web.act(
        "click cell", column="PPHID", row_match={"Name": "Other Person"})
    assert res.status in ("passed", "recovered"), res.error
    assert await bubblegum_web.is_visible(f"Opened: {SECOND}")


async def test_click_link_by_dynamic_text(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/ant_table.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    res = await bubblegum_web.act(f'click the link with text "{FIRST}"')
    assert res.status in ("passed", "recovered"), res.error
    assert await bubblegum_web.is_visible(f"Opened: {FIRST}")
