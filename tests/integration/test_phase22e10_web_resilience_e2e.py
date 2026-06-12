"""Web resilience features — live integration smoke (gated by --playwright).

Drives the new web improvements through the public ``bubblegum_web`` +
``widget_lab`` fixtures end-to-end:

  - iframe routing      : "Click Pay Now" inside a same-origin iframe
  - select-by-label     : "Select United States from Country" (label != value)

Browser-free logic for these features is covered in
tests/unit/test_web_resilience.py; this module proves the production NL flow
against a real Chromium page.

NOTE ON THE FILENAME: the ``test_phase22e*`` prefix is load-bearing, not
cosmetic. The async ``bubblegum_web`` fixture (pytest-asyncio) cannot be set up
after pytest-playwright's *sync* ``page`` fixture has run in the same session —
doing so raises "Runner.run() cannot be called from a running event loop". All
``bubblegum_web`` suites are therefore named to sort before
``test_playwright_adapter.py`` (the only module using the sync ``page``
fixture). Keep this file inside that ``phase22e`` block.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.bubblegum, pytest.mark.asyncio]


async def test_click_button_inside_iframe(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/iframe.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")
    # Ensure the child frame has rendered before grounding.
    await bubblegum_web.page.frame_locator("#payment").locator("#pay").wait_for()

    await bubblegum_web.act("Click Pay Now")

    inner_status = bubblegum_web.page.frame_locator("#payment").locator("#inner-status")
    assert (await inner_status.inner_text()) == "paid"
    bubblegum_web.assert_all_passed()


async def test_select_native_option_by_visible_label(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/select.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    # "United States" is the visible label; its option value is "US".
    await bubblegum_web.act('Select "United States" from Country')

    assert await bubblegum_web.page.locator("#country").input_value() == "US"
    bubblegum_web.assert_all_passed()
