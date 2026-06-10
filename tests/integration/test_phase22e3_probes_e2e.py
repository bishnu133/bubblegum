"""Phase 22E-3: live probes against real Chromium.

Gated by ``--playwright``. The fixture-finalizer auto-screenshot path is
covered by ``tests/unit/test_phase22e3_pytester_autoshot.py`` via
pytester (no live browser required).
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.bubblegum, pytest.mark.asyncio]


async def test_probes_read_real_widget_state(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/checkboxes.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    # Marketing emails starts checked; Newsletter starts unchecked.
    assert await bubblegum_web.is_checked("Marketing emails") is True
    assert await bubblegum_web.is_checked("Newsletter") is False

    await bubblegum_web.act("Check Newsletter")
    assert await bubblegum_web.is_checked("Newsletter") is True

    bubblegum_web.assert_all_passed()


async def test_selected_value_reads_native_select(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/select.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    await bubblegum_web.act("Select India from Country")

    assert await bubblegum_web.selected_value("Country") == "IN"


async def test_is_visible_against_visible_heading(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/checkboxes.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    assert await bubblegum_web.is_visible("Checkboxes") is True
