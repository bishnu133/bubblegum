"""A nav item collapsed into a responsive "…"/More overflow menu is still clicked.

When the window is narrow, a nav bar hides overflowing items behind a "…" trigger
(Ant `.ant-menu-overflow-item-rest`, or a generic aria-haspopup More control), so
the item ("My Account") isn't on the visible bar. The engine now opens the
overflow trigger and clicks the revealed item — generic across nav libraries.

Runs against a real (headless) browser; skips when none is available.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [pytest.mark.playwright, pytest.mark.asyncio]

# "Activities" stays on the bar; "My Account" is collapsed into the "…" rest item
# and only mounts into a popup when the "…" is opened.
_PAGE = """
<!doctype html><html><head><style>
  body { margin:0; font-family:Helvetica; }
  #pop { display:none; position:absolute; top:40px; left:200px; background:#fff;
         border:1px solid #ccc; padding:8px; }
</style></head><body>
  <ul class="ant-menu ant-menu-overflow ant-menu-horizontal" role="menu">
    <li class="ant-menu-overflow-item ant-menu-item" role="menuitem">Activities</li>
    <li class="ant-menu-overflow-item ant-menu-overflow-item-rest ant-menu-submenu"
        aria-haspopup="true" tabindex="0"
        onclick="document.getElementById('pop').style.display='block';">…</li>
  </ul>
  <div id="pop">
    <div role="menuitem" tabindex="-1" aria-haspopup="true" class="ant-menu-submenu-title"
         onclick="document.getElementById('out').textContent='opened';">
      <span class="ant-menu-title-content">My Account</span>
    </div>
  </div>
  <div id="out" style="margin-top:120px">closed</div>
</body></html>
"""


async def _page(p):
    launch_kwargs = {}
    exe = os.environ.get("BG_CHROMIUM_EXECUTABLE")
    if exe:
        launch_kwargs["executable_path"] = exe
    try:
        browser = await p.chromium.launch(**launch_kwargs)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"No usable Chromium binary: {exc}")
    page = await browser.new_page()
    await page.set_content(_PAGE)
    return browser, page


async def test_click_item_collapsed_into_overflow_menu():
    aw = pytest.importorskip("playwright.async_api")
    from bubblegum import act, configure_runtime

    configure_runtime()
    async with aw.async_playwright() as p:
        browser, page = await _page(p)
        try:
            res = await act("Click on the My Account menu", channel="web", page=page)
            assert res.status in ("passed", "recovered"), res.error and res.error.message
            assert await page.eval_on_selector("#out", "e => e.textContent") == "opened"
        finally:
            await browser.close()


async def test_overflow_reveal_is_noop_when_item_on_bar():
    """When the item is already on the visible bar, resolution is unaffected."""
    aw = pytest.importorskip("playwright.async_api")
    from bubblegum import act, configure_runtime

    configure_runtime()
    _BAR = """
    <!doctype html><html><body style="font-family:Helvetica">
      <ul class="ant-menu ant-menu-horizontal" role="menu">
        <li role="menuitem" class="ant-menu-submenu-title"
            onclick="document.getElementById('o').textContent='opened';">
          <span class="ant-menu-title-content">My Account</span></li>
      </ul>
      <div id="o">closed</div>
    </body></html>
    """
    async with aw.async_playwright() as p:
        launch_kwargs = {}
        exe = os.environ.get("BG_CHROMIUM_EXECUTABLE")
        if exe:
            launch_kwargs["executable_path"] = exe
        try:
            browser = await p.chromium.launch(**launch_kwargs)
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"No usable Chromium binary: {exc}")
        try:
            page = await browser.new_page()
            await page.set_content(_BAR)
            res = await act("Click on the My Account menu", channel="web", page=page)
            assert res.status in ("passed", "recovered"), res.error and res.error.message
            assert await page.eval_on_selector("#o", "e => e.textContent") == "opened"
        finally:
            await browser.close()
