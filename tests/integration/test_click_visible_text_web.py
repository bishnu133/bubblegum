"""Regression: disambiguate a click by visible text.

Two controls can share an accessible name when one gets its name from a
decorative icon's ``aria-label``: an icon-only trigger
(``<span role="button"><span role="img" aria-label="search">``) and a real
button with visible text (``<button><icon/><span>Search</span></button>``) both
answer to ``role=button[name="search"]``. "Click the Search button" must land on
the one whose *visible* text is "Search", not the first DOM match (the icon).

Runs against a real browser; skips when none is available.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.asyncio]

# Icon-only trigger appears BEFORE the text button in the DOM, so a naive
# first-match pick would wrongly choose the icon.
_DOM = """
<!doctype html><html><body>
 <span id="iconTrigger" role="button" tabindex="-1" class="ant-table-filter-trigger">
   <span role="img" aria-label="search" class="anticon anticon-search">S</span></span>
 <div class="ant-table-filter-dropdown"><div style="padding:8px">
   <button id="applyBtn" type="button" class="ant-btn ant-btn-primary ant-btn-sm">
     <span class="ant-btn-icon"><span role="img" aria-label="search" class="anticon anticon-search">S</span></span>
     <span>Search</span></button>
   <button type="button" class="ant-btn ant-btn-default ant-btn-sm"><span>Reset</span></button>
 </div></div>
 <script>window.__c="";
  document.getElementById('iconTrigger').addEventListener('click',()=>window.__c='ICON');
  document.getElementById('applyBtn').addEventListener('click',()=>window.__c='BUTTON');
 </script></body></html>
"""


async def _click(instr):
    aw = pytest.importorskip("playwright.async_api")
    launch_kwargs = {}
    exe = os.environ.get("BG_CHROMIUM_EXECUTABLE")
    if exe:
        launch_kwargs["executable_path"] = exe
    from bubblegum import act, configure_runtime
    configure_runtime()
    async with aw.async_playwright() as p:
        try:
            browser = await p.chromium.launch(**launch_kwargs)
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"No usable Chromium binary: {exc}")
        try:
            page = await browser.new_page()
            await page.set_content(_DOM)
            res = await act(instr, channel="web", page=page)
            return res.status, await page.evaluate("window.__c")
        finally:
            await browser.close()


async def test_click_search_button_prefers_visible_text_over_icon():
    status, clicked = await _click("Click the Search button")
    assert status in ("passed", "recovered")
    assert clicked == "BUTTON", "clicked the icon-only trigger instead of the labelled button"
