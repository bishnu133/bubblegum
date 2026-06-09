"""Phase 22E-5: Tier 2 widgets — live integration smoke.

Gated by ``--playwright``. Drives the three new widget lab scenarios
through the public ``bubblegum_web`` + ``widget_lab`` fixtures so we
exercise the production NL flow end-to-end:

  - Click X tab        => role=tab[name=X], aria-selected flips
  - Expand X section   => role=button (accordion header), aria-expanded flips
  - Set Volume to 75   => action=set, role=slider, value updates + event fires
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.bubblegum, pytest.mark.asyncio]


async def test_tabs_click_selects_billing(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/tabs.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    await bubblegum_web.act("Click Billing tab")

    assert (
        await bubblegum_web.page.locator("#tab-billing").get_attribute("aria-selected")
    ) == "true"
    assert await bubblegum_web.is_visible("Billing")
    assert not await bubblegum_web.page.locator("#panel-profile").is_visible()
    bubblegum_web.assert_all_passed()


async def test_accordion_expand_billing(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/accordion.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    await bubblegum_web.act("Expand Billing section")

    assert (
        await bubblegum_web.page.locator("#hdr-billing").get_attribute("aria-expanded")
    ) == "true"
    assert await bubblegum_web.page.locator("#region-billing").is_visible()
    bubblegum_web.assert_all_passed()


async def test_slider_set_volume(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/slider.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    await bubblegum_web.act("Set Volume to 75")

    assert await bubblegum_web.page.locator("#volume-slider").input_value() == "75"
    # Brightness untouched
    assert await bubblegum_web.page.locator("#brightness-slider").input_value() == "50"
    # The input handler updated the live result line
    result_text = await bubblegum_web.page.locator("#result").inner_text()
    assert "Volume is 75" in result_text
    bubblegum_web.assert_all_passed()
