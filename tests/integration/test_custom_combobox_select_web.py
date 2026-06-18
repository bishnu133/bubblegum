"""One-step selection from a custom (non-native) combobox — live integration.

Gated by ``--playwright``. Proves a tester can pick an option from a
div/button-based combobox (Ant Design / MUI / Angular CDK pattern) with a
single plain-English line — no DOM selectors, no manual open-then-click:

    "Select India from the country dropdown"   (named trigger, portal listbox)
    "Select Banana from the fruit dropdown"    (nameless trigger)

The adapter detects the trigger is not a native <select>, opens it, then clicks
the matching option. The native <select> case is covered to prove the legacy
path is unchanged.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.bubblegum, pytest.mark.asyncio]


async def test_one_step_select_from_custom_combobox(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/combobox.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    snapshot = await bubblegum_web.page.locator("body").aria_snapshot()
    result = await bubblegum_web.act("Select India from the country dropdown")
    assert result.status in ("passed", "recovered"), (
        f"one-step select failed: status={result.status}, "
        f"resolver={result.target.resolver_name if result.target else None}, "
        f"error={result.error.message if result.error else None}\n"
        f"--- aria snapshot ---\n{snapshot}"
    )
    assert await bubblegum_web.is_visible("Selected: India")
    bubblegum_web.assert_all_passed()


async def test_one_step_select_from_nameless_combobox(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/nameless_combobox.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    snapshot = await bubblegum_web.page.locator("body").aria_snapshot()
    result = await bubblegum_web.act("Select Banana from the fruit dropdown")
    assert result.status in ("passed", "recovered"), (
        f"one-step select on nameless combobox failed: status={result.status}, "
        f"resolver={result.target.resolver_name if result.target else None}, "
        f"error={result.error.message if result.error else None}\n"
        f"--- aria snapshot ---\n{snapshot}"
    )
    assert await bubblegum_web.is_visible("Selected: Banana")
    bubblegum_web.assert_all_passed()


async def test_one_step_select_from_ant_style_overlay_combobox(bubblegum_web, widget_lab):
    # Reproduces the real Ant Design failure: the inner role=combobox <input> is
    # covered by a selection <span>, so a non-forced click is intercepted. The
    # current value ("Participant") is also an option, so the option must be
    # targeted by role, not text. Pick a *different* option to prove the change.
    await bubblegum_web.page.goto(f"{widget_lab}/ant_select.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    snapshot = await bubblegum_web.page.locator("body").aria_snapshot()
    result = await bubblegum_web.act("Select Tracker from the search type dropdown")
    assert result.status in ("passed", "recovered"), (
        f"ant-style one-step select failed: status={result.status}, "
        f"resolver={result.target.resolver_name if result.target else None}, "
        f"error={result.error.message if result.error else None}\n"
        f"--- aria snapshot ---\n{snapshot}"
    )
    assert await bubblegum_web.is_visible("Selected: Tracker")
    bubblegum_web.assert_all_passed()


async def test_one_step_select_native_select_unchanged(bubblegum_web, widget_lab):
    await bubblegum_web.page.goto(f"{widget_lab}/select.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    result = await bubblegum_web.act("Select India from the country dropdown")
    assert result.status in ("passed", "recovered")
    assert await bubblegum_web.is_visible("Selected: India")
    bubblegum_web.assert_all_passed()
