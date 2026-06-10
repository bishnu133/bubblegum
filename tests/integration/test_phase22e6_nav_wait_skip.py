"""Phase 22E-6: nav-wait skip on non-navigating roles — live integration.

Gated by ``--playwright``. Verifies against real Chromium that clicking a
toggle-style control (radio, tab) completes without the cosmetic 5 s
wait_for_url probe, and that link/button clicks still get the probe so
real navigations keep working.
"""

from __future__ import annotations

import time

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.bubblegum, pytest.mark.asyncio]


async def test_radio_click_skips_nav_wait(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/radios.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    t0 = time.monotonic()
    result = await bubblegum_web.act("Click Red radio")
    elapsed = time.monotonic() - t0

    assert await bubblegum_web.is_checked("Red")
    assert result.target is not None
    assert result.target.metadata.get("nav_wait_skipped") is True
    assert result.target.metadata.get("nav_wait_skipped_role") == "radio"
    # Before 22E-6 this click always burned the full 5 s wait_for_url timeout.
    assert elapsed < 4.5
    bubblegum_web.assert_all_passed()


async def test_tab_click_skips_nav_wait(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/tabs.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    result = await bubblegum_web.act("Click Billing tab")

    assert (
        await bubblegum_web.page.locator("#tab-billing").get_attribute("aria-selected")
    ) == "true"
    assert result.target is not None
    assert result.target.metadata.get("nav_wait_skipped") is True
    assert result.target.metadata.get("nav_wait_skipped_role") == "tab"
    bubblegum_web.assert_all_passed()


async def test_link_click_still_waits_for_navigation(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/link_vs_button.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    result = await bubblegum_web.act("Click the Sign in link")

    # The probe must have run (no skip) and observed the navigation.
    assert result.target is not None
    assert "nav_wait_skipped" not in result.target.metadata
    assert bubblegum_web.page.url.endswith("link-clicked.html")
    bubblegum_web.assert_all_passed()
