"""Phase 22E-7: shared-browser fixtures — live integration.

Gated by ``--playwright``. Drives ``bubblegum_browser`` + ``bubblegum_page``
against real Chromium:

  - the same Browser instance is reused across tests (launch paid once)
  - each test still gets an isolated context (state does not leak)
  - ``BubblegumSession.goto`` navigates and the NL flow works end-to-end

Tests in this module run on the session event loop because Playwright
objects are bound to the loop that created them and the shared browser
lives on the session loop.
"""

from __future__ import annotations

import pytest

pytestmark = [
    pytest.mark.playwright,
    pytest.mark.bubblegum,
    pytest.mark.asyncio(loop_scope="session"),
]

_seen_browser_ids: set[int] = set()


async def test_page_fixture_runs_nl_flow_on_shared_browser(
    bubblegum_page, bubblegum_browser, widget_lab
):
    _seen_browser_ids.add(id(bubblegum_browser))

    await bubblegum_page.goto(f"{widget_lab}/radios.html")
    await bubblegum_page.act("Click Red radio")

    assert await bubblegum_page.is_checked("Red")
    bubblegum_page.assert_all_passed()

    # Leave state behind so the next test can prove context isolation.
    await bubblegum_page.page.evaluate("localStorage.setItem('bubblegum', 'leaky')")


async def test_browser_is_reused_and_context_is_isolated(
    bubblegum_page, bubblegum_browser, widget_lab
):
    # Same Browser object as the previous test — Chromium launched once.
    assert _seen_browser_ids == {id(bubblegum_browser)}

    await bubblegum_page.goto(f"{widget_lab}/radios.html")

    # Fresh incognito context: the previous test's localStorage is gone
    # and its radio selection did not carry over.
    leaked = await bubblegum_page.page.evaluate("localStorage.getItem('bubblegum')")
    assert leaked is None
    assert not await bubblegum_page.is_checked("Red")


async def test_goto_waits_for_dom_so_act_resolves_immediately(
    bubblegum_page, widget_lab
):
    await bubblegum_page.goto(f"{widget_lab}/tabs.html")

    await bubblegum_page.act("Click Billing tab")

    assert (
        await bubblegum_page.page.locator("#tab-billing").get_attribute("aria-selected")
    ) == "true"
    bubblegum_page.assert_all_passed()
