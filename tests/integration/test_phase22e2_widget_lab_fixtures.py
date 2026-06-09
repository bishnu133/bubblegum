"""Phase 22E-2: end-to-end demonstration of the new fixtures.

Before 22E-2 every widget-lab test had to launch Playwright, build a
context, open a page, set timeouts, and wrap it in a BubblegumSession by
hand. With `bubblegum_web` + `widget_lab` that whole prologue collapses
to a function signature.

Gated by `--playwright`; the unit suite covers fixture surface separately.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.bubblegum, pytest.mark.asyncio]


async def test_native_select_with_fixtures(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/select.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    step = await bubblegum_web.act("Select India from Country")

    assert step.status == "passed"
    assert await bubblegum_web.page.locator("#country").input_value() == "IN"
    bubblegum_web.assert_all_passed()


async def test_checkbox_with_fixtures(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/checkboxes.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    await bubblegum_web.act("Check Newsletter")
    await bubblegum_web.act("Uncheck Marketing emails")

    assert await bubblegum_web.page.locator("#cb_newsletter").is_checked() is True
    assert await bubblegum_web.page.locator("#cb_marketing").is_checked() is False
    bubblegum_web.assert_all_passed()
