"""Disambiguating multiple nameless selects — live integration.

Gated by ``--playwright``. The page has two nameless Ant-style selects (no
labels); the a11y snapshot can't ground a unique combobox, so resolution falls
back to the DOM and picks the one matching the step (by displayed value). Proves
"select X from the Y dropdown" works on a page with several comboboxes.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.bubblegum, pytest.mark.asyncio]


async def test_select_from_one_of_several_nameless_comboboxes(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/multi_select.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    snapshot = await bubblegum_web.page.locator("body").aria_snapshot()
    res = await bubblegum_web.act("Select Participant from the search type dropdown")
    assert res.status in ("passed", "recovered"), (
        f"multi-select disambiguation failed: status={res.status}, "
        f"error={res.error.message if res.error else None}\n--- aria ---\n{snapshot}"
    )
    assert await bubblegum_web.is_visible("Selected: Participant")
    bubblegum_web.assert_all_passed()
