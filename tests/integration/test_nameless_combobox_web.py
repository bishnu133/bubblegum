"""PR6: nameless-combobox fallback — live integration smoke.

Gated by ``--playwright``. Drives the nameless_combobox widget (a
role="combobox" with no accessible name) through the public ``bubblegum_web`` +
``widget_lab`` fixtures, proving the NL flow opens and selects from a combobox
that has no aria-label / label — the MUI / Angular CDK overlay case.

  - "Open the fruit dropdown" => resolves the nameless combobox, expands it
  - "Click Banana"            => selects the option, value updates

The assertions surface the a11y snapshot + resolver on failure so a regression
is diagnosable without a local browser.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.bubblegum, pytest.mark.asyncio]


async def test_open_and_select_from_nameless_combobox(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/nameless_combobox.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    snapshot = await bubblegum_web.page.locator("body").aria_snapshot()

    # The trigger has no accessible name; the dropdown intent + uniqueness
    # fallback must still resolve it.
    open_result = await bubblegum_web.act("Open the fruit dropdown")
    assert open_result.status in ("passed", "recovered"), (
        f"'Open the fruit dropdown' did not resolve/execute: status="
        f"{open_result.status}, resolver="
        f"{open_result.target.resolver_name if open_result.target else None}, "
        f"error={open_result.error.message if open_result.error else None}\n"
        f"--- aria snapshot ---\n{snapshot}"
    )
    assert (
        await bubblegum_web.page.locator("#fruit-trigger").get_attribute("aria-expanded")
    ) == "true", f"dropdown did not open. resolver={open_result.target.resolver_name}\n{snapshot}"

    await bubblegum_web.act("Click Banana")
    assert await bubblegum_web.is_visible("Selected: Banana")
    bubblegum_web.assert_all_passed()
