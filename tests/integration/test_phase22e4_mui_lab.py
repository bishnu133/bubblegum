"""Phase 22E-4: MUI lab — live integration test via bubblegum_web + a
custom ``mui_lab`` fixture that points the shared static server at the
MUI lab pages directory.

Gated by ``--playwright``. Uses the same NL surface the regression
runner exercises, but through the pytest fixtures so callers can see
how a tester would write these scenarios in their own suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.bubblegum, pytest.mark.asyncio]


_PAGES_DIR = (
    Path(__file__).resolve().parents[2]
    / "examples" / "web" / "widgets" / "mui_lab" / "pages"
)


@pytest.fixture(scope="session")
def mui_lab():
    """Yield base URL of an HTTP server serving the MUI lab pages."""
    from bubblegum.testing.widget_lab import start_widget_lab_server

    server, base_url = start_widget_lab_server(pages_dir=_PAGES_DIR)
    try:
        yield base_url
    finally:
        server.shutdown()


async def test_mui_select_picks_india(bubblegum_web, mui_lab):
    await bubblegum_web.page.goto(f"{mui_lab}/select.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    await bubblegum_web.act("Click Country")
    await bubblegum_web.page.wait_for_selector(
        "#country-menu", state="visible", timeout=3000
    )
    await bubblegum_web.act("Click India")

    assert await bubblegum_web.page.locator("#country-value").input_value() == "IN"
    bubblegum_web.assert_all_passed()


async def test_mui_checkbox_check_and_uncheck(bubblegum_web, mui_lab):
    await bubblegum_web.page.goto(f"{mui_lab}/checkbox.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    await bubblegum_web.act("Check Newsletter")
    await bubblegum_web.act("Uncheck Marketing emails")

    assert await bubblegum_web.is_checked("Newsletter") is True
    assert await bubblegum_web.is_checked("Marketing emails") is False
    bubblegum_web.assert_all_passed()


async def test_mui_dialog_save_round_trip(bubblegum_web, mui_lab):
    await bubblegum_web.page.goto(f"{mui_lab}/dialog.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    await bubblegum_web.act("Click Edit Profile")
    await bubblegum_web.page.wait_for_selector(
        "#edit-dialog[aria-modal='true']", state="visible", timeout=3000
    )

    await bubblegum_web.act('Enter "Sam" into Name')
    await bubblegum_web.act("Click Save")

    await bubblegum_web.page.wait_for_selector(
        "#edit-backdrop", state="detached", timeout=3000
    )
    result_text = await bubblegum_web.page.locator("#result").inner_text()
    assert "Saved name: Sam" in result_text
    bubblegum_web.assert_all_passed()


async def test_mui_autocomplete_filter_and_pick(bubblegum_web, mui_lab):
    await bubblegum_web.page.goto(f"{mui_lab}/autocomplete.html")
    await bubblegum_web.page.wait_for_load_state("domcontentloaded")

    # Typing "In" narrows the listbox to India / Indonesia / etc.
    await bubblegum_web.act('Enter "In" into Country')
    await bubblegum_web.page.wait_for_selector(
        "#country-listbox", state="visible", timeout=3000
    )

    await bubblegum_web.act("Click India")

    assert await bubblegum_web.page.locator("#country-input").input_value() == "India"
    bubblegum_web.assert_all_passed()
