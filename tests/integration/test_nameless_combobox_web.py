"""PR6: nameless-combobox fallback — live integration smoke.

Gated by ``--playwright``. Drives the nameless_combobox widget (a
role="combobox" with no accessible name) through the public ``bubblegum_web`` +
``widget_lab`` fixtures, proving the NL flow opens and selects from a combobox
that has no aria-label / label — the MUI / Angular CDK overlay case.

  - "Open the fruit dropdown" => resolves the nameless combobox, expands it
  - "Click Banana"            => selects the option, value updates
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.bubblegum, pytest.mark.asyncio]


async def test_open_and_select_from_nameless_combobox(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/nameless_combobox.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    # The trigger has no accessible name; the dropdown intent + uniqueness
    # fallback must still resolve it.
    await bubblegum_web.act("Open the fruit dropdown")
    assert (
        await bubblegum_web.page.locator("#fruit-trigger").get_attribute("aria-expanded")
    ) == "true"

    await bubblegum_web.act("Click Banana")
    assert await bubblegum_web.is_visible("Selected: Banana")
    bubblegum_web.assert_all_passed()
